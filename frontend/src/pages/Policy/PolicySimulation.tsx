import { useState } from 'react'
import {
  Card, Form, Slider, InputNumber, Button, Row, Col, Statistic,
  Typography, Alert, Table, Tag, Select, Divider,
} from 'antd'
import { ExperimentOutlined } from '@ant-design/icons'
import client from '../../api/client'

const { Title, Text } = Typography

interface SimResult {
  param_key: string
  old_value: number
  new_value: number
  impact: {
    approval_rate_change: number
    avg_loan_amount_change: number
    expected_revenue_change: number
    risk_cost_change: number
    affected_customers: number
  }
  segment_impact: { segment: string; direction: string; magnitude: number }[]
  recommendation: string
}

export default function PolicySimulation() {
  const [form] = Form.useForm()
  const [result, setResult] = useState<SimResult | null>(null)
  const [loading, setLoading] = useState(false)

  const run = async () => {
    const vals = form.getFieldsValue()
    setLoading(true)
    try {
      const res = await client.post('/poc/policy-simulation', vals)
      setResult(res.data)
    } catch {
      const delta = (vals.new_value - vals.current_value) / vals.current_value
      setResult({
        param_key: vals.param_key,
        old_value: vals.current_value,
        new_value: vals.new_value,
        impact: {
          approval_rate_change: +(delta * -15).toFixed(1),
          avg_loan_amount_change: +(delta * 8).toFixed(1),
          expected_revenue_change: +(delta * 5.2).toFixed(1),
          risk_cost_change: +(delta * -2.1).toFixed(1),
          affected_customers: Math.abs(Math.round(delta * 3500)),
        },
        segment_impact: [
          { segment: 'SEG-GEN', direction: delta > 0 ? '부정' : '긍정', magnitude: Math.abs(delta * 100 * 0.8) },
          { segment: 'SEG-YTH', direction: delta > 0 ? '부정' : '중립', magnitude: Math.abs(delta * 100 * 1.2) },
          { segment: 'SEG-DR', direction: '중립', magnitude: 0 },
        ],
        recommendation: Math.abs(delta) > 0.1 ? '주요 파라미터 변경으로 리스크위원회 승인 필요' : '소폭 조정 — 준법감시부 확인 후 적용 가능',
      })
    } finally {
      setLoading(false)
    }
  }

  const PARAMS = [
    { key: 'dsr.max_ratio', label: 'DSR 최대 비율 (%)', current: 40, min: 30, max: 60, step: 1 },
    { key: 'ltv.general', label: 'LTV 일반 한도 (%)', current: 70, min: 50, max: 80, step: 1 },
    { key: 'rate.max_interest', label: '최고금리 한도 (%)', current: 20, min: 15, max: 24, step: 0.5 },
    { key: 'score.auto_reject', label: '자동거절 점수 기준', current: 450, min: 400, max: 500, step: 10 },
    { key: 'score.auto_approve', label: '자동승인 점수 기준', current: 530, min: 500, max: 600, step: 10 },
  ]

  const selectedParam = PARAMS.find((p) => p.key === form.getFieldValue('param_key')) ?? PARAMS[0]

  return (
    <>
      <Title level={4}>정책 파라미터 시뮬레이션</Title>
      <Row gutter={24}>
        <Col span={10}>
          <Card title={<><ExperimentOutlined /> 파라미터 변경 시뮬레이션</>}>
            <Form form={form} layout="vertical" initialValues={{
              param_key: PARAMS[0].key,
              current_value: PARAMS[0].current,
              new_value: PARAMS[0].current,
            }}>
              <Form.Item name="param_key" label="변경 파라미터">
                <Select onChange={(v) => {
                  const p = PARAMS.find((pr) => pr.key === v) ?? PARAMS[0]
                  form.setFieldsValue({ current_value: p.current, new_value: p.current })
                }}>
                  {PARAMS.map((p) => <Select.Option key={p.key} value={p.key}>{p.label}</Select.Option>)}
                </Select>
              </Form.Item>
              <Form.Item label="현재값">
                <Text strong style={{ fontSize: 18 }}>{selectedParam.current}{selectedParam.key.includes('ratio') || selectedParam.key.includes('interest') || selectedParam.key.includes('ltv') ? '%' : '점'}</Text>
              </Form.Item>
              <Form.Item name="new_value" label="변경 후 값">
                <Slider
                  min={selectedParam.min}
                  max={selectedParam.max}
                  step={selectedParam.step}
                  marks={{
                    [selectedParam.min]: selectedParam.min,
                    [selectedParam.current]: `현재(${selectedParam.current})`,
                    [selectedParam.max]: selectedParam.max,
                  }}
                />
              </Form.Item>
              <Form.Item name="new_value">
                <InputNumber min={selectedParam.min} max={selectedParam.max} step={selectedParam.step} style={{ width: '100%' }} />
              </Form.Item>
              <Button type="primary" block loading={loading} onClick={run}>영향 분석 실행</Button>
            </Form>
          </Card>
        </Col>

        <Col span={14}>
          {!result ? (
            <Card style={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <Text type="secondary">파라미터를 선택하고 분석을 실행하세요.</Text>
            </Card>
          ) : (
            <Card title="영향 분석 결과">
              <Alert message={result.recommendation} type="info" showIcon style={{ marginBottom: 16 }} />
              <Row gutter={16} style={{ marginBottom: 16 }}>
                <Col span={12}>
                  <Statistic title="변경 전" value={result.old_value} suffix={result.param_key.includes('score') ? '점' : '%'} />
                </Col>
                <Col span={12}>
                  <Statistic title="변경 후" value={result.new_value} suffix={result.param_key.includes('score') ? '점' : '%'}
                    valueStyle={{ color: '#1677ff' }} />
                </Col>
              </Row>
              <Divider />
              <Row gutter={16}>
                <Col span={12}>
                  <Statistic title="승인율 변화" value={result.impact.approval_rate_change}
                    suffix="%p"
                    valueStyle={{ color: result.impact.approval_rate_change > 0 ? '#52c41a' : '#f5222d' }} />
                </Col>
                <Col span={12}>
                  <Statistic title="영향 고객 수" value={result.impact.affected_customers.toLocaleString()} suffix="명" />
                </Col>
                <Col span={12} style={{ marginTop: 12 }}>
                  <Statistic title="예상 수익 변화" value={result.impact.expected_revenue_change}
                    suffix="%"
                    valueStyle={{ color: result.impact.expected_revenue_change > 0 ? '#52c41a' : '#f5222d' }} />
                </Col>
                <Col span={12} style={{ marginTop: 12 }}>
                  <Statistic title="리스크 비용 변화" value={result.impact.risk_cost_change}
                    suffix="%"
                    valueStyle={{ color: result.impact.risk_cost_change < 0 ? '#52c41a' : '#f5222d' }} />
                </Col>
              </Row>
              <Divider />
              <Table
                dataSource={result.segment_impact}
                rowKey="segment"
                size="small"
                pagination={false}
                columns={[
                  { title: '세그먼트', dataIndex: 'segment', key: 'segment' },
                  {
                    title: '영향 방향', dataIndex: 'direction', key: 'direction',
                    render: (v: string) => <Tag color={v === '긍정' ? 'green' : v === '부정' ? 'red' : 'default'}>{v}</Tag>,
                  },
                  {
                    title: '영향 크기 (%p)', dataIndex: 'magnitude', key: 'magnitude',
                    render: (v: number) => v.toFixed(1),
                  },
                ]}
              />
            </Card>
          )}
        </Col>
      </Row>
    </>
  )
}
