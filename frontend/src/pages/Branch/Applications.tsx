import { useEffect, useState } from 'react'
import { Table, Tag, Card, Select, Button, Space, Typography } from 'antd'
import { pocApi } from '../../api/poc'

const { Title } = Typography

const statusColor = (s: string) =>
  s === '승인' ? 'success' : s === '심사중' ? 'processing' : 'error'

const columns = [
  { title: '신청ID', dataIndex: 'id', key: 'id' },
  { title: '고객명', dataIndex: 'customer_name', key: 'customer_name' },
  { title: '상품', dataIndex: 'product', key: 'product' },
  { title: '금액', dataIndex: 'amount', key: 'amount', render: (v: number) => `${(v / 10000).toLocaleString()}만원` },
  { title: '점수', dataIndex: 'score', key: 'score' },
  { title: '등급', dataIndex: 'grade', key: 'grade' },
  { title: '금리', dataIndex: 'rate', key: 'rate', render: (v: number) => `${v}%` },
  {
    title: '상태', dataIndex: 'status', key: 'status',
    render: (s: string) => <Tag color={statusColor(s)}>{s}</Tag>,
  },
  { title: '세그먼트', dataIndex: 'segment', key: 'segment', render: (v: string) => v || '—' },
  { title: '신청일', dataIndex: 'applied_at', key: 'applied_at' },
]

export default function BranchApplications() {
  const [data, setData] = useState<{ total: number; items: unknown[] }>({ total: 0, items: [] })
  const [status, setStatus] = useState<string | undefined>(undefined)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(false)

  const fetch = () => {
    setLoading(true)
    pocApi.applications.list({ page, page_size: 20, status }).then((res) => {
      setData(res.data)
    }).finally(() => setLoading(false))
  }

  useEffect(() => { fetch() }, [page, status])

  return (
    <>
      <Title level={4}>신청 목록</Title>
      <Card>
        <Space style={{ marginBottom: 16 }}>
          <Select
            placeholder="상태 필터"
            allowClear
            style={{ width: 140 }}
            onChange={(v) => { setStatus(v); setPage(1) }}
            options={[
              { label: '승인', value: '승인' },
              { label: '심사중', value: '심사중' },
              { label: '거절', value: '거절' },
            ]}
          />
          <Button onClick={fetch}>새로고침</Button>
        </Space>
        <Table
          dataSource={data.items as Record<string, unknown>[]}
          columns={columns}
          rowKey="id"
          loading={loading}
          pagination={{
            total: data.total,
            current: page,
            pageSize: 20,
            onChange: setPage,
          }}
          size="small"
          scroll={{ x: 900 }}
        />
      </Card>
    </>
  )
}
