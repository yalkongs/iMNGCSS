import { RouterProvider } from 'react-router-dom'
import { ConfigProvider } from 'antd'
import koKR from 'antd/locale/ko_KR'
import { router } from './router'

export default function App() {
  return (
    <ConfigProvider locale={koKR}>
      <RouterProvider router={router} />
    </ConfigProvider>
  )
}
