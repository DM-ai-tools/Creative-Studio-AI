import Cookies from 'js-cookie'
import type { User } from '@/types'

const ACCESS_TOKEN_KEY = 'cs_access_token'
const REFRESH_TOKEN_KEY = 'cs_refresh_token'
const USER_KEY = 'cs_user'

export const authStorage = {
  setTokens(access: string, refresh: string) {
    Cookies.set(ACCESS_TOKEN_KEY, access, { expires: 1, sameSite: 'lax' })
    Cookies.set(REFRESH_TOKEN_KEY, refresh, { expires: 7, sameSite: 'lax' })
  },

  getAccessToken(): string | undefined {
    return Cookies.get(ACCESS_TOKEN_KEY)
  },

  getRefreshToken(): string | undefined {
    return Cookies.get(REFRESH_TOKEN_KEY)
  },

  setUser(user: User) {
    if (typeof window !== 'undefined') {
      localStorage.setItem(USER_KEY, JSON.stringify(user))
    }
  },

  getUser(): User | null {
    if (typeof window === 'undefined') return null
    try {
      const raw = localStorage.getItem(USER_KEY)
      return raw ? (JSON.parse(raw) as User) : null
    } catch {
      return null
    }
  },

  clear() {
    Cookies.remove(ACCESS_TOKEN_KEY)
    Cookies.remove(REFRESH_TOKEN_KEY)
    if (typeof window !== 'undefined') {
      localStorage.removeItem(USER_KEY)
    }
  },
}
