let csrf = ''
const base = import.meta.env.VITE_API_BASE || ''
export function setCsrf(value: string) { csrf = value }
export class ApiError extends Error {
  constructor(message: string, public code: string, public status: number) { super(message) }
}
export async function api<T>(path: string, method = 'GET', data?: unknown): Promise<T> {
  const response = await fetch(base + '/api' + path, {
    method, credentials: 'include',
    headers: method === 'GET' ? {} : { 'Content-Type': 'application/json', 'X-CSRF-Token': csrf },
    body: method === 'GET' ? undefined : JSON.stringify(data ?? {}),
  })
  const result = await response.json().catch(() => ({ error: '后端返回了无效响应，请检查服务状态' }))
  if (!response.ok) {
    if (result.code === 'password_change_required' || (response.status === 401 && path !== '/auth/login')) {
      window.dispatchEvent(new CustomEvent('sentinel:auth', { detail: result.code }))
    }
    const fields = result.fields?.map((f: { message: string }) => f.message).join('；')
    throw new ApiError(fields || result.error || '请求失败', result.code || 'request_error', response.status)
  }
  return result as T
}
