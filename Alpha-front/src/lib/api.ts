import axios from 'axios'
import type { AxiosError } from 'axios'

import type { ApiEnvelope, ApiErrorBody } from '@/lib/types'

export const AUTH_TOKEN_KEY = 'auth_token'
export const AUTH_USER_KEY = 'auth_user'

const configuredBaseUrl = import.meta.env.VITE_API_URL
const baseURL = (
  configuredBaseUrl && configuredBaseUrl.trim()
    ? configuredBaseUrl
    : window.location.origin
).replace(/\/$/, '')

export const api = axios.create({
  baseURL,
  headers: {
    'Content-Type': 'application/json',
  },
})

api.interceptors.request.use((config) => {
  const token = localStorage.getItem(AUTH_TOKEN_KEY)
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

api.interceptors.response.use(
  (response) => {
    const body = response.data
    if (body && typeof body === 'object' && 'data' in body) {
      response.data = (body as ApiEnvelope<unknown>).data
    }
    return response
  },
  (error: AxiosError<ApiErrorBody>) => {
    if (error.response?.status === 401) {
      localStorage.removeItem(AUTH_TOKEN_KEY)
      localStorage.removeItem(AUTH_USER_KEY)

      if (window.location.pathname !== '/login') {
        window.location.assign('/login')
      }
    }
    return Promise.reject(error)
  },
)

function createIdempotencyKey() {
  if (typeof globalThis.crypto?.randomUUID === 'function') {
    return globalThis.crypto.randomUUID()
  }

  if (typeof globalThis.crypto?.getRandomValues === 'function') {
    const bytes = new Uint8Array(16)
    globalThis.crypto.getRandomValues(bytes)
    bytes[6] = (bytes[6] & 0x0f) | 0x40
    bytes[8] = (bytes[8] & 0x3f) | 0x80
    const hex = Array.from(bytes, (byte) =>
      byte.toString(16).padStart(2, '0'),
    ).join('')
    return [
      hex.slice(0, 8),
      hex.slice(8, 12),
      hex.slice(12, 16),
      hex.slice(16, 20),
      hex.slice(20),
    ].join('-')
  }

  return `${Date.now()}-${Math.random().toString(16).slice(2)}`
}

export function apiMutation<T>(
  method: 'POST' | 'PATCH' | 'DELETE',
  url: string,
  data?: unknown,
) {
  return api.request<T>({
    method,
    url,
    data,
    headers: {
      'Idempotency-Key': createIdempotencyKey(),
    },
  })
}

export function getApiErrorMessage(
  error: unknown,
  fallback = 'Не удалось выполнить запрос',
) {
  if (!axios.isAxiosError<ApiErrorBody>(error)) {
    return fallback
  }
  if (!error.response) {
    return 'Нет соединения. Проверьте интернет.'
  }
  if (error.response.status >= 500) {
    return 'Сервис временно недоступен. Попробуйте через минуту.'
  }
  return error.response.data?.error?.message ?? fallback
}
