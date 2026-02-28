import { useEffect, useState } from 'react'
import { Row, Col, Card, Typography, Spin } from 'antd'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell, Legend,
} from 'recharts'
import { pocApi } from '../../api/poc'

const { Title } = Typography
const COLORS = ['#1677ff', '#52c41a', '#faad14', '#f5222d', '#722ed1']

export default function MarketingDashboard() {
  const [data, setData] = useState<{
    channel_stats: { channel: string; applications: number; conversion_rate: number }[]
    segment_distribution: { segment: string; count: number }[]
    monthly_trend: { month: string; applications: number }[]
  } | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    pocApi.dashboard.marketing().then((res) => setData(res.data)).finally(() => setLoading(false))
  }, [])

  if (loading) return <Spin size="large" style={{ display: 'block', marginTop: 80 }} />

  return (
    <>
      <Title level={4}>비대면 마케팅 대시보드</Title>
      <Row gutter={16} style={{ marginBottom: 24 }}>
        <Col span={14}>
          <Card title="채널별 신청 건수 및 전환율">
            <ResponsiveContainer width="100%" height={260}>
              <BarChart data={data?.channel_stats}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="channel" />
                <YAxis yAxisId="left" />
                <YAxis yAxisId="right" orientation="right" unit="%" />
                <Tooltip />
                <Legend />
                <Bar yAxisId="left" dataKey="applications" name="신청건수" fill="#1677ff" />
                <Bar yAxisId="right" dataKey="conversion_rate" name="전환율(%)" fill="#52c41a" />
              </BarChart>
            </ResponsiveContainer>
          </Card>
        </Col>
        <Col span={10}>
          <Card title="세그먼트 분포">
            <ResponsiveContainer width="100%" height={260}>
              <PieChart>
                <Pie
                  data={data?.segment_distribution}
                  dataKey="count"
                  nameKey="segment"
                  cx="50%"
                  cy="50%"
                  outerRadius={90}
                  label={({ name, percent }) => `${name} ${((percent ?? 0) * 100).toFixed(0)}%`}
                >
                  {data?.segment_distribution.map((_, idx) => (
                    <Cell key={idx} fill={COLORS[idx % COLORS.length]} />
                  ))}
                </Pie>
                <Tooltip />
              </PieChart>
            </ResponsiveContainer>
          </Card>
        </Col>
      </Row>
      <Card title="월별 신청 추이">
        <ResponsiveContainer width="100%" height={200}>
          <BarChart data={data?.monthly_trend}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="month" tick={{ fontSize: 11 }} />
            <YAxis />
            <Tooltip />
            <Bar dataKey="applications" name="신청건수" fill="#1677ff" />
          </BarChart>
        </ResponsiveContainer>
      </Card>
    </>
  )
}
