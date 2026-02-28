import { useState } from 'react'
import { Modal, Button, Typography, Collapse } from 'antd'
import { QuestionCircleOutlined } from '@ant-design/icons'

const { Paragraph, Text } = Typography

interface HelpSection {
  key: string
  label: string
  content: string
}

interface HelpModalProps {
  title: string
  summary: string
  sections?: HelpSection[]
}

export default function HelpModal({ title, summary, sections }: HelpModalProps) {
  const [open, setOpen] = useState(false)

  return (
    <>
      <Button
        type="text"
        icon={<QuestionCircleOutlined />}
        size="small"
        onClick={() => setOpen(true)}
        style={{ color: '#8c8c8c' }}
      />
      <Modal
        title={`📋 ${title} — 도움말`}
        open={open}
        onCancel={() => setOpen(false)}
        footer={<Button onClick={() => setOpen(false)}>닫기</Button>}
        width={600}
      >
        <Paragraph>{summary}</Paragraph>
        {sections && sections.length > 0 && (
          <Collapse
            size="small"
            items={sections.map((s) => ({
              key: s.key,
              label: <Text strong>{s.label}</Text>,
              children: <Paragraph style={{ margin: 0 }}>{s.content}</Paragraph>,
            }))}
          />
        )}
      </Modal>
    </>
  )
}
