/**
 * Copyright (c) OpenSpug Organization. https://github.com/openspug/spug
 * Copyright (c) <spug.dev@gmail.com>
 * Released under the AGPL-3.0 License.
 */
import React, { useState, useMemo } from 'react';
import { observer } from 'mobx-react';
import { Modal, Form, Input, Tooltip, Checkbox, Divider, message } from 'antd';
import { ThunderboltOutlined, LoadingOutlined } from '@ant-design/icons';
import http from 'libs/http';
import store from './store';

const channelConfig = [
  {
    key: 'email',
    label: '邮箱',
    fields: [
      { name: 'email', label: '邮箱地址', placeholder: '请输入邮箱地址', testMode: '4' }
    ]
  },
  {
    key: 'ding',
    label: '钉钉',
    fields: [
      { name: 'ding', label: 'Webhook', placeholder: 'https://oapi.dingtalk.com/robot/send?access_token=xxx', testMode: '3' },
      { name: 'ding_secret', label: 'Secret', placeholder: 'SECxxxxxxxx', extra: '可选，机器人安全设置中的加签密钥' }
    ],
    help: { text: '钉钉收不到通知？请参考', link: 'https://ops.spug.cc/docs/use-problem#use-dd', linkText: '官方文档' }
  },
  {
    key: 'feishu',
    label: '飞书',
    fields: [
      { name: 'feishu', label: 'Webhook', placeholder: 'https://open.feishu.cn/open-apis/bot/v2/hook/xxx', testMode: '7' },
      { name: 'feishu_secret', label: 'Secret', placeholder: 'xxxxxxxx', extra: '可选，机器人安全设置中的签名校验密钥' }
    ]
  },
  {
    key: 'qy_wx',
    label: '企业微信',
    fields: [
      { name: 'qy_wx', label: 'Webhook', placeholder: 'https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=xxx', testMode: '5' }
    ]
  }
];

export default observer(function () {
  const [form] = Form.useForm();
  const [loading, setLoading] = useState(false);
  const [testLoading, setTestLoading] = useState('0');

  const initialChannels = useMemo(() => ({
    email: !!store.record.email,
    ding: !!store.record.ding,
    feishu: !!store.record.feishu,
    qy_wx: !!store.record.qy_wx,
  }), []);

  const [channels, setChannels] = useState(initialChannels);

  function handleChannelToggle(key, checked) {
    setChannels(prev => ({ ...prev, [key]: checked }));
    if (!checked) {
      const channel = channelConfig.find(c => c.key === key);
      if (channel) {
        form.setFieldsValue(channel.fields.reduce((values, field) => {
          values[field.name] = null;
          return values;
        }, {}));
      }
    }
  }

  function handleSubmit() {
    setLoading(true);
    const formData = form.getFieldsValue();
    formData['id'] = store.record.id;
    channelConfig.forEach(channel => {
      if (!channels[channel.key]) {
        channel.fields.forEach(field => {
          formData[field.name] = null;
        });
      }
    });
    const secret = {};
    if (formData.ding && formData.ding_secret) secret.ding = formData.ding_secret;
    if (formData.feishu && formData.feishu_secret) secret.feishu = formData.feishu_secret;
    delete formData.ding_secret;
    delete formData.feishu_secret;
    formData.secret = Object.keys(secret).length ? JSON.stringify(secret) : null;
    http.post('/api/alarm/contact/', formData)
      .then(res => {
        message.success('操作成功');
        store.formVisible = false;
        store.fetchRecords()
      }, () => setLoading(false))
  }

  function handleTest(mode, name) {
    const value = form.getFieldValue(name)
    if (!value) return message.error('请输入后再执行测试')
    const secretName = name === 'ding' ? 'ding_secret' : name === 'feishu' ? 'feishu_secret' : null;
    const secret = secretName ? form.getFieldValue(secretName) : undefined;
    setTestLoading(mode)
    http.post('/api/alarm/test/', {mode, value, secret})
      .then(() => {
        message.success('执行成功')
      })
      .finally(() => setTestLoading('0'))
  }

  function Test(props) {
    return testLoading === props.mode ? (
      <LoadingOutlined style={{fontSize: 16, color: '#faad14'}}/>
    ) : (
      <Tooltip title="执行测试">
        <ThunderboltOutlined
          style={{fontSize: 16, color: '#faad14', cursor: 'pointer'}}
          onClick={() => handleTest(props.mode, props.name)}/>
      </Tooltip>
    );
  }

  const secret = store.record.secret ? JSON.parse(store.record.secret) : {};

  return (
    <Modal
      visible
      width={800}
      maskClosable={false}
      title={store.record.id ? '编辑联系人' : '新建联系人'}
      onCancel={() => store.formVisible = false}
      confirmLoading={loading}
      onOk={handleSubmit}>
      <Form form={form} initialValues={{
        ...store.record,
        ding_secret: secret.ding,
        feishu_secret: secret.feishu,
      }} labelCol={{span: 6}} wrapperCol={{span: 14}}>
        <Form.Item required name="name" label="姓名">
          <Input placeholder="请输入联系人姓名"/>
        </Form.Item>
        <Form.Item name="phone" label="手机号">
          <Input placeholder="请输入手机号"/>
        </Form.Item>
        <Divider orientation="left" style={{margin: '8px 0 16px'}}>通知渠道</Divider>
        {channelConfig.map(channel => (
          <div key={channel.key} style={{marginBottom: channels[channel.key] ? 16 : 4}}>
            <Form.Item wrapperCol={{offset: 6, span: 14}} style={{marginBottom: 0}}>
              <Checkbox
                checked={channels[channel.key]}
                onChange={e => handleChannelToggle(channel.key, e.target.checked)}
              >
                {channel.label}
              </Checkbox>
            </Form.Item>
            {channels[channel.key] && channel.fields.map(field => {
              const extra = field.extra || (channel.help && field === channel.fields[0] ? (
                <span>
                  {channel.help.text}
                  <a target="_blank" rel="noopener noreferrer" href={channel.help.link}>{channel.help.linkText}</a>
                </span>
              ) : undefined);
              return (
                <Form.Item key={field.name} name={field.name} label={field.label} extra={extra}>
                  <Input
                    placeholder={field.placeholder}
                    suffix={field.testMode ? <Test mode={field.testMode} name={field.name}/> : <span/>}
                  />
                </Form.Item>
              );
            })}
          </div>
        ))}
      </Form>
    </Modal>
  )
})
