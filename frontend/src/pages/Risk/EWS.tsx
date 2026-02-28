import { useEffect, useState } from 'react'
import { Card, Row, Col, Table, Tag, Typography, Spin, Tabs, Badge, Alert, Progress } from 'antd'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  LineChart, Line, Legend,
} from 'recharts'
import client from '../../api/client'

const { Title, Text } = Typography

interface EWSSummary {
  overview: {
    total_monitored: number; critical: number; warning: number; watch: number; normal: number
  }
  monitored: {
    name: string; product: string; loan_amount: number; score: number; grade: string; trend: string
    txn_score: number; cb_score_change: number; debt_score: number; inquiry_score: number
    payment_score: number; income_score: number; composite: number; signals: string[]
  }[]
  signal_summary: { signal_type: string; count: number; this_month: number }[]
  monthly_alerts: { month: string; critical: number; warning: number; watch: number }[]
}

const GRADE_COLOR: Record<string, string> = {
  CRITICAL: 'red', WARNING: 'orange', WATCH: 'gold', NORMAL: 'green',
}

export default function RiskEWS() {
  const [summary, setSummary] = useState<EWSSummary | null>(null)
  const [cbSignals, setCbSignals] = useState<{ signals: { name: string; current_score: number; drop_amount: number; period: string; reason: string }[] } | null>(null)
  const [debtSignals, setDebtSignals] = useState<{ signals: { name: string; total_debt: number; new_count: number; dsr: number; dsr_change: number; risk_level: string }[] } | null>(null)
  const [delinquency, setDelinquency] = useState<{ signals: { name: string; product: string; dpd: number; overdue_amount: number; stage: string; prev_dpd: number }[] } | null>(null)
  const [publicRecords, setPublicRecords] = useState<{ records: { name: string; record_type: string; amount: number; date: string; source: string; status: string }[] } | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    Promise.all([
      client.get('/poc/ews/summary'),
      client.get('/poc/ews/cb-signal'),
      client.get('/poc/ews/debt-signal'),
      client.get('/poc/ews/delinquency-signal'),
      client.get('/poc/ews/public'),
    ]).then(([s, cb, debt, del, pub]) => {
      setSummary(s.data)
      setCbSignals(cb.data)
      setDebtSignals(debt.data)
      setDelinquency(del.data)
      setPublicRecords(pub.data)
    }).finally(() => setLoading(false))
  }, [])

  if (loading) return <Spin size="large" style={{ display: 'block', marginTop: 80 }} />

  const ov = summary!.overview

  // 통합 탭
  const SummaryTab = () => (
    <>
      <Row gutter={16} style={{ marginBottom: 16 }}>
        {[
          { label: '모니터링 대상', value: ov.total_monitored, color: '#1677ff' },
          { label: 'CRITICAL', value: ov.critical, color: '#f5222d' },
          { label: 'WARNING', value: ov.warning, color: '#fa8c16' },
          { label: 'WATCH', value: ov.watch, color: '#faad14' },
          { label: 'NORMAL', value: ov.normal, color: '#52c41a' },
        ].map((k) => (
          <Col key={k.label} span={4}>
            <Card size="small" style={{ textAlign: 'center' }}>
              <Text type="secondary" style={{ fontSize: 11 }}>{k.label}</Text><br />
              <Text strong style={{ fontSize: 24, color: k.color }}>{k.value}</Text>
            </Card>
          </Col>
        ))}
      </Row>

      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={16}>
          <Card title="월별 EWS 경보 추이">
            <ResponsiveContainer width="100%" height={220}>
              <LineChart data={summary!.monthly_alerts}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="month" tick={{ fontSize: 11 }} />
                <YAxis />
                <Tooltip />
                <Legend />
                <Line type="monotone" dataKey="critical" name="CRITICAL" stroke="#f5222d" strokeWidth={2} />
                <Line type="monotone" dataKey="warning" name="WARNING" stroke="#fa8c16" strokeWidth={2} />
                <Line type="monotone" dataKey="watch" name="WATCH" stroke="#faad14" strokeWidth={2} />
              </LineChart>
            </ResponsiveContainer>
          </Card>
        </Col>
        <Col span={8}>
          <Card title="신호 유형별 건수">
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={summary!.signal_summary} layout="vertical">
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis type="number" />
                <YAxis type="category" dataKey="signal_type" width={120} tick={{ fontSize: 10 }} />
                <Tooltip />
                <Bar dataKey="count" name="누적" fill="#1677ff" />
                <Bar dataKey="this_month" name="이번달" fill="#52c41a" />
              </BarChart>
            </ResponsiveContainer>
          </Card>
        </Col>
      </Row>

      <Card title="EWS 모니터링 대상 (종합점수 기준)">
        <Table
          dataSource={summary!.monitored}
          rowKey="name"
          size="small"
          pagination={{ pageSize: 8 }}
          columns={[
            { title: '고객명', dataIndex: 'name', key: 'name', width: 80 },
            { title: '상품', dataIndex: 'product', key: 'product', width: 80 },
            {
              title: '대출금', dataIndex: 'loan_amount', key: 'loan_amount', width: 100,
              render: (v: number) => `${(v / 10000).toLocaleString()}만`,
            },
            {
              title: '등급', dataIndex: 'grade', key: 'grade', width: 90,
              render: (v: string) => <Tag color={GRADE_COLOR[v] ?? 'default'}>{v}</Tag>,
            },
            {
              title: '추세', dataIndex: 'trend', key: 'trend', width: 60,
              render: (v: string) => <Text style={{ color: v === '악화' ? '#f5222d' : v === '개선' ? '#52c41a' : '#8c8c8c' }}>{v}</Text>,
            },
            {
              title: '거래행태', dataIndex: 'txn_score', key: 'txn_score', width: 80,
              render: (v: number) => <Progress percent={v} size="small" strokeColor={v < 40 ? '#f5222d' : '#1677ff'} />,
            },
            {
              title: 'CB변동', dataIndex: 'cb_score_change', key: 'cb_score_change', width: 80,
              render: (v: number) => <Text style={{ color: v < -20 ? '#f5222d' : v < 0 ? '#fa8c16' : '#52c41a' }}>{v > 0 ? `+${v}` : v}</Text>,
            },
            {
              title: '신호', dataIndex: 'signals', key: 'signals',
              render: (v: string[]) => v.map((s) => <Tag key={s} color="orange" style={{ fontSize: 10 }}>{s}</Tag>),
            },
          ]}
        />
      </Card>
    </>
  )

  // CB 신호 탭
  const CBSignalTab = () => (
    <Card title="CB 신용점수 급락 경보">
      <Alert message="30일 내 20점 이상 하락 고객 자동 감지" type="warning" showIcon style={{ marginBottom: 12 }} />
      <Table
        dataSource={cbSignals?.signals ?? []}
        rowKey="name"
        size="small"
        columns={[
          { title: '고객명', dataIndex: 'name', key: 'name' },
          { title: '현재점수', dataIndex: 'current_score', key: 'current_score' },
          {
            title: '하락폭', dataIndex: 'drop_amount', key: 'drop_amount',
            render: (v: number) => <Text style={{ color: '#f5222d', fontWeight: 700 }}>-{v}점</Text>,
          },
          { title: '기간', dataIndex: 'period', key: 'period' },
          { title: '추정 원인', dataIndex: 'reason', key: 'reason' },
        ]}
      />
    </Card>
  )

  // 부채 신호 탭
  const DebtSignalTab = () => (
    <Card title="부채 급증 / 다중채무 경보">
      <Alert message="3개월 내 타기관 대출 3건 이상 신규, 또는 DSR 급증 감지" type="warning" showIcon style={{ marginBottom: 12 }} />
      <Table
        dataSource={debtSignals?.signals ?? []}
        rowKey="name"
        size="small"
        columns={[
          { title: '고객명', dataIndex: 'name', key: 'name' },
          { title: '총 부채', dataIndex: 'total_debt', key: 'total_debt', render: (v: number) => `${(v / 10000).toLocaleString()}만원` },
          { title: '신규 건수', dataIndex: 'new_count', key: 'new_count', render: (v: number) => <Tag color={v >= 3 ? 'red' : 'orange'}>{v}건</Tag> },
          { title: 'DSR (%)', dataIndex: 'dsr', key: 'dsr', render: (v: number) => <Tag color={v > 40 ? 'red' : 'orange'}>{v.toFixed(1)}%</Tag> },
          { title: 'DSR 변화', dataIndex: 'dsr_change', key: 'dsr_change', render: (v: number) => `+${v.toFixed(1)}%p` },
          { title: '위험등급', dataIndex: 'risk_level', key: 'risk_level', render: (v: string) => <Tag color={v === 'HIGH' ? 'red' : 'orange'}>{v}</Tag> },
        ]}
      />
    </Card>
  )

  // 연체 탭
  const DelinquencyTab = () => (
    <Card title="연체 조기경보 (DPD)">
      <Alert message="DPD 1일 이상 발생 시 즉시 경보, 30일 이상은 CRITICAL 처리" type="error" showIcon style={{ marginBottom: 12 }} />
      <Table
        dataSource={delinquency?.signals ?? []}
        rowKey="name"
        size="small"
        columns={[
          { title: '고객명', dataIndex: 'name', key: 'name' },
          { title: '상품', dataIndex: 'product', key: 'product' },
          {
            title: 'DPD', dataIndex: 'dpd', key: 'dpd',
            render: (v: number) => <Tag color={v >= 30 ? 'red' : v >= 7 ? 'orange' : 'gold'}>{v}일</Tag>,
          },
          { title: '연체금액', dataIndex: 'overdue_amount', key: 'overdue_amount', render: (v: number) => `${(v / 10000).toLocaleString()}만원` },
          {
            title: '단계', dataIndex: 'stage', key: 'stage',
            render: (v: string) => <Tag color={v === 'CRITICAL' ? 'red' : v === 'WARNING' ? 'orange' : 'gold'}>{v}</Tag>,
          },
        ]}
      />
    </Card>
  )

  // 공적정보 탭
  const PublicTab = () => (
    <Card title="공적 정보 이상 감지 (세금체납/소송/파산)">
      <Alert message="국세청, 법원 공개 데이터 연동 기반 자동 감지" type="info" showIcon style={{ marginBottom: 12 }} />
      <Table
        dataSource={publicRecords?.records ?? []}
        rowKey={(r) => `${r.name}-${r.date}`}
        size="small"
        columns={[
          { title: '고객명', dataIndex: 'name', key: 'name' },
          {
            title: '유형', dataIndex: 'record_type', key: 'record_type',
            render: (v: string) => <Tag color={v.includes('체납') || v.includes('파산') ? 'red' : 'orange'}>{v}</Tag>,
          },
          { title: '금액', dataIndex: 'amount', key: 'amount', render: (v: number) => `${(v / 10000).toLocaleString()}만원` },
          { title: '발생일', dataIndex: 'date', key: 'date' },
          { title: '출처', dataIndex: 'source', key: 'source' },
          {
            title: '상태', dataIndex: 'status', key: 'status',
            render: (v: string) => <Tag color={v === '미해결' ? 'red' : 'default'}>{v}</Tag>,
          },
        ]}
      />
    </Card>
  )

  return (
    <>
      <Title level={4}>개인 고객 EWS (조기경보 시스템)</Title>
      <Tabs
        items={[
          { key: 'summary', label: <Badge count={ov.critical} size="small"><span>통합 대시보드</span></Badge>, children: <SummaryTab /> },
          { key: 'cb', label: 'CB 신호', children: <CBSignalTab /> },
          { key: 'debt', label: '부채 급증', children: <DebtSignalTab /> },
          { key: 'delinquency', label: '연체 경보', children: <DelinquencyTab /> },
          { key: 'public', label: '공적 정보', children: <PublicTab /> },
        ]}
      />
    </>
  )
}
