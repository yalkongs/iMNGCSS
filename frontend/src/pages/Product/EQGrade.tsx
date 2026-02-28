import { useEffect, useState } from 'react'
import { Card, Table, Tag, Typography, Spin } from 'antd'
import client from '../../api/client'

const { Title } = Typography

interface EQGrade {
  grade: string
  limit_multiplier: number
  rate_adj: number
  description: string
  active: boolean
}

const columns = [
  { title: 'EQ Grade', dataIndex: 'grade', key: 'grade', render: (v: string) => <Tag color="blue">{v}</Tag> },
  { title: '설명', dataIndex: 'description', key: 'description' },
  { title: '한도 배수', dataIndex: 'limit_multiplier', key: 'limit_multiplier', render: (v: number) => `${v}x` },
  {
    title: '금리 조정', dataIndex: 'rate_adj', key: 'rate_adj',
    render: (v: number) => {
      const pct = (v * 100).toFixed(2)
      return v < 0 ? <Tag color="green">{pct}%p</Tag> : v > 0 ? <Tag color="red">+{pct}%p</Tag> : <span>—</span>
    },
  },
  {
    title: '활성', dataIndex: 'active', key: 'active',
    render: (v: boolean) => <Tag color={v ? 'success' : 'default'}>{v ? '활성' : '비활성'}</Tag>,
  },
]

export default function ProductEQGrade() {
  const [grades, setGrades] = useState<EQGrade[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    client.get('/poc/eq-grade-master').then((res) => setGrades(res.data.grades)).finally(() => setLoading(false))
  }, [])

  if (loading) return <Spin size="large" style={{ display: 'block', marginTop: 80 }} />

  return (
    <>
      <Title level={4}>EQ Grade 관리</Title>
      <Card title="기업 신용등급 (EQ Grade) 마스터">
        <Table dataSource={grades} columns={columns} rowKey="grade" pagination={false} />
      </Card>
    </>
  )
}
