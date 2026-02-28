import { useEffect, useState } from 'react'
import { Row, Col, Card, Typography, Spin, Tag, Progress, Table, Timeline } from 'antd'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from 'recharts'
import client from '../../api/client'

const { Title, Text } = Typography

interface PolicyDashData {
  param_stats: { total: number; active: number; modified_this_month: number; pending_review: number }
  compliance: {
    dsr_compliance_rate: number; ltv_compliance_rate: number; rate_compliance_rate: number; overall: number
  }
  recent_changes: { param_key: string; old_value: string; new_value: string; changed_by: string; changed_at: string; category: string }[]
  approval_pipeline: { stage: string; count: number }[]
  policy_kpi: { name: string; value: number; target: number; unit: string; ok: boolean }[]
}

export default function PolicyDashboard() {
  const [data, setData] = useState<PolicyDashData | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    client.get('/poc/dashboard/policy').then((r) => setData(r.data)).finally(() => setLoading(false))
  }, [])

  if (loading) return <Spin size="large" style={{ display: 'block', marginTop: 80 }} />

  const ps = data!.param_stats
  const co = data!.compliance

  return (
    <>
      <Title level={4}>여신 정책 대시보드</Title>

      {/* 파라미터 현황 */}
      <Row gutter={16} style={{ marginBottom: 16 }}>
        {[
          { label: '전체 파라미터', value: ps.total, color: '#1677ff' },
          { label: '활성', value: ps.active, color: '#52c41a' },
          { label: '이번달 변경', value: ps.modified_this_month, color: '#faad14' },
          { label: '검토 대기', value: ps.pending_review, color: '#f5222d' },
        ].map((k) => (
          <Col key={k.label} span={6}>
            <Card size="small" style={{ textAlign: 'center' }}>
              <Text type="secondary" style={{ fontSize: 12 }}>{k.label}</Text><br />
              <Text strong style={{ fontSize: 28, color: k.color }}>{k.value}</Text>
            </Card>
          </Col>
        ))}
      </Row>

      {/* 규제 준수율 */}
      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={12}>
          <Card title="규제 준수율">
            <Row gutter={16}>
              {[
                { label: 'DSR', value: co.dsr_compliance_rate },
                { label: 'LTV', value: co.ltv_compliance_rate },
                { label: '금리한도', value: co.rate_compliance_rate },
                { label: '종합', value: co.overall },
              ].map((c) => (
                <Col key={c.label} span={12} style={{ marginBottom: 16 }}>
                  <Text type="secondary">{c.label}</Text>
                  <Progress
                    percent={c.value}
                    strokeColor={c.value >= 99 ? '#52c41a' : c.value >= 95 ? '#faad14' : '#f5222d'}
                    format={(p) => `${p}%`}
                  />
                </Col>
              ))}
            </Row>
          </Card>
        </Col>
        <Col span={12}>
          <Card title="정책 KPI">
            <Table
              dataSource={data!.policy_kpi}
              rowKey="name"
              size="small"
              pagination={false}
              columns={[
                { title: '지표', dataIndex: 'name', key: 'name' },
                {
                  title: '현재', key: 'current',
                  render: (_: unknown, r: { value: number; unit: string; ok: boolean }) => (
                    <Text style={{ color: r.ok ? '#3f8600' : '#cf1322', fontWeight: 700 }}>
                      {r.value}{r.unit}
                    </Text>
                  ),
                },
                { title: '목표', key: 'target', render: (_: unknown, r: { value: number; target: number; unit: string; ok: boolean }) => `${r.target}${r.unit}` },
                {
                  title: '달성', key: 'ok',
                  render: (_: unknown, r: { ok: boolean }) => <Tag color={r.ok ? 'green' : 'red'}>{r.ok ? '달성' : '미달'}</Tag>,
                },
              ]}
            />
          </Card>
        </Col>
      </Row>

      <Row gutter={16}>
        <Col span={14}>
          <Card title="승인 파이프라인">
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={data!.approval_pipeline}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="stage" tick={{ fontSize: 11 }} />
                <YAxis />
                <Tooltip />
                <Bar dataKey="count" name="건수" fill="#1677ff" />
              </BarChart>
            </ResponsiveContainer>
          </Card>
        </Col>
        <Col span={10}>
          <Card title="최근 파라미터 변경 이력">
            <Timeline
              items={data!.recent_changes.slice(0, 5).map((c) => ({
                color: 'blue',
                children: (
                  <div style={{ fontSize: 12 }}>
                    <Tag color="blue" style={{ fontSize: 10 }}>{c.category}</Tag>
                    <Text strong style={{ fontSize: 12 }}>{c.param_key}</Text><br />
                    <Text type="secondary">{c.old_value} → {c.new_value}</Text><br />
                    <Text type="secondary" style={{ fontSize: 10 }}>{c.changed_by} | {c.changed_at}</Text>
                  </div>
                ),
              }))}
            />
          </Card>
        </Col>
      </Row>
    </>
  )
}
