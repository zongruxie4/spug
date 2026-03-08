# Copyright: (c) OpenSpug Organization. https://github.com/openspug/spug
# Copyright: (c) <spug.dev@gmail.com>
# Released under the AGPL-3.0 License.
from apps.alarm.models import Group, Contact
from apps.setting.utils import AppSetting
from apps.notify.models import Notify
from libs.mail import Mail
from libs.utils import human_datetime
from libs.push import push_server
import requests
import json
import time
import hmac
import hashlib
import base64
from urllib.parse import urlencode


def _gen_dd_sign(secret):
    timestamp = str(int(time.time() * 1000))
    string_to_sign = f'{timestamp}\n{secret}'
    hmac_code = hmac.new(secret.encode('utf-8'), string_to_sign.encode('utf-8'), digestmod=hashlib.sha256).digest()
    sign = base64.b64encode(hmac_code).decode('utf-8')
    return timestamp, sign


def _gen_fs_sign(secret):
    timestamp = str(int(time.time()))
    string_to_sign = f'{timestamp}\n{secret}'
    hmac_code = hmac.new(string_to_sign.encode('utf-8'), b'', digestmod=hashlib.sha256).digest()
    sign = base64.b64encode(hmac_code).decode('utf-8')
    return timestamp, sign


class Notification:
    def __init__(self, grp, event, target, title, message, duration):
        self.grp = grp
        self.event = event
        self.title = title
        self.target = target
        self.message = message
        self.duration = duration
        self.spug_push_key = AppSetting.get_default('spug_push_key')

    @staticmethod
    def handle_request(url, data, mode=None):
        try:
            res = requests.post(url, json=data, timeout=15)
        except Exception as e:
            return Notify.make_system_notify('通知发送失败', f'接口调用异常: {e}')
        if res.status_code != 200:
            return Notify.make_system_notify('通知发送失败', f'返回状态码：{res.status_code}, 请求URL：{res.url}')

        if mode in ['dd', 'wx']:
            res = res.json()
            if res.get('errcode') == 0:
                return
        elif mode == 'spug':
            res = res.json()
            if not res.get('error'):
                return
        elif mode == 'fs':
            res = res.json()
            if res.get('StatusCode') == 0:
                return
        else:
            raise NotImplementedError
        Notify.make_system_notify('通知发送失败', f'返回数据：{res}')

    def monitor_by_email(self, users):
        mail_service = AppSetting.get_default('mail_service', {})
        body = [
            f'告警名称：{self.title}',
            f'告警对象：{self.target}',
            f'{"告警" if self.event == "1" else "恢复"}时间：{human_datetime()}',
            f'告警描述：{self.message}'
        ]
        if self.event == '2':
            body.append('故障持续：' + self.duration)
        if mail_service.get('server'):
            event_map = {'1': '监控告警通知', '2': '告警恢复通知'}
            subject = f'{event_map[self.event]}-{self.title}'
            mail = Mail(**mail_service)
            mail.send_text_mail(users, subject, '\r\n'.join(body) + '\r\n\r\n自动发送，请勿回复。')
        else:
            Notify.make_monitor_notify(
                '发送报警信息失败',
                '未配置报警服务，请在系统管理/系统设置/报警服务设置中配置邮件服务。'
            )

    def monitor_by_dd(self, users):
        texts = [
            '## %s ## ' % ('监控告警通知' if self.event == '1' else '告警恢复通知'),
            f'**告警名称：** <font color="#{"f90202" if self.event == "1" else "008000"}">{self.title}</font> ',
            f'**告警对象：** {self.target} ',
            f'**{"告警" if self.event == "1" else "恢复"}时间：** {human_datetime()} ',
            f'**告警描述：** {self.message} ',
        ]
        if self.event == '2':
            texts.append(f'**持续时间：** {self.duration} ')
        data = {
            'msgtype': 'markdown',
            'markdown': {
                'title': '监控告警通知',
                'text': '\n\n'.join(texts) + '\n\n> ###### 来自 Spug运维平台'
            },
            'at': {
                'isAtAll': True
            }
        }
        for url, secret in users:
            if secret:
                timestamp, sign = _gen_dd_sign(secret)
                url = f'{url}&{urlencode({"timestamp": timestamp, "sign": sign})}'
            self.handle_request(url, data, 'dd')

    def monitor_by_fs(self, users):
        title = '监控告警通知' if self.event == '1' else '告警恢复通知'
        content = [
            [{'tag': 'text', 'text': f'告警名称：{self.title}'}],
            [{'tag': 'text', 'text': f'告警对象：{self.target}'}],
            [{'tag': 'text', 'text': f'{"告警" if self.event == "1" else "恢复"}时间：{human_datetime()}'}],
            [{'tag': 'text', 'text': f'告警描述：{self.message}'}],
        ]
        if self.event == '2':
            content.append([{'tag': 'text', 'text': f'持续时间：{self.duration}'}])
        content.append([{'tag': 'text', 'text': '来自 Spug运维平台'}])
        for url, secret in users:
            data = {
                'msg_type': 'post',
                'content': {
                    'post': {
                        'zh_cn': {
                            'title': title,
                            'content': content
                        }
                    }
                }
            }
            if secret:
                timestamp, sign = _gen_fs_sign(secret)
                data['timestamp'] = timestamp
                data['sign'] = sign
            self.handle_request(url, data, 'fs')

    def monitor_by_qy_wx(self, users):
        color, title = ('warning', '监控告警通知') if self.event == '1' else ('info', '告警恢复通知')
        texts = [
            f'## {title}',
            f'**告警名称：** <font color="{color}">{self.title}</font> ',
            f'**告警对象：** {self.target}',
            f'**{"告警" if self.event == "1" else "恢复"}时间：** {human_datetime()} ',
            f'**告警描述：** {self.message} ',
        ]
        if self.event == '2':
            texts.append(f'**持续时间：** {self.duration} ')
        data = {
            'msgtype': 'markdown',
            'markdown': {
                'content': '\n'.join(texts) + '\n> 来自 Spug运维平台'
            }
        }
        for url in users:
            self.handle_request(url, data, 'wx')

    def monitor_by_spug_push(self, targets):
        if not self.spug_push_key:
            Notify.make_monitor_notify(
                '发送报警信息失败',
                '未绑定推送服务，请在系统管理/系统设置/推送服务设置中绑定推送助手账户。'
            )
            return
        data = {
            'source': 'monitor',
            'token': self.spug_push_key,
            'targets': list(targets),
            'dataset': {
                'title': self.title,
                'target': self.target,
                'message': self.message,
                'duration': self.duration,
                'event': self.event
            }
        }
        self.handle_request(f'{push_server}/spug/message/', data, 'spug')

    def dispatch_monitor(self, modes):
        u_ids, push_ids = [], []
        for item in Group.objects.filter(id__in=self.grp):
            for x in json.loads(item.contacts):
                if isinstance(x, str) and '_' in x:
                    push_ids.append(x)
                else:
                    u_ids.append(x)

        targets = set()
        for mode in modes:
            if mode == '1':
                wx_mp_ids = set(x for x in push_ids if x.startswith('wx_mp_'))
                targets.update(wx_mp_ids)
            elif mode == '2':
                sms_ids = set(x for x in push_ids if x.startswith('sms_'))
                targets.update(sms_ids)
            elif mode == '3':
                contacts = Contact.objects.filter(id__in=u_ids, ding__isnull=False)
                users = []
                for c in contacts:
                    sec = None
                    if c.secret:
                        sec = json.loads(c.secret).get('ding')
                    users.append((c.ding, sec))
                if not users:
                    Notify.make_monitor_notify(
                        '发送报警信息失败',
                        '未找到可用的通知对象，请确保设置了相关报警联系人的钉钉。'
                    )
                    continue
                self.monitor_by_dd(users)
            elif mode == '4':
                mail_ids = set(x for x in push_ids if x.startswith('mail_'))
                targets.update(mail_ids)
                users = set(x.email for x in Contact.objects.filter(id__in=u_ids, email__isnull=False))
                if not users:
                    if not mail_ids:
                        Notify.make_monitor_notify(
                            '发送报警信息失败',
                            '未找到可用的通知对象，请确保设置了相关报警联系人的邮件地址。'
                        )
                    continue
                self.monitor_by_email(users)
            elif mode == '5':
                users = set(x.qy_wx for x in Contact.objects.filter(id__in=u_ids, qy_wx__isnull=False))
                if not users:
                    Notify.make_monitor_notify(
                        '发送报警信息失败',
                        '未找到可用的通知对象，请确保设置了相关报警联系人的企业微信。'
                    )
                    continue
                self.monitor_by_qy_wx(users)
            elif mode == '6':
                voice_ids = set(x for x in push_ids if x.startswith('voice_'))
                targets.update(voice_ids)
            elif mode == '7':
                contacts = Contact.objects.filter(id__in=u_ids, feishu__isnull=False)
                users = []
                for c in contacts:
                    sec = None
                    if c.secret:
                        sec = json.loads(c.secret).get('feishu')
                    users.append((c.feishu, sec))
                if not users:
                    Notify.make_monitor_notify(
                        '发送报警信息失败',
                        '未找到可用的通知对象，请确保设置了相关报警联系人的飞书。'
                    )
                    continue
                self.monitor_by_fs(users)

        if targets:
            self.monitor_by_spug_push(targets)
