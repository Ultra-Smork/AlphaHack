import { createContext, useCallback, useContext, useMemo, useState } from 'react'
import type { ReactNode } from 'react'

import { api, AUTH_TOKEN_KEY, AUTH_USER_KEY } from '@/lib/api'
import type { JwtPayload, LoginResponse, User } from '@/lib/types'

interface AuthContextValue {
  user: User | null
  token: string | null
  isAuthenticated: boolean
  login: (email: string, password: string) => Promise<User>
  logout: () => void
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined)

function decodeJwt(token: string): JwtPayload {
  const encoded = token.split('.')[1]
  if (!encoded) {
    throw new Error('Некорректный токен')
  }

  const base64 = encoded.replace(/-/g, '+').replace(/_/g, '/')
  const padded = base64.padEnd(Math.ceil(base64.length / 4) * 4, '=')
  return JSON.parse(atob(padded)) as JwtPayload
}

function readStoredUser(): User | null {
  const raw = localStorage.getItem(AUTH_USER_KEY)
  if (!raw) {
    return null
  }

  try {
    const parsed = JSON.parse(raw) as Partial<User>
    if (typeof parsed.id === 'number' && typeof parsed.email === 'string') {
      return {
        id: parsed.id,
        email: parsed.email,
      }
    }
  } catch {
    // Invalid storage is cleared below.
  }

  localStorage.removeItem(AUTH_USER_KEY)
  return null
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setToken] = useState<string | null>(() =>
    localStorage.getItem(AUTH_TOKEN_KEY),
  )
  const [user, setUser] = useState<User | null>(() => readStoredUser())

  const login = useCallback(async (email: string, password: string) => {
    const response = await api.post<LoginResponse>('/api/auth/login', {
      email,
      password,
    })
    const payload = response.data
    const claims = decodeJwt(payload.access_token)

    const rawId = payload.user_id ?? claims.sub ?? claims.uid
    const id = Number(rawId)
    if (!Number.isFinite(id)) {
      throw new Error('В токене отсутствует идентификатор пользователя')
    }

    const nextUser: User = {
      id,
      email: payload.email ?? email,
    }

    localStorage.setItem(AUTH_TOKEN_KEY, payload.access_token)
    localStorage.setItem(AUTH_USER_KEY, JSON.stringify(nextUser))
    setToken(payload.access_token)
    setUser(nextUser)
    return nextUser
  }, [])

  const logout = useCallback(() => {
    localStorage.removeItem(AUTH_TOKEN_KEY)
    localStorage.removeItem(AUTH_USER_KEY)
    setToken(null)
    setUser(null)
  }, [])

  const value = useMemo<AuthContextValue>(
    () => ({
      user,
      token,
      isAuthenticated: Boolean(token && user),
      login,
      logout,
    }),
    [token, user, login, logout],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

// eslint-disable-next-line react-refresh/only-export-components
export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) {
    throw new Error('useAuth must be used within AuthProvider')
  }
  return context
}
