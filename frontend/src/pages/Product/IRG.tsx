import { useEffect, useState } from 'react'
import { Card, Table, Tag, Typography, Spin, Row, Col } from 'antd'
import client from '../../api/client'

const { Title } = Typography

interface IRGItem {
  industry: string
  irg: string
  rate_adj: number
  active: boolean
}

const irgColor = (irg: string) =>
  irg === 'L' ? 'success' : irg === 'M' ? 'blue' : irg === 'H' ? 'warning' : 'error'

const columns = [
  { title: '업종', dataIndex: 'industry', key: 'industry' },
  {
    title: 'IRG', dataIndex: 'irg', key: 'irg',
    render: (v: string) => <Tag color={irgColor(v)}>{v}</Tag>,
  },
  {
    title: '금리 조정', dataIndex: 'rate_adj', key: 'rate_adj',
    render: (v: number) => {
      const pct = (v * 100).toFixed(2)
      return v < 0 ? <Tag color="green">{pct}%p</Tag> : v > 0 ? <Tag color="red">+{pct}%p</Tag> : <span>기준</span>
    },
  },
  {
    title: '활성', dataIndex: 'active', key: 'active',
    render: (v: boolean) => <Tag color={v ? 'success' : 'default'}>{v ? '활성' : '비활성'}</Tag>,
  },
]

const scaleColumns = [
  { title: 'IRG', dataIndex: 'grade', key: 'grade' },
  { title: '설명', dataIndex: 'desc', key: 'desc' },
  { title: 'Rate Adj', dataIndex: 'adj', key: 'adj', render: (v: number) => v > 0 ? `+${(v*100).toFixed(0)}bp` : `${(v*100).toFixed(0)}bp` },
]

export default function ProductIRG() {
  const [items, setItems] = useState<IRGItem[]>([])
  const [scale, setScale] = useState<Record<string, number>>({})
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    client.get('/poc/irg-master').then((res) => {
      setItems(res.data.irg_grades)
      setScale(res.data.scale)
    }).finally(() => setLoading(false))
  }, [])

  if (loading) return <Spin size="large" style={{ display: 'block', marginTop: 80 }} />

  const scaleData = [
    { grade: 'L', desc: '저위험 (IT, 의료 등)', adj: scale['L'] },
    { grade: 'M', desc: '중위험 (금융, 제조 등)', adj: scale['M'] },
    { grade: 'H', desc: '고위험 (건설, 부동산)', adj: scale['H'] },
    { grade: 'VH', desc: '초고위험 (요식, 코인 등)', adj: scale['VH'] },
  ]

  return (
    <>
      <Title level={4}>산업 리스크 등급 (IRG) 현황</Title>
      <Row gutter={16}>
        <Col span={8}>
          <Card title="IRG 스케일">
            <Table dataSource={scaleData} columns={scaleColumns} rowKey="grade" pagination={false} size="small" />
          </Card>
        </Col>
        <Col span={16}>
          <Card title="업종별 IRG">
            <Table dataSource={items} columns={columns} rowKey="industry" pagination={false} />
          </Card>
        </Col>
      </Row>
    </>
  )
}
