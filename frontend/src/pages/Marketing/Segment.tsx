import { useEffect, useState } from 'react'
import { Card, Table, Tag, Typography, Spin, Statistic, Row, Col } from 'antd'
import { pocApi } from '../../api/poc'

const { Title } = Typography

interface Segment {
  segment_code: string
  segment_name: string
  count: number
  approval_rate: number
  avg_score: number
  avg_rate: number
  rate_discount: number
  limit_multiplier: number
  eq_floor: string
}

const columns = [
  { title: '세그먼트', dataIndex: 'segment_code', key: 'segment_code', render: (v: string) => <Tag color="blue">{v}</Tag> },
  { title: '대상', dataIndex: 'segment_name', key: 'segment_name' },
  { title: '건수', dataIndex: 'count', key: 'count', render: (v: number) => v.toLocaleString() },
  { title: '승인율', dataIndex: 'approval_rate', key: 'approval_rate', render: (v: number) => `${v.toFixed(1)}%` },
  { title: '평균 점수', dataIndex: 'avg_score', key: 'avg_score' },
  { title: '평균 금리', dataIndex: 'avg_rate', key: 'avg_rate', render: (v: number) => `${v.toFixed(2)}%` },
  {
    title: '금리 할인', dataIndex: 'rate_discount', key: 'rate_discount',
    render: (v: number) => v !== 0 ? <Tag color="green">{(v * 100).toFixed(2)}%p</Tag> : '—',
  },
  { title: '한도 배수', dataIndex: 'limit_multiplier', key: 'limit_multiplier', render: (v: number) => `${v}x` },
  { title: 'EQ 하한', dataIndex: 'eq_floor', key: 'eq_floor', render: (v: string) => v !== '—' ? <Tag>{v}</Tag> : '—' },
]

export default function MarketingSegment() {
  const [segments, setSegments] = useState<Segment[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    pocApi.segmentStats().then((res) => setSegments(res.data.segments)).finally(() => setLoading(false))
  }, [])

  if (loading) return <Spin size="large" style={{ display: 'block', marginTop: 80 }} />

  const total = segments.reduce((s, r) => s + r.count, 0)
  const special = segments.filter((s) => s.segment_code !== '일반').reduce((s, r) => s + r.count, 0)

  return (
    <>
      <Title level={4}>세그먼트 현황</Title>
      <Row gutter={16} style={{ marginBottom: 24 }}>
        <Col span={8}><Card><Statistic title="전체 건수" value={total.toLocaleString()} /></Card></Col>
        <Col span={8}><Card><Statistic title="특수 세그먼트" value={special.toLocaleString()} /></Card></Col>
        <Col span={8}><Card><Statistic title="특수 비중" value={`${(special / total * 100).toFixed(1)}%`} /></Card></Col>
      </Row>
      <Card title="세그먼트별 현황">
        <Table dataSource={segments} columns={columns} rowKey="segment_code" pagination={false} />
      </Card>
    </>
  )
}
