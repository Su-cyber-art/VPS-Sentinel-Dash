import { reactive } from 'vue'
import { api, setCsrf } from '../api'
import type { Session } from '../types'

export const auth = reactive<Session & { loaded: boolean }>({ configured: true, authenticated: false, must_change_password: false, loaded: false })
let loading: Promise<void> | null = null
export function applySession(session: Session) { Object.assign(auth, session, { loaded: true }); setCsrf(session.csrf || '') }
export async function loadSession(force = false) {
  if (auth.loaded && !force) return
  if (!loading) loading = api<Session>('/auth/session').then(applySession).finally(() => { loading = null })
  await loading
}
export async function login(username: string, password: string) {
  applySession(await api<Session>('/auth/login', 'POST', { username, password }))
}
export async function changePassword(current_password: string, new_password: string) {
  applySession(await api<Session>('/auth/password', 'POST', { current_password, new_password }))
}
export async function logout() {
  await api('/auth/logout', 'POST')
  applySession({ configured: true, authenticated: false, must_change_password: false })
}
