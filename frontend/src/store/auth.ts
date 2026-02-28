import { create } from 'zustand'
import { persist } from 'zustand/middleware'

export type Role = 'admin' | 'risk_manager' | 'compliance' | 'developer' | 'viewer'

interface User {
  username: string
  role: Role
}

interface AuthState {
  token: string | null
  user: User | null
  login: (token: string, user: User) => void
  logout: () => void
  isAuthenticated: () => boolean
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
      token: null,
      user: null,
      login: (token, user) => set({ token, user }),
      logout: () => set({ token: null, user: null }),
      isAuthenticated: () => !!get().token,
    }),
    { name: 'kcs-auth' }
  )
)

// Role -> 허용 메뉴 매핑
export const ROLE_MENUS: Record<string, string[]> = {
  admin: ['branch', 'marketing', 'product', 'risk', 'policy'],
  risk_manager: ['risk', 'product'],
  compliance: ['policy', 'risk'],
  developer: ['branch', 'marketing'],
  viewer: ['branch'],
}
