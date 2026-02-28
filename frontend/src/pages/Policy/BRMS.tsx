import { useEffect, useState } from 'react'
import { Card, Table, Tag, Typography, Select, Space, Button, Modal, Form, Input, message } from 'antd'
import { PlusOutlined } from '@ant-design/icons'
import client from '../../api/client'

const { Title } = Typography

interface BRMSParam {
  key: string
  value: string
  description: string
  category: string
  active: boolean
  updated_at: string
}

const categoryColor = (c: string) =>
  c === '규제' ? 'red' : c === '스트레스DSR' ? 'orange' : c === '스코어' ? 'blue' : 'default'

export default function PolicyBRMS() {
  const [params, setParams] = useState<BRMSParam[]>([])
  const [filtered, setFiltered] = useState<BRMSParam[]>([])
  const [category, setCategory] = useState<string | undefined>(undefined)
  const [loading, setLoading] = useState(true)
  const [modalOpen, setModalOpen] = useState(false)
  const [form] = Form.useForm()

  const fetch = () => {
    setLoading(true)
    client.get('/poc/brms-params').then((res) => {
      setParams(res.data.params)
      setFiltered(res.data.params)
    }).finally(() => setLoading(false))
  }

  useEffect(() => { fetch() }, [])

  useEffect(() => {
    setFiltered(category ? params.filter((p) => p.category === category) : params)
  }, [category, params])

  const columns = [
    { title: 'Key', dataIndex: 'key', key: 'key', render: (v: string) => <code>{v}</code> },
    { title: '현재값', dataIndex: 'value', key: 'value' },
    { title: '설명', dataIndex: 'description', key: 'description' },
    {
      title: '카테고리', dataIndex: 'category', key: 'category',
      render: (v: string) => <Tag color={categoryColor(v)}>{v}</Tag>,
    },
    {
      title: '활성', dataIndex: 'active', key: 'active',
      render: (v: boolean) => <Tag color={v ? 'success' : 'default'}>{v ? '활성' : '비활성'}</Tag>,
    },
    { title: '최종수정', dataIndex: 'updated_at', key: 'updated_at' },
  ]

  const categories = [...new Set(params.map((p) => p.category))]

  const onSave = () => {
    form.validateFields().then(() => {
      message.success('파라미터가 등록되었습니다. (POC 데모: 실제 저장되지 않음)')
      setModalOpen(false)
      form.resetFields()
    })
  }

  return (
    <>
      <Title level={4}>BRMS 파라미터 관리</Title>
      <Card>
        <Space style={{ marginBottom: 16 }}>
          <Select
            placeholder="카테고리 필터"
            allowClear
            style={{ width: 160 }}
            onChange={setCategory}
            options={categories.map((c) => ({ label: c, value: c }))}
          />
          <Button onClick={fetch}>새로고침</Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setModalOpen(true)}>
            파라미터 등록
          </Button>
        </Space>
        <Table dataSource={filtered} columns={columns} rowKey="key" loading={loading} pagination={false} size="small" />
      </Card>

      <Modal title="파라미터 등록" open={modalOpen} onOk={onSave} onCancel={() => setModalOpen(false)}>
        <Form form={form} layout="vertical">
          <Form.Item name="key" label="Key" rules={[{ required: true }]}>
            <Input placeholder="예: dsr.max_ratio" />
          </Form.Item>
          <Form.Item name="value" label="값" rules={[{ required: true }]}>
            <Input placeholder="예: 0.40" />
          </Form.Item>
          <Form.Item name="description" label="설명">
            <Input />
          </Form.Item>
          <Form.Item name="reason" label="변경 사유" rules={[{ required: true }]}>
            <Input.TextArea rows={2} placeholder="예: 금융위원회 가이드라인 반영" />
          </Form.Item>
        </Form>
      </Modal>
    </>
  )
}
