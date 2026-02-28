import { useEffect, useState } from 'react'
import { Card, Row, Col, Table, Tag, Typography, Spin, Statistic } from 'antd'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  ReferenceLine, Cell,
} from 'recharts'
import client from '../../api/client'

const { Title, Text } = Typography

interface ScoreDistData {
  histogram: { bin: string; count: number; zone: string; cum_pct: number }[]
  by_grade: { grade: string; min: number; max: number; count: number; pct: number; avg_pd: number }[]
  stats: {
    mean: number; median: number; p10: number; p90: number; std: number
    auto_reject_pct: number; manual_review_pct: number; auto_approve_pct: number
  }
  gini: number
  ks: number
}

const ZONE_COLOR: Record<string, string> = {
  '자동거절': '#f5222d',
  '수동심사': '#faad14',
  '자동승인': '#52c41a',
}

export default function RiskScoreDistribution() {
  const [data, setData] = useState<ScoreDistData | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    client.get('/poc/score-distribution').then((r) => setData(r.data)).finally(() => setLoading(false))
  }, [])

  if (loading) return <Spin size="large" style={{ display: 'block', marginTop: 80 }} />

  const st = data!.stats

  const gradeColumns = [
    { title: '등급', dataIndex: 'grade', key: 'grade' },
    { title: '점수 범위', key: 'range', render: (_: unknown, r: { min: number; max: number }) => `${r.min}~${r.max}` },
    { title: '건수', dataIndex: 'count', key: 'count', render: (v: number) => v.toLocaleString() },
    {
      title: '비중(%)', dataIndex: 'pct', key: 'pct',
      render: (v: number) => <Tag color={v > 30 ? 'red' : v > 20 ? 'orange' : 'default'}>{v.toFixed(1)}</Tag>,
    },
    { title: '평균 PD (%)', dataIndex: 'avg_pd', key: 'avg_pd', render: (v: number) => v.toFixed(3) },
  ]

  return (
    <>
      <Title level={4}>점수 분포 분석</Title>

      {/* 모델 지표 */}
      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={4}><Card size="small"><Statistic title="평균 점수" value={st.mean.toFixed(0)} /></Card></Col>
        <Col span={4}><Card size="small"><Statistic title="중앙값" value={st.median.toFixed(0)} /></Card></Col>
        <Col span={4}><Card size="small"><Statistic title="표준편차" value={st.std.toFixed(0)} /></Card></Col>
        <Col span={4}>
          <Card size="small">
            <Statistic title="Gini 계수" value={data!.gini.toFixed(4)}
              valueStyle={{ color: data!.gini >= 0.3 ? '#3f8600' : '#cf1322' }} />
          </Card>
        </Col>
        <Col span={4}>
          <Card size="small">
            <Statistic title="KS 통계량" value={data!.ks.toFixed(4)}
              valueStyle={{ color: data!.ks >= 0.2 ? '#3f8600' : '#cf1322' }} />
          </Card>
        </Col>
      </Row>

      {/* 자동심사 구간 비중 */}
      <Row gutter={16} style={{ marginBottom: 16 }}>
        {[
          { label: '자동거절 (score < 450)', value: st.auto_reject_pct, color: '#f5222d' },
          { label: '수동심사 (450~529)', value: st.manual_review_pct, color: '#faad14' },
          { label: '자동승인 (score ≥ 530)', value: st.auto_approve_pct, color: '#52c41a' },
        ].map((k) => (
          <Col key={k.label} span={8}>
            <Card size="small" style={{ textAlign: 'center', borderColor: k.color }}>
              <Text style={{ fontSize: 11, color: '#8c8c8c' }}>{k.label}</Text><br />
              <Text strong style={{ fontSize: 24, color: k.color }}>{k.value.toFixed(1)}%</Text>
            </Card>
          </Col>
        ))}
      </Row>

      {/* 히스토그램 */}
      <Card title="점수 분포 히스토그램 (50점 구간)" style={{ marginBottom: 16 }}>
        <ResponsiveContainer width="100%" height={300}>
          <BarChart data={data!.histogram} margin={{ left: 20 }}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="bin" tick={{ fontSize: 10 }} />
            <YAxis />
            <Tooltip
              formatter={(v, name) => [typeof v === 'number' ? v.toLocaleString() : v, name]}
            />
            <ReferenceLine x="450~499" stroke="#faad14" strokeDasharray="4 4" label="수동심사↑" />
            <ReferenceLine x="530~579" stroke="#52c41a" strokeDasharray="4 4" label="자동승인↑" />
            <Bar dataKey="count" name="건수">
              {data!.histogram.map((entry, idx) => (
                <Cell key={idx} fill={ZONE_COLOR[entry.zone] ?? '#1677ff'} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
        <div style={{ display: 'flex', gap: 16, marginTop: 8, justifyContent: 'center' }}>
          {Object.entries(ZONE_COLOR).map(([zone, color]) => (
            <span key={zone} style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
              <span style={{ display: 'inline-block', width: 12, height: 12, background: color, borderRadius: 2 }} />
              <Text style={{ fontSize: 12 }}>{zone}</Text>
            </span>
          ))}
        </div>
      </Card>

      {/* 등급별 */}
      <Card title="등급별 분포 상세">
        <Table
          dataSource={data!.by_grade}
          columns={gradeColumns}
          rowKey="grade"
          size="small"
          pagination={false}
        />
      </Card>
    </>
  )
}
