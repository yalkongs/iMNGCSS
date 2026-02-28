import { useState, useEffect } from 'react'
import { Badge, Button, Popover, List, Typography, Tag, Empty } from 'antd'
import { BellOutlined } from '@ant-design/icons'
import client from '../api/client'

const { Text } = Typography

interface Notification {
  id: string
  level: 'INFO' | 'WARNING' | 'CRITICAL'
  category: string
  message: string
  created_at: string
  read: boolean
}

const levelColor: Record<string, string> = {
  INFO: 'blue',
  WARNING: 'orange',
  CRITICAL: 'red',
}

export default function NotificationCenter() {
  const [items, setItems] = useState<Notification[]>([])
  const [open, setOpen] = useState(false)

  useEffect(() => {
    client.get('/poc/notifications')
      .then((r) => setItems(r.data.notifications ?? []))
      .catch(() => {/* 조용히 무시 */})
  }, [])

  const unread = items.filter((n) => !n.read).length

  const markAllRead = () => setItems((prev) => prev.map((n) => ({ ...n, read: true })))

  const content = (
    <div style={{ width: 340 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
        <Text strong>알림 센터</Text>
        {unread > 0 && (
          <Button type="link" size="small" onClick={markAllRead}>모두 읽음</Button>
        )}
      </div>
      {items.length === 0 ? (
        <Empty description="알림 없음" image={Empty.PRESENTED_IMAGE_SIMPLE} />
      ) : (
        <List
          size="small"
          dataSource={items.slice(0, 10)}
          renderItem={(n) => (
            <List.Item style={{ opacity: n.read ? 0.5 : 1, alignItems: 'flex-start' }}>
              <div style={{ width: '100%' }}>
                <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                  <Tag color={levelColor[n.level]} style={{ margin: 0 }}>{n.level}</Tag>
                  <Text type="secondary" style={{ fontSize: 11 }}>{n.category}</Text>
                </div>
                <Text style={{ fontSize: 12 }}>{n.message}</Text>
                <div>
                  <Text type="secondary" style={{ fontSize: 10 }}>{n.created_at}</Text>
                </div>
              </div>
            </List.Item>
          )}
        />
      )}
    </div>
  )

  return (
    <Popover
      content={content}
      trigger="click"
      open={open}
      onOpenChange={setOpen}
      placement="bottomRight"
    >
      <Badge count={unread} size="small">
        <Button type="text" icon={<BellOutlined />} style={{ color: '#fff' }} />
      </Badge>
    </Popover>
  )
}
