import { Card, Progress, Typography } from 'antd'

const { Text } = Typography

interface GaugeCardProps {
  title: string
  value: number         // 0~100
  unit?: string
  thresholds?: {        // 색상 임계값 (기본: 녹색/노랑/빨강)
    green: number       // value < green → 초록
    yellow: number      // green ≤ value < yellow → 노랑
  }
  size?: 'small' | 'default'
  description?: string
  invertColor?: boolean // 높을수록 좋은 지표 (예: 승인율) → 반전
}

export default function GaugeCard({
  title, value, unit = '%', thresholds, size = 'default', description, invertColor,
}: GaugeCardProps) {
  const green = thresholds?.green ?? 60
  const yellow = thresholds?.yellow ?? 80

  let strokeColor: string
  if (invertColor) {
    strokeColor = value >= yellow ? '#52c41a' : value >= green ? '#faad14' : '#f5222d'
  } else {
    strokeColor = value < green ? '#52c41a' : value < yellow ? '#faad14' : '#f5222d'
  }

  return (
    <Card size="small" style={{ textAlign: 'center', height: '100%' }}>
      <Text type="secondary" style={{ fontSize: 12 }}>{title}</Text>
      <div style={{ marginTop: 8 }}>
        <Progress
          type="dashboard"
          percent={Math.round(value)}
          strokeColor={strokeColor}
          size={size === 'small' ? 80 : 120}
          format={(pct) => (
            <span style={{ fontSize: size === 'small' ? 14 : 18, fontWeight: 600 }}>
              {pct}{unit}
            </span>
          )}
        />
      </div>
      {description && (
        <Text type="secondary" style={{ fontSize: 11 }}>{description}</Text>
      )}
    </Card>
  )
}
