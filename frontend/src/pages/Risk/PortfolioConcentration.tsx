import { useEffect, useState } from 'react'
import { Card, Row, Col, Table, Tag, Typography, Spin, Alert, Progress } from 'antd'
import {
  PieChart, Pie, Cell, Tooltip, ResponsiveContainer,
  BarChart, Bar, XAxis, YAxis, CartesianGrid,
} from 'recharts'
import client from '../../api/client'

const { Title, Text } = Typography

const COLORS = ['#1677ff', '#52c41a', '#faad14', '#f5222d', '#722ed1', '#13c2c2', '#eb2f96']

interface ConcentrationData {
  summary: { hhi: number; top3_share: number; alert_level: string; alert_message: string }
  by_product: { name: string; count: number; share: number; avg_score: number; avg_rate: number; total_amount: number }[]
  by_segment: { name: string; count: number; share: number; avg_score: number; approval_rate: number }[]
  by_region: { name: string; count: number; share: number; avg_amount: number }[]
  by_income: { name: string; count: number; share: number; avg_dsr: number; default_rate: number }[]
}

export default function RiskPortfolioConcentration() {
  const [data, setData] = useState<ConcentrationData | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    client.get('/poc/portfolio-concentration').then((r) => setData(r.data)).finally(() => setLoading(false))
  }, [])

  if (loading) return <Spin size="large" style={{ display: 'block', marginTop: 80 }} />

  const s = data!.summary
  const alertType = s.alert_level === 'HIGH' ? 'error' : s.alert_level === 'MEDIUM' ? 'warning' : 'success'

  return (
    <>
      <Title level={4}>포트폴리오 집중도 분석</Title>

      <Alert
        type={alertType}
        message={`집중도 수준: ${s.alert_level}`}
        description={s.alert_message}
        showIcon
        style={{ marginBottom: 16 }}
      />

      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={6}>
          <Card size="small" style={{ textAlign: 'center' }}>
            <Text type="secondary" style={{ fontSize: 11 }}>HHI (허핀달-허쉬만 지수)</Text><br />
            <Text strong style={{ fontSize: 24, color: s.hhi > 2500 ? '#f5222d' : s.hhi > 1500 ? '#faad14' : '#52c41a' }}>
              {s.hhi.toFixed(0)}
            </Text><br />
            <Text type="secondary" style={{ fontSize: 10 }}>{"<1500:분산 / 1500~2500:보통 / >2500:집중"}</Text>
          </Card>
        </Col>
        <Col span={6}>
          <Card size="small" style={{ textAlign: 'center' }}>
            <Text type="secondary" style={{ fontSize: 11 }}>상위 3개 비중 합계</Text><br />
            <Text strong style={{ fontSize: 24, color: s.top3_share > 70 ? '#f5222d' : '#52c41a' }}>
              {s.top3_share.toFixed(1)}%
            </Text>
          </Card>
        </Col>
      </Row>

      {/* 상품별 */}
      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={10}>
          <Card title="상품별 포트폴리오 구성">
            <ResponsiveContainer width="100%" height={240}>
              <PieChart>
                <Pie data={data!.by_product} dataKey="share" nameKey="name" cx="50%" cy="50%" outerRadius={90}
                  label={({ name, value }: { name?: string; value?: number }) => `${name ?? ''} ${(value ?? 0).toFixed(0)}%`}>
                  {data!.by_product.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
                </Pie>
                <Tooltip formatter={(v) => typeof v === 'number' ? `${v.toFixed(1)}%` : v} />
              </PieChart>
            </ResponsiveContainer>
          </Card>
        </Col>
        <Col span={14}>
          <Card title="상품별 상세">
            <Table
              dataSource={data!.by_product}
              rowKey="name"
              size="small"
              pagination={false}
              columns={[
                { title: '상품', dataIndex: 'name', key: 'name' },
                { title: '건수', dataIndex: 'count', key: 'count', render: (v: number) => v.toLocaleString() },
                {
                  title: '비중', dataIndex: 'share', key: 'share',
                  render: (v: number) => <Progress percent={v} size="small" />,
                },
                { title: '평균점수', dataIndex: 'avg_score', key: 'avg_score' },
                { title: '평균금리', dataIndex: 'avg_rate', key: 'avg_rate', render: (v: number) => `${v.toFixed(2)}%` },
              ]}
            />
          </Card>
        </Col>
      </Row>

      {/* 지역별 */}
      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={24}>
          <Card title="지역별 집중도">
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={data!.by_region}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="name" tick={{ fontSize: 11 }} />
                <YAxis unit="%" />
                <Tooltip formatter={(v) => typeof v === 'number' ? `${v.toFixed(1)}%` : v} />
                <Bar dataKey="share" name="비중" fill="#1677ff" />
              </BarChart>
            </ResponsiveContainer>
          </Card>
        </Col>
      </Row>

      {/* 소득구간별 */}
      <Row gutter={16}>
        <Col span={12}>
          <Card title="세그먼트별 분포">
            <Table
              dataSource={data!.by_segment}
              rowKey="name"
              size="small"
              pagination={false}
              columns={[
                { title: '세그먼트', dataIndex: 'name', key: 'name' },
                { title: '건수', dataIndex: 'count', key: 'count' },
                { title: '비중(%)', dataIndex: 'share', key: 'share', render: (v: number) => v.toFixed(1) },
                { title: '평균점수', dataIndex: 'avg_score', key: 'avg_score' },
                { title: '승인율(%)', dataIndex: 'approval_rate', key: 'approval_rate',
                  render: (v: number) => <Tag color={v >= 70 ? 'green' : 'orange'}>{v.toFixed(1)}</Tag> },
              ]}
            />
          </Card>
        </Col>
        <Col span={12}>
          <Card title="소득구간별 리스크 분포">
            <Table
              dataSource={data!.by_income}
              rowKey="name"
              size="small"
              pagination={false}
              columns={[
                { title: '소득구간', dataIndex: 'name', key: 'name' },
                { title: '건수', dataIndex: 'count', key: 'count' },
                { title: '비중(%)', dataIndex: 'share', key: 'share', render: (v: number) => v.toFixed(1) },
                { title: '평균 DSR(%)', dataIndex: 'avg_dsr', key: 'avg_dsr', render: (v: number) => <Tag color={v > 40 ? 'red' : 'green'}>{v.toFixed(1)}</Tag> },
                { title: '부도율(%)', dataIndex: 'default_rate', key: 'default_rate', render: (v: number) => v.toFixed(2) },
              ]}
            />
          </Card>
        </Col>
      </Row>
    </>
  )
}
