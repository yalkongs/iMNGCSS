import { useEffect, useState } from 'react'
import { Card, Table, Tag, Typography, Spin, Badge, Tabs, Modal, Form, Input, Select, Button, message } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import client from '../../api/client'

const { Title, Text } = Typography

interface AppealItem {
  id: string
  app_id: string
  customer_name: string
  product: string
  amount: number
  original_score: number
  original_grade: string
  reason: string
  status: string
  submitted_at: string
  resolved_at: string | null
  revised_score: number | null
  revised_grade: string | null
  outcome_note: string | null
}

const STATUS_COLOR: Record<string, string> = {
  '접수': 'blue', '검토중': 'orange', '완료-인용': 'green', '완료-기각': 'default',
}

const COLUMNS: ColumnsType<AppealItem> = [
  { title: '이의번호', dataIndex: 'id', key: 'id', width: 130 },
  { title: '신청번호', dataIndex: 'app_id', key: 'app_id', width: 130 },
  { title: '고객명', dataIndex: 'customer_name', key: 'customer_name', width: 80 },
  { title: '상품', dataIndex: 'product', key: 'product', width: 80 },
  {
    title: '금액', dataIndex: 'amount', key: 'amount', width: 110,
    render: (v: number) => `${(v / 10000).toLocaleString()}만원`,
  },
  { title: '원점수', dataIndex: 'original_score', key: 'original_score', width: 70, align: 'center' },
  { title: '원등급', dataIndex: 'original_grade', key: 'original_grade', width: 60, align: 'center' },
  { title: '이의사유', dataIndex: 'reason', key: 'reason', ellipsis: true },
  {
    title: '상태', dataIndex: 'status', key: 'status', width: 100,
    render: (s: string) => <Tag color={STATUS_COLOR[s] ?? 'default'}>{s}</Tag>,
  },
  {
    title: '조정점수', dataIndex: 'revised_score', key: 'revised_score', width: 80, align: 'center',
    render: (v: number | null, row) => v
      ? <Text type={v > row.original_score ? 'success' : 'danger'}>{v}</Text>
      : '-',
  },
  { title: '접수일', dataIndex: 'submitted_at', key: 'submitted_at', width: 100 },
]

export default function BranchAppeal() {
  const [data, setData] = useState<AppealItem[]>([])
  const [loading, setLoading] = useState(true)
  const [modalOpen, setModalOpen] = useState(false)
  const [form] = Form.useForm()

  useEffect(() => {
    client.get('/poc/appeals')
      .then((r) => setData(r.data.appeals ?? []))
      .finally(() => setLoading(false))
  }, [])

  const counts = {
    total: data.length,
    pending: data.filter((d) => d.status === '접수').length,
    reviewing: data.filter((d) => d.status === '검토중').length,
    accepted: data.filter((d) => d.status === '완료-인용').length,
    rejected: data.filter((d) => d.status === '완료-기각').length,
  }

  const handleNewAppeal = async () => {
    await form.validateFields()
    message.success('이의제기가 접수되었습니다.')
    setModalOpen(false)
    form.resetFields()
  }

  return (
    <>
      <Title level={4}>이의제기 관리</Title>

      {/* 집계 */}
      <div style={{ display: 'flex', gap: 16, marginBottom: 16 }}>
        {[
          { label: '전체', value: counts.total, color: 'default' },
          { label: '접수', value: counts.pending, color: 'blue' },
          { label: '검토중', value: counts.reviewing, color: 'orange' },
          { label: '인용', value: counts.accepted, color: 'green' },
          { label: '기각', value: counts.rejected, color: 'red' },
        ].map((c) => (
          <Card key={c.label} size="small" style={{ minWidth: 100, textAlign: 'center' }}>
            <Badge color={c.color === 'default' ? '#d9d9d9' : c.color} text={c.label} /><br />
            <Text strong style={{ fontSize: 20 }}>{c.value}</Text>
          </Card>
        ))}
        <div style={{ flex: 1 }} />
        <Button type="primary" onClick={() => setModalOpen(true)}>이의제기 신규 접수</Button>
      </div>

      {loading ? <Spin /> : (
        <Tabs
          items={[
            {
              key: 'all', label: `전체 (${counts.total})`,
              children: <Table dataSource={data} columns={COLUMNS} rowKey="id" size="small" pagination={{ pageSize: 8 }} />,
            },
            {
              key: 'pending', label: <Badge count={counts.pending + counts.reviewing}>진행 중</Badge>,
              children: <Table dataSource={data.filter((d) => ['접수', '검토중'].includes(d.status))} columns={COLUMNS} rowKey="id" size="small" />,
            },
            {
              key: 'done', label: '완료',
              children: <Table dataSource={data.filter((d) => d.status.startsWith('완료'))} columns={COLUMNS} rowKey="id" size="small" />,
            },
          ]}
        />
      )}

      <Modal title="이의제기 신규 접수" open={modalOpen} onCancel={() => setModalOpen(false)}
        footer={[<Button key="cancel" onClick={() => setModalOpen(false)}>취소</Button>, <Button key="ok" type="primary" onClick={handleNewAppeal}>접수</Button>]}>
        <Form form={form} layout="vertical">
          <Form.Item name="app_id" label="신청 번호" rules={[{ required: true }]}>
            <Input placeholder="APP-202510001" />
          </Form.Item>
          <Form.Item name="reason_type" label="이의 사유 유형" rules={[{ required: true }]}>
            <Select>
              <Select.Option value="income">소득 증빙 추가 제출</Select.Option>
              <Select.Option value="employment">재직 정보 오류 수정</Select.Option>
              <Select.Option value="cb_error">CB 데이터 오류</Select.Option>
              <Select.Option value="other">기타</Select.Option>
            </Select>
          </Form.Item>
          <Form.Item name="detail" label="상세 내용">
            <Input.TextArea rows={3} />
          </Form.Item>
        </Form>
      </Modal>
    </>
  )
}
