import { Card, Statistic, Typography } from 'antd'
import { ArrowUpOutlined, ArrowDownOutlined, MinusOutlined } from '@ant-design/icons'

const { Text } = Typography

interface SparkPoint { value: number }

interface StatCardProps {
  title: string
  value: number | string
  prefix?: string
  suffix?: string
  precision?: number
  change?: number        // 전기 대비 변화량 (양수=증가, 음수=감소)
  changeLabel?: string   // 변화 라벨 (예: "전월 대비")
  spark?: SparkPoint[]   // 스파크라인 데이터 (최대 12개)
  invertColor?: boolean  // 감소가 좋은 지표(예: 연체율)일 때 true
}

export default function StatCard({
  title, value, prefix, suffix, precision, change, changeLabel, spark, invertColor,
}: StatCardProps) {
  const hasChange = change !== undefined && change !== null

  const isPositive = (change ?? 0) > 0
  const isNegative = (change ?? 0) < 0

  // 색상: 기본은 양수=초록/음수=빨강, invertColor면 반전
  const changeColor = !hasChange ? '#8c8c8c'
    : isPositive ? (invertColor ? '#f5222d' : '#3f8600')
    : isNegative ? (invertColor ? '#3f8600' : '#f5222d')
    : '#8c8c8c'

  const ChangeIcon = !hasChange ? MinusOutlined
    : isPositive ? ArrowUpOutlined
    : isNegative ? ArrowDownOutlined
    : MinusOutlined

  // 미니 스파크라인 SVG (너비 80, 높이 28)
  const SparkLine = () => {
    if (!spark || spark.length < 2) return null
    const vals = spark.map((p) => p.value)
    const min = Math.min(...vals)
    const max = Math.max(...vals)
    const range = max - min || 1
    const W = 80, H = 28, pad = 2
    const pts = vals.map((v, i) => {
      const x = pad + (i / (vals.length - 1)) * (W - pad * 2)
      const y = H - pad - ((v - min) / range) * (H - pad * 2)
      return `${x},${y}`
    }).join(' ')
    return (
      <svg width={W} height={H} style={{ display: 'block', marginTop: 4 }}>
        <polyline points={pts} fill="none" stroke="#1677ff" strokeWidth={1.5} />
      </svg>
    )
  }

  return (
    <Card size="small" style={{ height: '100%' }}>
      <Statistic
        title={title}
        value={value}
        prefix={prefix}
        suffix={suffix}
        precision={precision}
      />
      <SparkLine />
      {hasChange && (
        <div style={{ marginTop: 4 }}>
          <ChangeIcon style={{ color: changeColor, fontSize: 11 }} />
          <Text style={{ color: changeColor, fontSize: 12, marginLeft: 3 }}>
            {Math.abs(change!).toFixed(precision ?? 1)}{suffix}
          </Text>
          {changeLabel && (
            <Text type="secondary" style={{ fontSize: 11, marginLeft: 4 }}>{changeLabel}</Text>
          )}
        </div>
      )}
    </Card>
  )
}
