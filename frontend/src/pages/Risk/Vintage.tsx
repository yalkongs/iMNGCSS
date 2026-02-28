import { useEffect, useState } from 'react'
import { Card, Table, Typography, Spin } from 'antd'
import client from '../../api/client'

const { Title } = Typography

interface VintageRow {
  cohort: string
  mob_3: number
  mob_6: number
  mob_12: number
}

const heatColor = (v: number) => {
  if (v < 1.0) return '#f6ffed'
  if (v < 2.0) return '#fff7e6'
  if (v < 3.5) return '#fff1f0'
  return '#ffa39e'
}

export default function RiskVintage() {
  const [data, setData] = useState<{ cohorts: VintageRow[]; mobs: number[] } | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    client.get('/poc/vintage').then((res) => setData(res.data)).finally(() => setLoading(false))
  }, [])

  if (loading) return <Spin size="large" style={{ display: 'block', marginTop: 80 }} />

  const columns = [
    { title: '코호트', dataIndex: 'cohort', key: 'cohort' },
    ...data!.mobs.map((mob) => ({
      title: `MOB ${mob}`,
      dataIndex: `mob_${mob}`,
      key: `mob_${mob}`,
      render: (v: number) => (
        <div style={{ background: heatColor(v), padding: '2px 8px', borderRadius: 4, textAlign: 'center' as const }}>
          {v.toFixed(2)}%
        </div>
      ),
    })),
  ]

  return (
    <>
      <Title level={4}>빈티지 분석 (Vintage Analysis)</Title>
      <Card
        title="코호트별 누적 부도율 (%)"
        extra={
          <span style={{ fontSize: 12 }}>
            <span style={{ background: '#f6ffed', padding: '2px 8px', marginRight: 8 }}>{'<'}1.0%</span>
            <span style={{ background: '#fff7e6', padding: '2px 8px', marginRight: 8 }}>1~2%</span>
            <span style={{ background: '#fff1f0', padding: '2px 8px', marginRight: 8 }}>2~3.5%</span>
            <span style={{ background: '#ffa39e', padding: '2px 8px' }}>{'≥'}3.5%</span>
          </span>
        }
      >
        <Table
          dataSource={data!.cohorts}
          columns={columns}
          rowKey="cohort"
          pagination={false}
          size="small"
        />
      </Card>
    </>
  )
}
