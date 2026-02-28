import { useState } from 'react'
import {
  Card, Form, Slider, InputNumber, Button, Row, Col, Statistic,
  Typography, Alert, Divider, Select, Tag,
} from 'antd'
import { CalculatorOutlined } from '@ant-design/icons'
import client from '../../api/client'

const { Title, Text } = Typography

interface SimResult {
  base_rate: number
  spread: number
  final_rate: number
  raroc: number
  el: number
  rwa: number
  breakeven_rate: number
  recommendation: string
}

export default function ProductRateSimulation() {
  const [form] = Form.useForm()
  const [result, setResult] = useState<SimResult | null>(null)
  const [loading, setLoading] = useState(false)

  const run = async () => {
    const vals = form.getFieldsValue()
    setLoading(true)
    try {
      const res = await client.post('/poc/rate-simulation', vals)
      setResult(res.data)
    } catch {
      // fallback mock
      const pd = (vals.credit_score ? Math.max(0.005, (900 - vals.credit_score) * 0.0003) : 0.05)
      const base = vals.base_rate ?? 3.5
      const spread = pd * 100 * 2.5 + (vals.ltv ?? 0) * 0.01
      const final_rate = +(base + spread).toFixed(2)
      setResult({
        base_rate: base, spread: +spread.toFixed(2), final_rate,
        raroc: +(15 - pd * 100 * 2).toFixed(1),
        el: +(vals.loan_amount * pd * 0.45 / 10000).toFixed(0) * 10000,
        rwa: +(vals.loan_amount * pd * 12.5 / 10000).toFixed(0) * 10000,
        breakeven_rate: +(base + pd * 100 * 1.8).toFixed(2),
        recommendation: final_rate >= 5.0 && final_rate <= 18.0 ? '승인 가능' : '한도 외 검토 필요',
      })
    } finally {
      setLoading(false)
    }
  }

  return (
    <>
      <Title level={4}>금리 정책 시뮬레이션</Title>
      <Row gutter={24}>
        <Col span={10}>
          <Card title={<><CalculatorOutlined /> 입력 파라미터</>}>
            <Form form={form} layout="vertical" initialValues={{
              base_rate: 3.5, credit_score: 650, ltv: 0, loan_amount: 30000000, product: '신용대출', segment: 'SEG-GEN',
            }}>
              <Form.Item name="product" label="상품 유형">
                <Select>
                  <Select.Option value="신용대출">신용대출</Select.Option>
                  <Select.Option value="주담대">주택담보대출</Select.Option>
                  <Select.Option value="소액론">소액론</Select.Option>
                </Select>
              </Form.Item>
              <Form.Item name="segment" label="고객 세그먼트">
                <Select>
                  {['SEG-GEN', 'SEG-DR', 'SEG-JD', 'SEG-YTH', 'SEG-MIL', 'SEG-ART'].map((s) => (
                    <Select.Option key={s} value={s}>{s}</Select.Option>
                  ))}
                </Select>
              </Form.Item>
              <Form.Item name="credit_score" label={<>신용점수 <Text type="secondary" style={{ fontSize: 11 }}>(300~900)</Text></>}>
                <Slider min={300} max={900} marks={{ 450: '자동거절', 530: '자동승인' }} />
              </Form.Item>
              <Form.Item name="base_rate" label="기준금리 (%)">
                <InputNumber min={0} max={10} step={0.1} style={{ width: '100%' }} />
              </Form.Item>
              <Form.Item name="loan_amount" label="대출 금액 (원)">
                <InputNumber min={500000} max={800000000} step={1000000} style={{ width: '100%' }}
                  formatter={(v) => `${v}`.replace(/\B(?=(\d{3})+(?!\d))/g, ',')} />
              </Form.Item>
              <Form.Item name="ltv" label="LTV (%)">
                <Slider min={0} max={100} marks={{ 40: '투기', 60: '조정', 70: '일반' }} />
              </Form.Item>
              <Button type="primary" block loading={loading} onClick={run}>시뮬레이션 실행</Button>
            </Form>
          </Card>
        </Col>
        <Col span={14}>
          {!result ? (
            <Card style={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <Text type="secondary">파라미터를 입력하고 시뮬레이션을 실행하세요.</Text>
            </Card>
          ) : (
            <Card title="시뮬레이션 결과">
              <Alert
                message={result.recommendation}
                type={result.recommendation.includes('승인') ? 'success' : 'warning'}
                showIcon
                style={{ marginBottom: 16 }}
              />
              <Row gutter={16}>
                <Col span={8}>
                  <Statistic title="기준금리" value={result.base_rate} suffix="%" precision={2} />
                </Col>
                <Col span={8}>
                  <Statistic title="가산금리" value={result.spread} suffix="%" precision={2}
                    valueStyle={{ color: '#faad14' }} />
                </Col>
                <Col span={8}>
                  <Statistic title="최종 적용금리" value={result.final_rate} suffix="%" precision={2}
                    valueStyle={{ color: result.final_rate > 15 ? '#f5222d' : '#3f8600', fontSize: 28 }} />
                </Col>
              </Row>
              <Divider />
              <Row gutter={16}>
                <Col span={8}>
                  <Statistic title="RAROC" value={result.raroc} suffix="%" precision={1}
                    valueStyle={{ color: result.raroc >= 12 ? '#3f8600' : '#f5222d' }} />
                </Col>
                <Col span={8}>
                  <Statistic title="기대손실(EL)" value={(result.el / 10000).toLocaleString()} suffix="만원" />
                </Col>
                <Col span={8}>
                  <Statistic title="위험가중자산(RWA)" value={(result.rwa / 100000000).toFixed(1)} suffix="억원" />
                </Col>
              </Row>
              <Divider />
              <Row>
                <Col span={12}>
                  <Text type="secondary">손익분기 금리 </Text>
                  <Tag color={result.final_rate >= result.breakeven_rate ? 'green' : 'red'}>
                    {result.breakeven_rate}%
                  </Tag>
                  <br />
                  <Text type="secondary" style={{ fontSize: 11 }}>
                    최종금리 {result.final_rate >= result.breakeven_rate ? '≥' : '<'} 손익분기 → {result.final_rate >= result.breakeven_rate ? '수익' : '손실'} 구간
                  </Text>
                </Col>
                <Col span={12}>
                  <Text type="secondary">법정 최고금리 한도 </Text>
                  <Tag color={result.final_rate <= 20 ? 'green' : 'red'}>20.0%</Tag>
                  <br />
                  <Text type="secondary" style={{ fontSize: 11 }}>
                    현재 {result.final_rate}% → {result.final_rate <= 20 ? '적법' : '한도 초과'}
                  </Text>
                </Col>
              </Row>
            </Card>
          )}
        </Col>
      </Row>
    </>
  )
}
