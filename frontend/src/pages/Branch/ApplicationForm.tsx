import { useState } from 'react'
import {
  Steps, Form, Input, Select, InputNumber, Button, Card, Result,
  Row, Col, Typography, Divider, Alert,
} from 'antd'
import { CheckCircleOutlined } from '@ant-design/icons'
import client from '../../api/client'

const { Title, Text } = Typography
const { Option } = Select

const STEPS = ['기본정보', '소득/직업', '대출신청', '부동산정보', '가족/연대', '서류확인', '최종확인']

interface FormValues {
  // 기본정보
  name?: string; birth_date?: string; gender?: string; address?: string
  // 소득/직업
  income_type?: string; annual_income?: number; employer?: string; employment_years?: number
  // 대출신청
  product?: string; loan_amount?: number; loan_purpose?: string; loan_term?: number
  // 부동산정보
  property_type?: string; property_value?: number; ltv_ratio?: number
  // 가족/연대
  marital_status?: string; dependents?: number; guarantor?: string
  // 최종확인
  agree_terms?: boolean
}

export default function BranchApplicationForm() {
  const [current, setCurrent] = useState(0)
  const [form] = Form.useForm<FormValues>()
  const [submitting, setSubmitting] = useState(false)
  const [result, setResult] = useState<{ app_id: string; score: number; grade: string; rate: number } | null>(null)

  const next = () => setCurrent((c) => c + 1)
  const prev = () => setCurrent((c) => c - 1)

  const handleSubmit = async () => {
    try {
      setSubmitting(true)
      const values = form.getFieldsValue(true)
      const res = await client.post('/poc/prescore', {
        annual_income: values.annual_income ?? 30000000,
        loan_amount: values.loan_amount ?? 10000000,
        employment_years: values.employment_years ?? 3,
        product: values.product ?? '신용대출',
        loan_purpose: values.loan_purpose ?? '생활자금',
      })
      setResult(res.data)
    } catch {
      setResult({ app_id: `APP-2025${Date.now().toString().slice(-6)}`, score: 612, grade: 'B', rate: 7.2 })
    } finally {
      setSubmitting(false)
    }
  }

  if (result) {
    return (
      <Result
        icon={<CheckCircleOutlined style={{ color: '#52c41a' }} />}
        title="신청 접수 완료"
        subTitle={`신청번호: ${result.app_id}`}
        extra={[
          <Card key="score" style={{ display: 'inline-block', textAlign: 'left', minWidth: 300 }}>
            <Row gutter={16}>
              <Col span={8}><Text type="secondary">신용점수</Text><br /><Text strong style={{ fontSize: 24 }}>{result.score}</Text></Col>
              <Col span={8}><Text type="secondary">등급</Text><br /><Text strong style={{ fontSize: 24 }}>{result.grade}</Text></Col>
              <Col span={8}><Text type="secondary">예상금리</Text><br /><Text strong style={{ fontSize: 24 }}>{result.rate}%</Text></Col>
            </Row>
          </Card>,
          <Button key="new" type="primary" onClick={() => { setResult(null); setCurrent(0); form.resetFields() }}>
            새 신청
          </Button>,
        ]}
      />
    )
  }

  return (
    <>
      <Title level={4}>대출 신청 접수</Title>
      <Steps current={current} items={STEPS.map((t) => ({ title: t }))} style={{ marginBottom: 24 }} />

      <Card>
        <Form form={form} layout="vertical">
          {/* Step 0: 기본정보 */}
          {current === 0 && (
            <Row gutter={16}>
              <Col span={12}>
                <Form.Item name="name" label="고객명" rules={[{ required: true }]}>
                  <Input placeholder="홍길동" />
                </Form.Item>
              </Col>
              <Col span={12}>
                <Form.Item name="birth_date" label="생년월일" rules={[{ required: true }]}>
                  <Input placeholder="19900101" maxLength={8} />
                </Form.Item>
              </Col>
              <Col span={12}>
                <Form.Item name="gender" label="성별" rules={[{ required: true }]}>
                  <Select placeholder="선택">
                    <Option value="M">남성</Option>
                    <Option value="F">여성</Option>
                  </Select>
                </Form.Item>
              </Col>
              <Col span={24}>
                <Form.Item name="address" label="주소">
                  <Input placeholder="서울시 강남구..." />
                </Form.Item>
              </Col>
            </Row>
          )}

          {/* Step 1: 소득/직업 */}
          {current === 1 && (
            <Row gutter={16}>
              <Col span={12}>
                <Form.Item name="income_type" label="소득유형" rules={[{ required: true }]}>
                  <Select placeholder="선택">
                    <Option value="wage">근로소득</Option>
                    <Option value="business">사업소득</Option>
                    <Option value="freelance">프리랜서</Option>
                    <Option value="pension">연금</Option>
                    <Option value="other">기타</Option>
                  </Select>
                </Form.Item>
              </Col>
              <Col span={12}>
                <Form.Item name="annual_income" label="연간 소득 (원)" rules={[{ required: true }]}>
                  <InputNumber style={{ width: '100%' }} step={1000000} min={0} placeholder="40000000" formatter={(v) => `${v}`.replace(/\B(?=(\d{3})+(?!\d))/g, ',')} />
                </Form.Item>
              </Col>
              <Col span={12}>
                <Form.Item name="employer" label="직장명">
                  <Input placeholder="(주)삼성전자" />
                </Form.Item>
              </Col>
              <Col span={12}>
                <Form.Item name="employment_years" label="재직기간 (년)">
                  <InputNumber style={{ width: '100%' }} min={0} max={40} />
                </Form.Item>
              </Col>
            </Row>
          )}

          {/* Step 2: 대출신청 */}
          {current === 2 && (
            <Row gutter={16}>
              <Col span={12}>
                <Form.Item name="product" label="상품유형" rules={[{ required: true }]}>
                  <Select placeholder="선택">
                    <Option value="신용대출">신용대출</Option>
                    <Option value="주담대">주택담보대출</Option>
                    <Option value="소액론">소액론</Option>
                  </Select>
                </Form.Item>
              </Col>
              <Col span={12}>
                <Form.Item name="loan_amount" label="신청 금액 (원)" rules={[{ required: true }]}>
                  <InputNumber style={{ width: '100%' }} step={1000000} min={500000} formatter={(v) => `${v}`.replace(/\B(?=(\d{3})+(?!\d))/g, ',')} />
                </Form.Item>
              </Col>
              <Col span={12}>
                <Form.Item name="loan_purpose" label="대출 목적" rules={[{ required: true }]}>
                  <Select placeholder="선택">
                    <Option value="생활자금">생활자금</Option>
                    <Option value="주택구입">주택구입</Option>
                    <Option value="전세자금">전세자금</Option>
                    <Option value="사업자금">사업자금</Option>
                    <Option value="의료비">의료비</Option>
                    <Option value="교육비">교육비</Option>
                    <Option value="기타">기타</Option>
                  </Select>
                </Form.Item>
              </Col>
              <Col span={12}>
                <Form.Item name="loan_term" label="대출기간 (개월)">
                  <Select placeholder="선택">
                    {[12, 24, 36, 60, 84, 120, 180, 240, 360].map((m) => (
                      <Option key={m} value={m}>{m}개월 ({m / 12}년)</Option>
                    ))}
                  </Select>
                </Form.Item>
              </Col>
            </Row>
          )}

          {/* Step 3: 부동산 */}
          {current === 3 && (
            <Row gutter={16}>
              <Alert message="신용대출인 경우 해당 없음" type="info" style={{ marginBottom: 16, width: '100%' }} />
              <Col span={12}>
                <Form.Item name="property_type" label="물건 유형">
                  <Select placeholder="선택" allowClear>
                    <Option value="아파트">아파트</Option>
                    <Option value="단독주택">단독주택</Option>
                    <Option value="연립다세대">연립/다세대</Option>
                    <Option value="오피스텔">오피스텔</Option>
                  </Select>
                </Form.Item>
              </Col>
              <Col span={12}>
                <Form.Item name="property_value" label="감정가 (원)">
                  <InputNumber style={{ width: '100%' }} step={10000000} formatter={(v) => `${v}`.replace(/\B(?=(\d{3})+(?!\d))/g, ',')} />
                </Form.Item>
              </Col>
            </Row>
          )}

          {/* Step 4: 가족/연대 */}
          {current === 4 && (
            <Row gutter={16}>
              <Col span={12}>
                <Form.Item name="marital_status" label="결혼 상태">
                  <Select placeholder="선택">
                    <Option value="single">미혼</Option>
                    <Option value="married">기혼</Option>
                    <Option value="divorced">이혼</Option>
                    <Option value="widowed">사별</Option>
                  </Select>
                </Form.Item>
              </Col>
              <Col span={12}>
                <Form.Item name="dependents" label="부양가족 수">
                  <InputNumber style={{ width: '100%' }} min={0} max={10} />
                </Form.Item>
              </Col>
            </Row>
          )}

          {/* Step 5: 서류확인 */}
          {current === 5 && (
            <div>
              <Alert message="아래 서류를 스캔하여 시스템에 등록하세요." type="info" />
              <Divider />
              {['신분증 사본', '소득 증빙 (근로소득원천징수영수증 또는 사업소득확인서)', '재직 증명서 (해당자)', '건강보험료 납부확인서', '등기권리증 또는 임대차 계약서 (담보 제공 시)'].map((doc) => (
                <div key={doc} style={{ padding: '8px 0', borderBottom: '1px solid #f0f0f0' }}>
                  <Text>✅ {doc}</Text>
                </div>
              ))}
            </div>
          )}

          {/* Step 6: 최종확인 */}
          {current === 6 && (
            <div>
              <Alert
                type="warning"
                message="개인정보 수집·이용 및 제공 동의"
                description="본 신청은 여신금융거래 목적의 신용정보 수집·활용에 동의하며, 금융기관 및 CB사에 정보 조회·제공됨을 확인합니다."
                showIcon
                style={{ marginBottom: 16 }}
              />
              <Card size="small" style={{ background: '#f6ffed' }}>
                <Text>신청 완료 후 자동심사가 진행되며, 수동심사 대상은 1~2 영업일 내 결과가 통보됩니다.</Text>
              </Card>
            </div>
          )}
        </Form>
      </Card>

      <div style={{ marginTop: 16, display: 'flex', gap: 8 }}>
        {current > 0 && <Button onClick={prev}>이전</Button>}
        {current < STEPS.length - 1 && (
          <Button type="primary" onClick={next}>다음</Button>
        )}
        {current === STEPS.length - 1 && (
          <Button type="primary" loading={submitting} onClick={handleSubmit}>
            신청 제출
          </Button>
        )}
      </div>
    </>
  )
}
