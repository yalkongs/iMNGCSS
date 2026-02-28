import { useEffect, useState } from 'react'
import { Card, Table, Tag, Typography, Select, Space, Button } from 'antd'
import { pocApi } from '../../api/poc'

const { Title } = Typography

interface AuditRecord {
  id: number
  param_key: string
  old_value: string
  new_value: string
  changed_by: string
  changed_at: string
  reason: string
}

const userColor = (u: string) =>
  u === 'admin' ? 'red' : u === 'risk_manager' ? 'orange' : 'blue'

export default function PolicyAudit() {
  const [records, setRecords] = useState<AuditRecord[]>([])
  const [limit, setLimit] = useState(30)
  const [loading, setLoading] = useState(true)

  const fetch = () => {
    setLoading(true)
    pocApi.auditTrail({ limit }).then((res) => setRecords(res.data.records)).finally(() => setLoading(false))
  }

  useEffect(() => { fetch() }, [limit])

  const columns = [
    {
      title: '변경일시', dataIndex: 'changed_at', key: 'changed_at',
      render: (v: string) => v.replace('T', ' '),
    },
    { title: '파라미터 Key', dataIndex: 'param_key', key: 'param_key', render: (v: string) => <code>{v}</code> },
    { title: '변경 전', dataIndex: 'old_value', key: 'old_value' },
    { title: '변경 후', dataIndex: 'new_value', key: 'new_value', render: (v: string) => <strong>{v}</strong> },
    {
      title: '변경자', dataIndex: 'changed_by', key: 'changed_by',
      render: (v: string) => <Tag color={userColor(v)}>{v}</Tag>,
    },
    { title: '사유', dataIndex: 'reason', key: 'reason' },
  ]

  return (
    <>
      <Title level={4}>감사 추적 (Audit Trail)</Title>
      <Card>
        <Space style={{ marginBottom: 16 }}>
          <Select
            value={limit}
            onChange={setLimit}
            options={[
              { label: '최근 30건', value: 30 },
              { label: '최근 50건', value: 50 },
              { label: '최근 100건', value: 100 },
            ]}
            style={{ width: 140 }}
          />
          <Button onClick={fetch}>새로고침</Button>
        </Space>
        <Table
          dataSource={records}
          columns={columns}
          rowKey="id"
          loading={loading}
          pagination={{ pageSize: 20, showSizeChanger: false }}
          size="small"
          scroll={{ x: 900 }}
        />
      </Card>
    </>
  )
}
