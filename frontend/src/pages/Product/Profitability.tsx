import { useEffect, useState } from 'react'
import { Card, Row, Col, Table, Tag, Typography, Spin, Progress } from 'antd'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  ScatterChart, Scatter, ZAxis, Legend,
} from 'recharts'
import client from '../../api/client'

const { Title } = Typography

interface ProfitData {
  summary: {
    avg_raroc: number; avg_clv: number; avg_nim: number
    portfolio_return: number; cost_of_risk: number
  }
  by_grade: {
    grade: string; raroc: number; avg_clv: number; nim: number; count: number; avg_pd: number
  }[]
  by_product: {
    product: string; raroc: number; avg_clv: number; total_el: number; rwa: number
  }[]
  scatter: { name: string; pd: number; raroc: number; clv: number; grade: string }[]
}

const GRADE_COLOR: Record<string, string> = {
  'AAA': '#003a8c', 'AA': '#0050b3', 'A': '#1677ff',
  'B': '#52c41a', 'C': '#faad14', 'D': '#f5222d',
}

export default function ProductProfitability() {
  const [data, setData] = useState<ProfitData | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    client.get('/poc/profitability').then((r) => setData(r.data)).finally(() => setLoading(false))
  }, [])

  if (loading) return <Spin size="large" style={{ display: 'block', marginTop: 80 }} />

  const gradeColumns = [
    { title: '신용등급', dataIndex: 'grade', key: 'grade', render: (v: string) => <Tag color={GRADE_COLOR[v] ?? 'default'}>{v}</Tag> },
    { title: '건수', dataIndex: 'count', key: 'count', render: (v: number) => v.toLocaleString() },
    { title: '평균 PD (%)', dataIndex: 'avg_pd', key: 'avg_pd', render: (v: number) => v.toFixed(2) },
    {
      title: 'RAROC (%)', dataIndex: 'raroc', key: 'raroc',
      render: (v: number) => (
        <span style={{ color: v >= 12 ? '#3f8600' : v >= 8 ? '#d48806' : '#cf1322' }}>{v.toFixed(1)}</span>
      ),
    },
    { title: '평균 CLV (만원)', dataIndex: 'avg_clv', key: 'avg_clv', render: (v: number) => (v / 10000).toLocaleString() },
    {
      title: 'NIM (%)', dataIndex: 'nim', key: 'nim',
      render: (v: number) => <Progress percent={v * 10} size="small" format={() => `${v.toFixed(2)}%`} />,
    },
  ]

  const productColumns = [
    { title: '상품', dataIndex: 'product', key: 'product' },
    {
      title: 'RAROC (%)', dataIndex: 'raroc', key: 'raroc',
      render: (v: number) => <Tag color={v >= 12 ? 'green' : v >= 8 ? 'orange' : 'red'}>{v.toFixed(1)}%</Tag>,
    },
    { title: '평균 CLV (만원)', dataIndex: 'avg_clv', key: 'avg_clv', render: (v: number) => (v / 10000).toLocaleString() },
    { title: '총 기대손실 (억원)', dataIndex: 'total_el', key: 'total_el', render: (v: number) => (v / 100000000).toFixed(1) },
    { title: 'RWA (억원)', dataIndex: 'rwa', key: 'rwa', render: (v: number) => (v / 100000000).toFixed(1) },
  ]

  const s = data!.summary
  return (
    <>
      <Title level={4}>고객 수익성 분석 (RAROC / CLV)</Title>

      <Row gutter={16} style={{ marginBottom: 16 }}>
        {[
          { label: '포트폴리오 평균 RAROC', value: s.avg_raroc.toFixed(1), unit: '%', ok: s.avg_raroc >= 12 },
          { label: '평균 고객 생애가치(CLV)', value: (s.avg_clv / 10000).toLocaleString(), unit: '만원', ok: true },
          { label: '순이자마진(NIM)', value: s.avg_nim.toFixed(2), unit: '%', ok: s.avg_nim >= 1.5 },
          { label: '포트폴리오 수익률', value: s.portfolio_return.toFixed(2), unit: '%', ok: s.portfolio_return >= 3 },
          { label: '리스크 비용', value: s.cost_of_risk.toFixed(2), unit: '%', ok: s.cost_of_risk <= 1.5 },
        ].map((k) => (
          <Col key={k.label} span={4}>
            <Card size="small" style={{ textAlign: 'center', borderColor: k.ok ? '#b7eb8f' : '#ffccc7' }}>
              <div style={{ fontSize: 11, color: '#8c8c8c' }}>{k.label}</div>
              <div style={{ fontSize: 22, fontWeight: 700, color: k.ok ? '#3f8600' : '#cf1322' }}>
                {k.value}{k.unit}
              </div>
            </Card>
          </Col>
        ))}
      </Row>

      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={14}>
          <Card title="등급별 RAROC">
            <ResponsiveContainer width="100%" height={240}>
              <BarChart data={data!.by_grade}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="grade" />
                <YAxis unit="%" />
                <Tooltip formatter={(v) => typeof v === 'number' ? `${v.toFixed(1)}%` : v} />
                <Bar dataKey="raroc" name="RAROC" fill="#1677ff" />
              </BarChart>
            </ResponsiveContainer>
          </Card>
        </Col>
        <Col span={10}>
          <Card title="PD vs RAROC 산점도">
            <ResponsiveContainer width="100%" height={240}>
              <ScatterChart>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="pd" name="PD" unit="%" type="number" label={{ value: 'PD(%)', position: 'bottom', offset: 0 }} />
                <YAxis dataKey="raroc" name="RAROC" unit="%" label={{ value: 'RAROC(%)', angle: -90, position: 'insideLeft' }} />
                <ZAxis dataKey="clv" range={[40, 300]} />
                <Tooltip cursor={{ strokeDasharray: '3 3' }} formatter={(v) => typeof v === 'number' ? v.toFixed(2) : v} />
                <Legend />
                <Scatter name="고객" data={data!.scatter} fill="#1677ff" opacity={0.6} />
              </ScatterChart>
            </ResponsiveContainer>
          </Card>
        </Col>
      </Row>

      <Row gutter={16}>
        <Col span={12}>
          <Card title="신용등급별 수익성 상세">
            <Table dataSource={data!.by_grade} columns={gradeColumns} rowKey="grade" size="small" pagination={false} />
          </Card>
        </Col>
        <Col span={12}>
          <Card title="상품별 수익성 상세">
            <Table dataSource={data!.by_product} columns={productColumns} rowKey="product" size="small" pagination={false} />
          </Card>
        </Col>
      </Row>
    </>
  )
}
