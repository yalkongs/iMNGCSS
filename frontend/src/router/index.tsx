import { createBrowserRouter, Navigate } from 'react-router-dom'
import AppLayout from '../components/AppLayout'
import Login from '../pages/Login'
import BranchDashboard from '../pages/Branch/Dashboard'
import BranchApplications from '../pages/Branch/Applications'
import BranchResult from '../pages/Branch/Result'
import BranchApplicationForm from '../pages/Branch/ApplicationForm'
import BranchAppeal from '../pages/Branch/Appeal'
import MarketingDashboard from '../pages/Marketing/Dashboard'
import MarketingPrescore from '../pages/Marketing/Prescore'
import MarketingSegment from '../pages/Marketing/Segment'
import MarketingCampaign from '../pages/Marketing/Campaign'
import ProductDashboard from '../pages/Product/Dashboard'
import ProductEQGrade from '../pages/Product/EQGrade'
import ProductIRG from '../pages/Product/IRG'
import ProductRateSimulation from '../pages/Product/RateSimulation'
import ProductProfitability from '../pages/Product/Profitability'
import RiskDashboard from '../pages/Risk/Dashboard'
import RiskPSI from '../pages/Risk/PSI'
import RiskCalibration from '../pages/Risk/Calibration'
import RiskVintage from '../pages/Risk/Vintage'
import RiskStressTest from '../pages/Risk/StressTest'
import RiskEWS from '../pages/Risk/EWS'
import RiskPortfolioConcentration from '../pages/Risk/PortfolioConcentration'
import RiskScoreDistribution from '../pages/Risk/ScoreDistribution'
import PolicyDashboard from '../pages/Policy/Dashboard'
import PolicyBRMS from '../pages/Policy/BRMS'
import PolicyCompliance from '../pages/Policy/Compliance'
import PolicyAudit from '../pages/Policy/Audit'
import PolicySimulation from '../pages/Policy/PolicySimulation'
import ProtectedRoute from '../components/ProtectedRoute'

export const router = createBrowserRouter([
  {
    path: '/login',
    element: <Login />,
  },
  {
    path: '/',
    element: <ProtectedRoute><AppLayout /></ProtectedRoute>,
    children: [
      { index: true, element: <Navigate to="/branch" replace /> },
      // 영업점
      { path: 'branch', element: <BranchDashboard /> },
      { path: 'branch/applications', element: <BranchApplications /> },
      { path: 'branch/application-form', element: <BranchApplicationForm /> },
      { path: 'branch/result', element: <BranchResult /> },
      { path: 'branch/appeal', element: <BranchAppeal /> },
      // 비대면 마케팅
      { path: 'marketing', element: <MarketingDashboard /> },
      { path: 'marketing/prescore', element: <MarketingPrescore /> },
      { path: 'marketing/segment', element: <MarketingSegment /> },
      { path: 'marketing/campaign', element: <MarketingCampaign /> },
      // 상품(여신)
      { path: 'product', element: <ProductDashboard /> },
      { path: 'product/eq-grade', element: <ProductEQGrade /> },
      { path: 'product/irg', element: <ProductIRG /> },
      { path: 'product/rate-simulation', element: <ProductRateSimulation /> },
      { path: 'product/profitability', element: <ProductProfitability /> },
      // 리스크
      { path: 'risk', element: <RiskDashboard /> },
      { path: 'risk/psi', element: <RiskPSI /> },
      { path: 'risk/calibration', element: <RiskCalibration /> },
      { path: 'risk/vintage', element: <RiskVintage /> },
      { path: 'risk/stress-test', element: <RiskStressTest /> },
      { path: 'risk/ews', element: <RiskEWS /> },
      { path: 'risk/portfolio-concentration', element: <RiskPortfolioConcentration /> },
      { path: 'risk/score-distribution', element: <RiskScoreDistribution /> },
      // 여신 정책
      { path: 'policy', element: <PolicyDashboard /> },
      { path: 'policy/brms', element: <PolicyBRMS /> },
      { path: 'policy/compliance', element: <PolicyCompliance /> },
      { path: 'policy/audit', element: <PolicyAudit /> },
      { path: 'policy/simulation', element: <PolicySimulation /> },
    ],
  },
])
