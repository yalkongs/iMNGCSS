import { useEffect, useState } from 'react'
import { Row, Col, Card, Statistic, Badge, Typography, Spin } from 'antd'
import { pocApi } from '../../api/poc'

const { Title, Text } = Typography

const psiLight = (status: string) =>
  status === 'green' ? '#52c41a' : status === 'yellow' ? '#faad14' : '#f5222d'

const psiLabel = (v: number) => v < 0.1 ? '정상' : v < 0.2 ? '경고' : '위험'

export default function RiskDashboard() {
  const [data, setData] = useState<{
    psi_summary: { score_psi: number; feature_psi_avg: number; target_psi: number; status: string }
    portfolio: { total_exposure: number; avg_pd: number; avg_lgd: number; expected_loss: number; rwa: number }
    calibration: { ece: number; brier_score: number; gini: number; ks_stat: number }
  } | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    pocApi.dashboard.risk().then((res) => setData(res.data)).finally(() => setLoading(false))
  }, [])

  if (loading) return <Spin size="large" style={{ display: 'block', marginTop: 80 }} />

  const psi = data!.psi_summary
  const port = data!.portfolio
  const cal = data!.calibration

  return (
    <>
      <Title level={4}>리스크 대시보드</Title>
      <Row gutter={16} style={{ marginBottom: 24 }}>
        <Col span={8}>
          <Card title="PSI 신호등">
            <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
              <div style={{
                width: 48, height: 48, borderRadius: '50%',
                background: psiLight(psi.status), boxShadow: `0 0 16px ${psiLight(psi.status)}`
              }} />
              <div>
                <Text strong style={{ fontSize: 16 }}>{psiLabel(psi.score_psi)}</Text><br />
                <Text type="secondary">Score PSI: {psi.score_psi.toFixed(3)}</Text><br />
                <Text type="secondary">Feature PSI: {psi.feature_psi_avg.toFixed(3)}</Text>
              </div>
            </div>
          </Card>
        </Col>
        <Col span={16}>
          <Card title="포트폴리오 요약">
            <Row gutter={16}>
              <Col span={6}><Statistic title="총 익스포저" value={`${(port.total_exposure / 10000).toLocaleString()}억`} /></Col>
              <Col span={6}><Statistic title="평균 PD" value={`${(port.avg_pd * 100).toFixed(2)}%`} /></Col>
              <Col span={6}><Statistic title="예상 손실" value={`${(port.expected_loss * 100).toFixed(2)}%`} /></Col>
              <Col span={6}><Statistic title="RWA" value={`${(port.rwa / 10000).toLocaleString()}억`} /></Col>
            </Row>
          </Card>
        </Col>
      </Row>
      <Row gutter={16}>
        <Col span={24}>
          <Card title="모델 성능 지표">
            <Row gutter={16}>
              <Col span={6}><Statistic title="Gini 계수" value={`${(cal.gini * 100).toFixed(1)}%`} valueStyle={{ color: '#1677ff' }} /></Col>
              <Col span={6}><Statistic title="KS 통계량" value={`${(cal.ks_stat * 100).toFixed(1)}%`} valueStyle={{ color: '#1677ff' }} /></Col>
              <Col span={6}><Statistic title="ECE" value={cal.ece.toFixed(4)} /></Col>
              <Col span={6}><Statistic title="Brier Score" value={cal.brier_score.toFixed(4)} /></Col>
            </Row>
          </Card>
        </Col>
      </Row>
      <Row style={{ marginTop: 16 }}>
        <Col span={24}>
          <Card size="small">
            <Badge status="success" text="PSI < 0.10: 정상" style={{ marginRight: 24 }} />
            <Badge status="warning" text="0.10 ≤ PSI < 0.20: 경고 (모니터링 강화)" style={{ marginRight: 24 }} />
            <Badge status="error" text="PSI ≥ 0.20: 위험 (재학습 필요)" />
          </Card>
        </Col>
      </Row>
    </>
  )
}
