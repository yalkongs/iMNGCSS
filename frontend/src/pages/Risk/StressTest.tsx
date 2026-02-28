import { useState } from 'react'
import { Card, Form, Select, Button, Row, Col, Statistic, Alert, Typography, Divider } from 'antd'
import { ThunderboltOutlined } from '@ant-design/icons'
import { pocApi } from '../../api/poc'

const { Title, Text } = Typography

interface StressResult {
  scenario: string
  impact: {
    pd_change: number
    stressed_pd: number
    el_change: number
    stressed_el: number
    rwa_increase_pct: number
    capital_adequacy_ratio: number
    tier1_ratio: number
  }
  portfolio_impact: {
    approval_rate_change: number
    avg_rate_change: number
    affected_accounts: number
  }
}

const SCENARIOS = [
  { value: 'base', label: '기준 시나리오 (Base)' },
  { value: 'rate_shock', label: '금리 충격 (+150bp)' },
  { value: 'real_estate', label: '부동산 하락 (-20%)' },
  { value: 'recession', label: '경기침체 (복합 충격)' },
]

export default function RiskStressTest() {
  const [form] = Form.useForm()
  const [result, setResult] = useState<StressResult | null>(null)
  const [loading, setLoading] = useState(false)

  const onFinish = (values: Record<string, unknown>) => {
    setLoading(true)
    pocApi.stressTest(values).then((res) => setResult(res.data)).finally(() => setLoading(false))
  }

  const pctColor = (v: number) => v > 0 ? '#f5222d' : '#3f8600'

  return (
    <>
      <Title level={4}>스트레스 테스트</Title>
      <Row gutter={24}>
        <Col span={8}>
          <Card title="시나리오 선택">
            <Form form={form} layout="vertical" onFinish={onFinish}>
              <Form.Item name="scenario" label="시나리오" rules={[{ required: true }]} initialValue="base">
                <Select options={SCENARIOS} />
              </Form.Item>
              <Alert message="시뮬레이션 결과는 내부 분석용이며 실제 포트폴리오에 영향을 미치지 않습니다." type="info" showIcon style={{ marginBottom: 16 }} />
              <Button type="primary" htmlType="submit" block loading={loading} icon={<ThunderboltOutlined />}>
                스트레스 테스트 실행
              </Button>
            </Form>
          </Card>
        </Col>
        <Col span={16}>
          {result && (
            <Card title={`결과: ${SCENARIOS.find((s) => s.value === result.scenario)?.label}`}>
              <Title level={5}>신용 위험 지표</Title>
              <Row gutter={16}>
                <Col span={8}><Statistic title="PD 변화" value={`+${(result.impact.pd_change * 100).toFixed(2)}%p`} valueStyle={{ color: pctColor(result.impact.pd_change) }} /></Col>
                <Col span={8}><Statistic title="스트레스 PD" value={`${(result.impact.stressed_pd * 100).toFixed(2)}%`} /></Col>
                <Col span={8}><Statistic title="EL 변화" value={`+${(result.impact.el_change * 100).toFixed(2)}%p`} valueStyle={{ color: pctColor(result.impact.el_change) }} /></Col>
              </Row>
              <Divider />
              <Title level={5}>건전성 지표</Title>
              <Row gutter={16}>
                <Col span={8}><Statistic title="RWA 증가" value={`+${result.impact.rwa_increase_pct}%`} valueStyle={{ color: pctColor(result.impact.rwa_increase_pct) }} /></Col>
                <Col span={8}><Statistic title="BIS 비율" value={`${result.impact.capital_adequacy_ratio.toFixed(1)}%`} /></Col>
                <Col span={8}><Statistic title="Tier1 비율" value={`${result.impact.tier1_ratio.toFixed(1)}%`} /></Col>
              </Row>
              <Divider />
              <Title level={5}>포트폴리오 영향</Title>
              <Row gutter={16}>
                <Col span={8}><Statistic title="승인율 변화" value={`${result.portfolio_impact.approval_rate_change}%p`} valueStyle={{ color: pctColor(-result.portfolio_impact.approval_rate_change) }} /></Col>
                <Col span={8}><Statistic title="평균금리 변화" value={`+${result.portfolio_impact.avg_rate_change}%p`} /></Col>
                <Col span={8}><Statistic title="영향 계좌" value={result.portfolio_impact.affected_accounts.toLocaleString()} suffix="건" /></Col>
              </Row>
              <Divider />
              <Text type="secondary">BIS 규정: BIS비율 ≥ 10.5%, Tier1 ≥ 8.5% 유지 권고</Text>
            </Card>
          )}
        </Col>
      </Row>
    </>
  )
}
