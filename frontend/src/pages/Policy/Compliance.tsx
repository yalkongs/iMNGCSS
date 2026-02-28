import { useEffect, useState } from 'react'
import { Card, Row, Col, Statistic, Progress, Typography, Spin, Badge } from 'antd'

import { pocApi } from '../../api/poc'

const { Title, Text } = Typography

interface ComplianceData {
  as_of: string
  dsr: { limit: number; actual_avg: number; violation_count: number; compliance_rate: number; status: string }
  ltv: { general_limit: number; adjusted_limit: number; speculative_limit: number; actual_avg: number; violation_count: number; compliance_rate: number; status: string }
  rate: { max_limit: number; actual_max: number; violation_count: number; compliance_rate: number; status: string }
}

const lightColor = (s: string) =>
  s === 'green' ? '#52c41a' : s === 'yellow' ? '#faad14' : '#f5222d'

export default function PolicyCompliance() {
  const [data, setData] = useState<ComplianceData | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    pocApi.complianceStatus().then((res) => setData(res.data)).finally(() => setLoading(false))
  }, [])

  if (loading) return <Spin size="large" style={{ display: 'block', marginTop: 80 }} />

  return (
    <>
      <Title level={4}>규제 준수 현황 <Text type="secondary" style={{ fontSize: 14 }}>(기준일: {data?.as_of})</Text></Title>
      <Row gutter={16}>
        {/* DSR */}
        <Col span={8}>
          <Card
            title={<><span style={{ width: 12, height: 12, borderRadius: '50%', background: lightColor(data!.dsr.status), display: 'inline-block', marginRight: 8 }} />DSR 준수율</>}
          >
            <Progress percent={+data!.dsr.compliance_rate.toFixed(1)} status={data!.dsr.status === 'green' ? 'success' : 'exception'} />
            <Statistic title="한도" value={`${(data!.dsr.limit * 100).toFixed(0)}%`} style={{ marginTop: 12 }} />
            <Statistic title="실제 평균" value={`${(data!.dsr.actual_avg * 100).toFixed(1)}%`} />
            <Statistic title="위반 건수" value={data!.dsr.violation_count} suffix="건"
              valueStyle={{ color: data!.dsr.violation_count > 0 ? '#f5222d' : '#3f8600' }} />
          </Card>
        </Col>
        {/* LTV */}
        <Col span={8}>
          <Card
            title={<><span style={{ width: 12, height: 12, borderRadius: '50%', background: lightColor(data!.ltv.status), display: 'inline-block', marginRight: 8 }} />LTV 준수율</>}
          >
            <Progress percent={+data!.ltv.compliance_rate.toFixed(1)} status={data!.ltv.status === 'green' ? 'success' : 'exception'} />
            <Statistic title="일반 한도" value={`${(data!.ltv.general_limit * 100).toFixed(0)}%`} style={{ marginTop: 12 }} />
            <Statistic title="실제 평균" value={`${(data!.ltv.actual_avg * 100).toFixed(1)}%`} />
            <Statistic title="위반 건수" value={data!.ltv.violation_count} suffix="건"
              valueStyle={{ color: data!.ltv.violation_count > 0 ? '#f5222d' : '#3f8600' }} />
          </Card>
        </Col>
        {/* 금리 */}
        <Col span={8}>
          <Card
            title={<><span style={{ width: 12, height: 12, borderRadius: '50%', background: lightColor(data!.rate.status), display: 'inline-block', marginRight: 8 }} />최고금리 준수율</>}
          >
            <Progress percent={+data!.rate.compliance_rate.toFixed(1)} status="success" />
            <Statistic title="법정 최고금리" value={`${(data!.rate.max_limit * 100).toFixed(0)}%`} style={{ marginTop: 12 }} />
            <Statistic title="실제 최고금리" value={`${(data!.rate.actual_max * 100).toFixed(1)}%`} />
            <Statistic title="위반 건수" value={data!.rate.violation_count} suffix="건"
              valueStyle={{ color: '#3f8600' }} />
          </Card>
        </Col>
      </Row>
      <Card style={{ marginTop: 16 }} size="small">
        <Badge status="success" text="DSR 한도: 40% (금융위원회)" style={{ marginRight: 24 }} />
        <Badge status="success" text="LTV: 일반 70% / 조정 60% / 투기 40%" style={{ marginRight: 24 }} />
        <Badge status="success" text="법정 최고금리: 20%" />
      </Card>
    </>
  )
}
