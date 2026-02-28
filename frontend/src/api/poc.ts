import client from './client'

export const pocApi = {
  dashboard: {
    branch: () => client.get('/poc/dashboard/branch'),
    marketing: () => client.get('/poc/dashboard/marketing'),
    risk: () => client.get('/poc/dashboard/risk'),
    product: () => client.get('/poc/dashboard/product'),
    policy: () => client.get('/poc/dashboard/policy'),
  },
  applications: {
    list: (params?: Record<string, unknown>) => client.get('/poc/applications', { params }),
    get: (id: string) => client.get(`/poc/applications/${id}`),
  },
  prescore: (data: Record<string, unknown>) => client.post('/poc/prescore', data),
  auditTrail: (params?: Record<string, unknown>) => client.get('/poc/audit-trail', { params }),
  complianceStatus: () => client.get('/poc/compliance-status'),
  stressTest: (data: Record<string, unknown>) => client.post('/poc/stress-test', data),
  segmentStats: () => client.get('/poc/segment-stats'),
}
