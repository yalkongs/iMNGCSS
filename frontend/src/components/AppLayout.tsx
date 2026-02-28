import { Outlet, useNavigate, useLocation } from 'react-router-dom'
import { Layout, Menu, Avatar, Dropdown, Typography, theme } from 'antd'
import {
  HomeOutlined, TeamOutlined, BarChartOutlined, DollarOutlined,
  AlertOutlined, AuditOutlined, LogoutOutlined, UserOutlined,
} from '@ant-design/icons'
import { useAuthStore, ROLE_MENUS } from '../store/auth'
import NotificationCenter from './NotificationCenter'

const { Sider, Header, Content } = Layout
const { Text } = Typography

const ALL_MENUS = [
  {
    key: 'branch',
    icon: <HomeOutlined />,
    label: '영업점',
    children: [
      { key: '/branch', label: '대시보드' },
      { key: '/branch/applications', label: '신청 목록' },
      { key: '/branch/application-form', label: '신청 접수 (7단계)' },
      { key: '/branch/result', label: '심사 결과 조회' },
      { key: '/branch/appeal', label: '이의제기 관리' },
    ],
  },
  {
    key: 'marketing',
    icon: <TeamOutlined />,
    label: '비대면 마케팅',
    children: [
      { key: '/marketing', label: '대시보드' },
      { key: '/marketing/prescore', label: '사전심사 (Shadow)' },
      { key: '/marketing/segment', label: '세그먼트 현황' },
      { key: '/marketing/campaign', label: '캠페인 분석' },
    ],
  },
  {
    key: 'product',
    icon: <DollarOutlined />,
    label: '상품(여신)',
    children: [
      { key: '/product', label: '대시보드' },
      { key: '/product/eq-grade', label: 'EQ Grade 관리' },
      { key: '/product/irg', label: 'IRG 현황' },
      { key: '/product/rate-simulation', label: '금리 시뮬레이션' },
      { key: '/product/profitability', label: '고객 수익성 (RAROC/CLV)' },
    ],
  },
  {
    key: 'risk',
    icon: <AlertOutlined />,
    label: '리스크',
    children: [
      { key: '/risk', label: '리스크 대시보드' },
      { key: '/risk/ews', label: 'EWS 조기경보' },
      { key: '/risk/psi', label: 'PSI 모니터링' },
      { key: '/risk/calibration', label: '칼리브레이션' },
      { key: '/risk/vintage', label: '빈티지 분석' },
      { key: '/risk/stress-test', label: '스트레스 테스트' },
      { key: '/risk/portfolio-concentration', label: '포트폴리오 집중도' },
      { key: '/risk/score-distribution', label: '점수 분포' },
    ],
  },
  {
    key: 'policy',
    icon: <AuditOutlined />,
    label: '여신 정책',
    children: [
      { key: '/policy', label: '정책 대시보드' },
      { key: '/policy/brms', label: 'BRMS 파라미터' },
      { key: '/policy/compliance', label: '규제 준수 현황' },
      { key: '/policy/audit', label: '감사 추적' },
      { key: '/policy/simulation', label: '정책 시뮬레이션' },
    ],
  },
]

export default function AppLayout() {
  const navigate = useNavigate()
  const location = useLocation()
  const { user, logout } = useAuthStore()
  const { token: { colorBgContainer } } = theme.useToken()

  const allowedMenus = ROLE_MENUS[user?.role ?? 'viewer'] ?? []
  const menus = ALL_MENUS.filter((m) => allowedMenus.includes(m.key))

  const selectedKey = location.pathname
  const openKey = ALL_MENUS.find((m) =>
    m.children.some((c) => location.pathname.startsWith('/' + c.key.split('/')[1]))
  )?.key

  const userMenuItems = [
    {
      key: 'logout',
      icon: <LogoutOutlined />,
      label: '로그아웃',
      onClick: () => { logout(); navigate('/login') },
    },
  ]

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Sider width={220} theme="dark" collapsible>
        <div style={{ padding: '16px', color: '#fff', fontWeight: 700, fontSize: 15, borderBottom: '1px solid #333' }}>
          <BarChartOutlined style={{ marginRight: 8 }} />
          i뱅크 KCS POC
        </div>
        <Menu
          theme="dark"
          mode="inline"
          selectedKeys={[selectedKey]}
          defaultOpenKeys={openKey ? [openKey] : []}
          items={menus}
          onClick={({ key }) => navigate(key)}
        />
      </Sider>
      <Layout>
        <Header style={{
          background: '#1677ff', padding: '0 24px',
          display: 'flex', alignItems: 'center', justifyContent: 'flex-end', gap: 16,
        }}>
          <NotificationCenter />
          <Dropdown menu={{ items: userMenuItems }} placement="bottomRight">
            <span style={{ cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 8 }}>
              <Avatar icon={<UserOutlined />} size="small" style={{ background: '#fff', color: '#1677ff' }} />
              <Text style={{ color: '#fff', fontWeight: 600 }}>{user?.username}</Text>
              <Text style={{ color: 'rgba(255,255,255,0.7)', fontSize: 12 }}>({user?.role})</Text>
            </span>
          </Dropdown>
        </Header>
        <Content style={{ margin: '24px', background: colorBgContainer, padding: 24, borderRadius: 8 }}>
          <Outlet />
        </Content>
      </Layout>
    </Layout>
  )
}
