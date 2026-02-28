import { useEffect, useState } from 'react'
import { Card, Row, Col, Statistic, Table, Typography, Spin } from 'antd'
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend, ReferenceLine,
} from 'recharts'
import client from '../../api/client'

const { Title } = Typography

export default function RiskCalibration() {
  const [data, setData] = useState<{
    deciles: number[]
    predicted_pd: number[]
    actual_dr: number[]
    ece: number
    brier_score: number
  } | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    client.get('/poc/calibration-curve').then((res) => setData(res.data)).finally(() => setLoading(false))
  }, [])

  if (loading) return <Spin size="large" style={{ display: 'block', marginTop: 80 }} />

  const chartData = data!.deciles.map((d, i) => ({
    decile: `D${d}`,
    predicted: +(data!.predicted_pd[i] * 100).toFixed(3),
    actual: +(data!.actual_dr[i] * 100).toFixed(3),
  }))

  const tableColumns = [
    { title: '분위', dataIndex: 'decile', key: 'decile' },
    { title: '예측 PD (%)', dataIndex: 'predicted', key: 'predicted' },
    { title: '실제 DR (%)', dataIndex: 'actual', key: 'actual' },
    {
      title: '차이', key: 'diff',
      render: (_: unknown, r: { predicted: number; actual: number }) => {
        const d = (r.actual - r.predicted).toFixed(3)
        return <span style={{ color: Math.abs(+d) > 0.5 ? '#f5222d' : '#3f8600' }}>{d}</span>
      },
    },
  ]

  return (
    <>
      <Title level={4}>칼리브레이션 (Calibration)</Title>
      <Row gutter={16} style={{ marginBottom: 24 }}>
        <Col span={6}><Card><Statistic title="ECE" value={data!.ece.toFixed(4)} /></Card></Col>
        <Col span={6}><Card><Statistic title="Brier Score" value={data!.brier_score.toFixed(4)} /></Card></Col>
        <Col span={12}>
          <Card size="small" style={{ background: '#f6ffed', borderColor: '#b7eb8f' }}>
            ECE &lt; 0.03, Brier &lt; 0.10 → 양호한 칼리브레이션
          </Card>
        </Col>
      </Row>
      <Row gutter={16}>
        <Col span={14}>
          <Card title="칼리브레이션 곡선 (10분위)">
            <ResponsiveContainer width="100%" height={300}>
              <LineChart data={chartData}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="decile" />
                <YAxis unit="%" />
                <Tooltip formatter={(v) => typeof v === 'number' ? `${v.toFixed(3)}%` : v} />
                <Legend />
                <ReferenceLine y={0} stroke="#aaa" />
                <Line type="monotone" dataKey="predicted" name="예측 PD" stroke="#1677ff" strokeWidth={2} />
                <Line type="monotone" dataKey="actual" name="실제 DR" stroke="#f5222d" strokeWidth={2} strokeDasharray="5 5" />
              </LineChart>
            </ResponsiveContainer>
          </Card>
        </Col>
        <Col span={10}>
          <Card title="분위별 상세">
            <Table dataSource={chartData} columns={tableColumns} rowKey="decile" pagination={false} size="small" />
          </Card>
        </Col>
      </Row>
    </>
  )
}
