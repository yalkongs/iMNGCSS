import { useEffect, useState } from 'react'
import { Row, Col, Card, Statistic, Typography, Spin } from 'antd'
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend } from 'recharts'
import { pocApi } from '../../api/poc'

const { Title } = Typography

export default function ProductDashboard() {
  const [data, setData] = useState<{
    product_stats: { product: string; raroc: number; el_ratio: number; rwa: number; nim: number }[]
    rate_simulation: { base_rate: number; spread: number; risk_premium: number; total_rate: number }
  } | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    pocApi.dashboard.product().then((res) => setData(res.data)).finally(() => setLoading(false))
  }, [])

  if (loading) return <Spin size="large" style={{ display: 'block', marginTop: 80 }} />

  return (
    <>
      <Title level={4}>상품(여신) 대시보드</Title>
      <Row gutter={16} style={{ marginBottom: 24 }}>
        {data?.product_stats.map((p) => (
          <Col span={8} key={p.product}>
            <Card title={p.product}>
              <Statistic title="RAROC" value={`${p.raroc.toFixed(1)}%`} />
              <Statistic title="EL 비율" value={`${p.el_ratio.toFixed(2)}%`} />
              <Statistic title="NIM" value={`${p.nim.toFixed(2)}%`} />
            </Card>
          </Col>
        ))}
      </Row>
      <Row gutter={16}>
        <Col span={16}>
          <Card title="상품별 RAROC 비교">
            <ResponsiveContainer width="100%" height={240}>
              <BarChart data={data?.product_stats}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="product" />
                <YAxis unit="%" />
                <Tooltip formatter={(v) => typeof v === 'number' ? `${v.toFixed(1)}%` : v} />
                <Legend />
                <Bar dataKey="raroc" name="RAROC" fill="#1677ff" />
                <Bar dataKey="nim" name="NIM" fill="#52c41a" />
              </BarChart>
            </ResponsiveContainer>
          </Card>
        </Col>
        <Col span={8}>
          <Card title="금리 구성">
            <Statistic title="기준금리" value={`${data?.rate_simulation.base_rate}%`} style={{ marginBottom: 12 }} />
            <Statistic title="가산금리" value={`${data?.rate_simulation.spread.toFixed(2)}%`} style={{ marginBottom: 12 }} />
            <Statistic title="위험프리미엄" value={`${data?.rate_simulation.risk_premium.toFixed(2)}%`} style={{ marginBottom: 12 }} />
            <Statistic title="최종금리" value={`${data?.rate_simulation.total_rate.toFixed(2)}%`} valueStyle={{ color: '#1677ff', fontWeight: 700 }} />
          </Card>
        </Col>
      </Row>
    </>
  )
}
