import { useState } from 'react'
import { Form, InputNumber, Select, Button, Card, Row, Col, Statistic, Tag, Alert, Typography, Divider } from 'antd'
import { ThunderboltOutlined } from '@ant-design/icons'
import { pocApi } from '../../api/poc'

const { Title } = Typography

interface PrescoreResult {
  shadow_mode: boolean
  score: number
  grade: string
  rate: number
  credit_limit: number
  dsr: number
  decision: string
  segment: string
  note: string
}

export default function MarketingPrescore() {
  const [form] = Form.useForm()
  const [result, setResult] = useState<PrescoreResult | null>(null)
  const [loading, setLoading] = useState(false)

  const onFinish = (values: Record<string, unknown>) => {
    setLoading(true)
    pocApi.prescore(values).then((res) => setResult(res.data)).finally(() => setLoading(false))
  }

  const decisionColor = (d: string) =>
    d === '승인' ? 'success' : d === '심사필요' ? 'warning' : 'error'

  return (
    <>
      <Title level={4}>사전심사 (Shadow Mode)</Title>
      <Alert
        message="Shadow Mode: 평가 결과가 DB에 저장되지 않습니다."
        type="info"
        showIcon
        style={{ marginBottom: 16 }}
      />
      <Row gutter={24}>
        <Col span={12}>
          <Card title="고객 정보 입력">
            <Form form={form} layout="vertical" onFinish={onFinish}>
              <Row gutter={12}>
                <Col span={12}>
                  <Form.Item name="age" label="연령" rules={[{ required: true }]}>
                    <InputNumber min={19} max={85} style={{ width: '100%' }} addonAfter="세" />
                  </Form.Item>
                </Col>
                <Col span={12}>
                  <Form.Item name="income" label="연소득" rules={[{ required: true }]}>
                    <InputNumber min={0} style={{ width: '100%' }} addonAfter="만원" formatter={(v) => `${v}`.replace(/\B(?=(\d{3})+(?!\d))/g, ',')} />
                  </Form.Item>
                </Col>
                <Col span={12}>
                  <Form.Item name="occupation" label="직업">
                    <Select options={[
                      { label: '직장인', value: '직장인' },
                      { label: '의사', value: '의사' },
                      { label: '변호사', value: '변호사' },
                      { label: '군인', value: '군인' },
                      { label: '자영업', value: '자영업' },
                      { label: '프리랜서', value: '프리랜서' },
                    ]} />
                  </Form.Item>
                </Col>
                <Col span={12}>
                  <Form.Item name="credit_score" label="CB 신용점수">
                    <InputNumber min={300} max={1000} style={{ width: '100%' }} />
                  </Form.Item>
                </Col>
                <Col span={12}>
                  <Form.Item name="existing_debt" label="기존 부채" >
                    <InputNumber min={0} style={{ width: '100%' }} addonAfter="만원" />
                  </Form.Item>
                </Col>
                <Col span={12}>
                  <Form.Item name="loan_amount" label="신청 금액" rules={[{ required: true }]}>
                    <InputNumber min={100} max={500000} style={{ width: '100%' }} addonAfter="만원" />
                  </Form.Item>
                </Col>
              </Row>
              <Button type="primary" htmlType="submit" block loading={loading} icon={<ThunderboltOutlined />}>
                사전심사 실행
              </Button>
            </Form>
          </Card>
        </Col>
        <Col span={12}>
          {result && (
            <Card title="사전심사 결과">
              <Row gutter={16}>
                <Col span={12}><Statistic title="신용점수" value={result.score} /></Col>
                <Col span={12}><Statistic title="등급" value={result.grade} /></Col>
                <Col span={12}><Statistic title="금리" value={`${result.rate}%`} /></Col>
                <Col span={12}><Statistic title="DSR" value={`${result.dsr}%`} /></Col>
                <Col span={24}><Statistic title="한도" value={`${(result.credit_limit / 10000).toLocaleString()}만원`} /></Col>
              </Row>
              <Divider />
              <div style={{ textAlign: 'center' }}>
                <Tag color={decisionColor(result.decision)} style={{ fontSize: 18, padding: '4px 16px' }}>
                  {result.decision}
                </Tag>
                {result.segment !== '일반' && (
                  <Tag color="blue" style={{ fontSize: 14, padding: '4px 12px' }}>
                    {result.segment}
                  </Tag>
                )}
              </div>
              <Divider />
              <Alert message={result.note} type="warning" showIcon />
            </Card>
          )}
        </Col>
      </Row>
    </>
  )
}
