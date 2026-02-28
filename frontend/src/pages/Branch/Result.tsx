import { useState } from 'react'
import { Card, Input, Button, Row, Col, Statistic, Tag, Table, Typography, Space, Divider } from 'antd'
import { SearchOutlined } from '@ant-design/icons'
import { pocApi } from '../../api/poc'

const { Title, Text } = Typography

interface AppDetail {
  id: string
  customer_name: string
  score: number
  grade: string
  rate: number
  dsr: number
  ltv: number
  status: string
  eq_grade: string
  segment: string
  shap_top5: { feature: string; contribution: number }[]
  applied_at: string
}

export default function BranchResult() {
  const [appId, setAppId] = useState('')
  const [detail, setDetail] = useState<AppDetail | null>(null)
  const [loading, setLoading] = useState(false)

  const search = () => {
    if (!appId) return
    setLoading(true)
    pocApi.applications.get(appId).then((res) => setDetail(res.data)).finally(() => setLoading(false))
  }

  const shapColumns = [
    { title: '변수', dataIndex: 'feature', key: 'feature' },
    {
      title: '기여도', dataIndex: 'contribution', key: 'contribution',
      render: (v: number) => (
        <Tag color={v > 0 ? 'green' : 'red'}>{v > 0 ? '+' : ''}{v.toFixed(1)}</Tag>
      ),
    },
  ]

  return (
    <>
      <Title level={4}>심사 결과 조회</Title>
      <Card style={{ marginBottom: 24 }}>
        <Space>
          <Input
            placeholder="신청 ID (예: APP-2025001)"
            value={appId}
            onChange={(e) => setAppId(e.target.value)}
            onPressEnter={search}
            style={{ width: 280 }}
          />
          <Button type="primary" icon={<SearchOutlined />} onClick={search} loading={loading}>
            조회
          </Button>
        </Space>
        <Text type="secondary" style={{ marginLeft: 12 }}>
          예시: APP-2025001 ~ APP-2025099
        </Text>
      </Card>

      {detail && (
        <Card title={`신청 상세 — ${detail.id}`}>
          <Row gutter={24}>
            <Col span={4}><Statistic title="신용점수" value={detail.score} /></Col>
            <Col span={4}><Statistic title="등급" value={detail.grade} /></Col>
            <Col span={4}><Statistic title="금리" value={`${detail.rate}%`} /></Col>
            <Col span={4}><Statistic title="DSR" value={`${detail.dsr}%`} /></Col>
            <Col span={4}><Statistic title="LTV" value={`${detail.ltv}%`} /></Col>
            <Col span={4}>
              <Statistic title="결과" valueRender={() => (
                <Tag color={detail.status === '승인' ? 'success' : detail.status === '심사중' ? 'processing' : 'error'} style={{ fontSize: 16 }}>
                  {detail.status}
                </Tag>
              )} />
            </Col>
          </Row>
          <Divider />
          <Row gutter={24}>
            <Col span={12}>
              <Text strong>EQ Grade:</Text> {detail.eq_grade} &nbsp;
              <Text strong>세그먼트:</Text> {detail.segment || '일반'}
            </Col>
            <Col span={12}>
              <Text strong>고객명:</Text> {detail.customer_name} &nbsp;
              <Text strong>신청일:</Text> {detail.applied_at}
            </Col>
          </Row>
          <Divider />
          <Title level={5}>주요 기여 변수 (SHAP Top 5)</Title>
          <Table
            dataSource={detail.shap_top5}
            columns={shapColumns}
            rowKey="feature"
            pagination={false}
            size="small"
          />
        </Card>
      )}
    </>
  )
}
