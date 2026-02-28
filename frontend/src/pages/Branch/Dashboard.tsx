import { useEffect, useState } from 'react'
import { Row, Col, Card, Statistic, Table, Tag, Typography, Spin } from 'antd'
import { CheckCircleOutlined, ClockCircleOutlined, CloseCircleOutlined, FileTextOutlined } from '@ant-design/icons'
import { pocApi } from '../../api/poc'

const { Title } = Typography

interface KPI {
  today_applications: number
  approved: number
  pending: number
  rejected: number
  approval_rate: number
}

interface AppRow {
  id: string
  name: string
  product: string
  score: number
  grade: string
  status: string
  applied_at: string
}

const statusColor = (s: string) =>
  s === '승인' ? 'success' : s === '심사중' ? 'processing' : 'error'

const columns = [
  { title: '신청ID', dataIndex: 'id', key: 'id' },
  { title: '고객명', dataIndex: 'name', key: 'name' },
  { title: '상품', dataIndex: 'product', key: 'product' },
  { title: '점수', dataIndex: 'score', key: 'score' },
  { title: '등급', dataIndex: 'grade', key: 'grade' },
  {
    title: '상태', dataIndex: 'status', key: 'status',
    render: (s: string) => <Tag color={statusColor(s)}>{s}</Tag>,
  },
  { title: '시각', dataIndex: 'applied_at', key: 'applied_at' },
]

export default function BranchDashboard() {
  const [kpi, setKpi] = useState<KPI | null>(null)
  const [apps, setApps] = useState<AppRow[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    pocApi.dashboard.branch().then((res) => {
      setKpi(res.data.kpi)
      setApps(res.data.recent_applications)
    }).finally(() => setLoading(false))
  }, [])

  if (loading) return <Spin size="large" style={{ display: 'block', marginTop: 80 }} />

  return (
    <>
      <Title level={4}>영업점 대시보드</Title>
      <Row gutter={16} style={{ marginBottom: 24 }}>
        <Col span={6}>
          <Card><Statistic title="오늘 신청" value={kpi?.today_applications} prefix={<FileTextOutlined />} /></Card>
        </Col>
        <Col span={6}>
          <Card><Statistic title="승인" value={kpi?.approved} prefix={<CheckCircleOutlined />} valueStyle={{ color: '#3f8600' }} /></Card>
        </Col>
        <Col span={6}>
          <Card><Statistic title="심사중" value={kpi?.pending} prefix={<ClockCircleOutlined />} valueStyle={{ color: '#cf9f00' }} /></Card>
        </Col>
        <Col span={6}>
          <Card><Statistic title="거절" value={kpi?.rejected} prefix={<CloseCircleOutlined />} valueStyle={{ color: '#cf1322' }} /></Card>
        </Col>
      </Row>
      <Card title={`최근 신청 목록 (오늘 승인율: ${kpi?.approval_rate}%)`}>
        <Table
          dataSource={apps}
          columns={columns}
          rowKey="id"
          pagination={false}
          size="small"
        />
      </Card>
    </>
  )
}
