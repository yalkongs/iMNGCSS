import { useEffect, useState } from 'react'
import { Card, Row, Col, Table, Tag, Typography, Spin, Progress } from 'antd'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  LineChart, Line, Legend,
} from 'recharts'
import client from '../../api/client'

const { Title, Text } = Typography

interface CampaignData {
  overview: {
    total_sent: number
    total_applied: number
    total_approved: number
    overall_conversion: number
    total_disbursed: number
    avg_loan_amount: number
  }
  by_channel: {
    channel: string
    sent: number
    applied: number
    approved: number
    conversion_rate: number
    approval_rate: number
    avg_loan_amount: number
    total_disbursed: number
  }[]
  monthly: { month: string; sent: number; applied: number; approved: number }[]
  segment_performance: {
    segment: string
    count: number
    conversion_rate: number
    avg_score: number
    avg_rate: number
  }[]
}

export default function MarketingCampaign() {
  const [data, setData] = useState<CampaignData | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    client.get('/poc/campaign').then((r) => setData(r.data)).finally(() => setLoading(false))
  }, [])

  if (loading) return <Spin size="large" style={{ display: 'block', marginTop: 80 }} />

  const channelColumns = [
    { title: '채널', dataIndex: 'channel', key: 'channel' },
    { title: '발송', dataIndex: 'sent', key: 'sent', render: (v: number) => v.toLocaleString() },
    { title: '신청', dataIndex: 'applied', key: 'applied', render: (v: number) => v.toLocaleString() },
    { title: '승인', dataIndex: 'approved', key: 'approved', render: (v: number) => v.toLocaleString() },
    {
      title: '전환율', dataIndex: 'conversion_rate', key: 'conversion_rate',
      render: (v: number) => <Progress percent={v} size="small" style={{ minWidth: 80 }} />,
    },
    {
      title: '승인율', dataIndex: 'approval_rate', key: 'approval_rate',
      render: (v: number) => <Tag color={v >= 70 ? 'green' : v >= 50 ? 'orange' : 'red'}>{v.toFixed(1)}%</Tag>,
    },
    {
      title: '평균 대출액', dataIndex: 'avg_loan_amount', key: 'avg_loan_amount',
      render: (v: number) => `${(v / 10000).toLocaleString()}만원`,
    },
    {
      title: '총 취급액', dataIndex: 'total_disbursed', key: 'total_disbursed',
      render: (v: number) => `${(v / 100000000).toFixed(1)}억`,
    },
  ]

  const segColumns = [
    { title: '세그먼트', dataIndex: 'segment', key: 'segment' },
    { title: '건수', dataIndex: 'count', key: 'count', render: (v: number) => v.toLocaleString() },
    {
      title: '전환율', dataIndex: 'conversion_rate', key: 'conversion_rate',
      render: (v: number) => <Tag color={v >= 15 ? 'green' : v >= 8 ? 'orange' : 'red'}>{v.toFixed(1)}%</Tag>,
    },
    { title: '평균점수', dataIndex: 'avg_score', key: 'avg_score' },
    { title: '평균금리', dataIndex: 'avg_rate', key: 'avg_rate', render: (v: number) => `${v.toFixed(2)}%` },
  ]

  const ov = data!.overview
  return (
    <>
      <Title level={4}>캠페인 분석</Title>

      {/* KPI */}
      <Row gutter={16} style={{ marginBottom: 16 }}>
        {[
          { label: '총 발송', value: ov.total_sent.toLocaleString(), unit: '건' },
          { label: '신청 접수', value: ov.total_applied.toLocaleString(), unit: '건' },
          { label: '최종 승인', value: ov.total_approved.toLocaleString(), unit: '건' },
          { label: '전환율', value: ov.overall_conversion.toFixed(1), unit: '%' },
          { label: '총 취급액', value: (ov.total_disbursed / 100000000).toFixed(0), unit: '억원' },
        ].map((k) => (
          <Col key={k.label} span={4}>
            <Card size="small" style={{ textAlign: 'center' }}>
              <Text type="secondary" style={{ fontSize: 11 }}>{k.label}</Text><br />
              <Text strong style={{ fontSize: 20 }}>{k.value}</Text>
              <Text type="secondary"> {k.unit}</Text>
            </Card>
          </Col>
        ))}
      </Row>

      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={14}>
          <Card title="월별 발송·신청·승인 추이">
            <ResponsiveContainer width="100%" height={240}>
              <LineChart data={data!.monthly}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="month" tick={{ fontSize: 11 }} />
                <YAxis />
                <Tooltip formatter={(v) => typeof v === 'number' ? v.toLocaleString() : v} />
                <Legend />
                <Line type="monotone" dataKey="sent" name="발송" stroke="#1677ff" dot={false} />
                <Line type="monotone" dataKey="applied" name="신청" stroke="#52c41a" dot={false} />
                <Line type="monotone" dataKey="approved" name="승인" stroke="#faad14" dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </Card>
        </Col>
        <Col span={10}>
          <Card title="채널별 전환율">
            <ResponsiveContainer width="100%" height={240}>
              <BarChart data={data!.by_channel} layout="vertical">
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis type="number" unit="%" />
                <YAxis type="category" dataKey="channel" width={60} tick={{ fontSize: 11 }} />
                <Tooltip formatter={(v) => typeof v === 'number' ? `${v.toFixed(1)}%` : v} />
                <Bar dataKey="conversion_rate" name="전환율" fill="#1677ff" />
              </BarChart>
            </ResponsiveContainer>
          </Card>
        </Col>
      </Row>

      <Row gutter={16}>
        <Col span={24}>
          <Card title="채널별 성과 상세">
            <Table
              dataSource={data!.by_channel}
              columns={channelColumns}
              rowKey="channel"
              size="small"
              pagination={false}
            />
          </Card>
        </Col>
      </Row>

      <Row gutter={16} style={{ marginTop: 16 }}>
        <Col span={24}>
          <Card title="세그먼트별 캠페인 성과">
            <Table
              dataSource={data!.segment_performance}
              columns={segColumns}
              rowKey="segment"
              size="small"
              pagination={false}
            />
          </Card>
        </Col>
      </Row>
    </>
  )
}
