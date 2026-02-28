import { Form, Input, Button, Card, Typography, message, Select } from 'antd'
import { UserOutlined, LockOutlined } from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'
import axios from 'axios'
import { useAuthStore, type Role } from '../../store/auth'

const { Title, Text } = Typography

const DEMO_ACCOUNTS = [
  { value: 'admin', label: 'admin (전체 메뉴)' },
  { value: 'risk_manager', label: 'risk_manager (리스크/상품)' },
  { value: 'compliance', label: 'compliance (정책/리스크)' },
  { value: 'developer', label: 'developer (영업점/마케팅)' },
]

export default function Login() {
  const navigate = useNavigate()
  const { login } = useAuthStore()
  const [form] = Form.useForm()

  const onFinish = async (values: { username: string; password: string }) => {
    try {
      const params = new URLSearchParams()
      params.append('username', values.username)
      params.append('password', values.password)
      const res = await axios.post('/api/v1/auth/token', params, {
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      })
      const { access_token } = res.data
      // JWT payload에서 role 추출
      const payload = JSON.parse(atob(access_token.split('.')[1]))
      login(access_token, { username: values.username, role: payload.role as Role })
      navigate('/')
    } catch {
      message.error('로그인 실패: 아이디 또는 비밀번호를 확인하세요.')
    }
  }

  const fillDemo = (username: string) => {
    const passwords: Record<string, string> = {
      admin: 'KCS@admin2024',
      risk_manager: 'KCS@risk2024',
      compliance: 'KCS@comp2024',
      developer: 'KCS@dev2024',
    }
    form.setFieldsValue({ username, password: passwords[username] })
  }

  return (
    <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', background: '#f0f2f5' }}>
      <Card style={{ width: 400, boxShadow: '0 4px 24px rgba(0,0,0,0.1)' }}>
        <div style={{ textAlign: 'center', marginBottom: 24 }}>
          <Title level={3} style={{ margin: 0 }}>i뱅크 KCS POC</Title>
          <Text type="secondary">차세대 신용평가 시스템 데모</Text>
        </div>
        <Form form={form} onFinish={onFinish} layout="vertical">
          <Form.Item name="username" rules={[{ required: true, message: '아이디를 입력하세요' }]}>
            <Input prefix={<UserOutlined />} placeholder="아이디" size="large" />
          </Form.Item>
          <Form.Item name="password" rules={[{ required: true, message: '비밀번호를 입력하세요' }]}>
            <Input.Password prefix={<LockOutlined />} placeholder="비밀번호" size="large" />
          </Form.Item>
          <Form.Item>
            <Button type="primary" htmlType="submit" block size="large">
              로그인
            </Button>
          </Form.Item>
        </Form>
        <div>
          <Text type="secondary" style={{ fontSize: 12 }}>데모 계정 선택:</Text>
          <Select
            placeholder="데모 계정 선택"
            style={{ width: '100%', marginTop: 4 }}
            options={DEMO_ACCOUNTS}
            onChange={fillDemo}
          />
        </div>
      </Card>
    </div>
  )
}
