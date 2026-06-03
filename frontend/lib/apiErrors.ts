import { AxiosError } from 'axios'

type ApiErrorBody = { detail?: string | { msg?: string }[]; message?: string }

export function extractApiError(err: unknown, fallback = 'Something went wrong'): string {
  if (err instanceof AxiosError) {
    const data = err.response?.data as ApiErrorBody | string | undefined
    if (typeof data === 'string' && data.trim()) return data
    if (data && typeof data === 'object') {
      if (typeof data.message === 'string' && data.message.trim()) return data.message
      if (typeof data.detail === 'string' && data.detail.trim()) return data.detail
      if (Array.isArray(data.detail) && data.detail.length > 0) {
        const first = data.detail[0]
        if (typeof first === 'string') return first
        if (first && typeof first === 'object' && typeof first.msg === 'string') return first.msg
      }
    }
    if (err.message) return err.message
  }
  if (err instanceof Error && err.message) return err.message
  return fallback
}
