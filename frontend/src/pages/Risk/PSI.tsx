import { useEffect, useState } from 'react'
import { Card, Row, Col, Typography, Spin, Badge } from 'antd'
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, ReferenceLine, Legend,
} from 'recharts'
import client from '../../api/client'

const { Title } = Typography

const PSI_COLORS = ['#1677ff', '#52c41a', '#faad14', '#f5222d']

export default function RiskPSI() {
  const [data, setData] = useState<{
    months: string[]
    score_psi: number[]
    feature_psi: Record<string, number[]>
    threshold: { green: number; yellow: number }
  } | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    client.get('/poc/psi-detail').then((res) => setData(res.data)).finally(() => setLoading(false))
  }, [])

  if (loading) return <Spin size="large" style={{ display: 'block', marginTop: 80 }} />

  const chartData = data!.months.map((m, i) => ({
    month: m,
    score_psi: data!.score_psi[i],
    ...Object.fromEntries(Object.entries(data!.feature_psi).map(([k, v]) => [k, v[i]])),
  }))

  const features = Object.keys(data!.feature_psi)

  return (
    <>
      <Title level={4}>PSI 모니터링</Title>
      <Row gutter={16}>
        <Col span={24}>
          <Card title="Score PSI 추이" extra={
            <span>
              <Badge status="success" text="정상(<0.10)" style={{ marginRight: 12 }} />
              <Badge status="warning" text="경고(<0.20)" style={{ marginRight: 12 }} />
              <Badge status="error" text="위험(≥0.20)" />
            </span>
          }>
            <ResponsiveContainer width="100%" height={280}>
              <LineChart data={chartData}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="month" tick={{ fontSize: 11 }} />
                <YAxis domain={[0, 0.3]} />
                <Tooltip formatter={(v) => typeof v === 'number' ? v.toFixed(4) : v} />
                <ReferenceLine y={0.1} stroke="#faad14" strokeDasharray="5 5" label="경고" />
                <ReferenceLine y={0.2} stroke="#f5222d" strokeDasharray="5 5" label="위험" />
                <Line type="monotone" dataKey="score_psi" name="Score PSI" stroke="#1677ff" dot={false} strokeWidth={2} />
              </LineChart>
            </ResponsiveContainer>
          </Card>
        </Col>
      </Row>
      <Row gutter={16} style={{ marginTop: 16 }}>
        <Col span={24}>
          <Card title="Feature PSI 추이">
            <ResponsiveContainer width="100%" height={280}>
              <LineChart data={chartData}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="month" tick={{ fontSize: 11 }} />
                <YAxis domain={[0, 0.2]} />
                <Tooltip formatter={(v) => typeof v === 'number' ? v.toFixed(4) : v} />
                <ReferenceLine y={0.1} stroke="#f5222d" strokeDasharray="5 5" label="임계값" />
                <Legend />
                {features.map((f, i) => (
                  <Line key={f} type="monotone" dataKey={f} stroke={PSI_COLORS[i % PSI_COLORS.length]} dot={false} strokeWidth={2} />
                ))}
              </LineChart>
            </ResponsiveContainer>
          </Card>
        </Col>
      </Row>
    </>
  )
}
