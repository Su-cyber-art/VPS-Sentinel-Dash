import { reactive } from 'vue'
import { api } from '../api'
import type { Overview } from '../types'
export const workspace = reactive<{ data: Overview | null; error: string; loading: boolean }>({ data: null, error: '', loading: false })
let timer: ReturnType<typeof setInterval> | null = null
export async function refresh() {
  if (workspace.loading) return
  workspace.loading = true
  try { workspace.data = await api<Overview>('/overview'); workspace.error = '' }
  catch (error) { workspace.error = (error as Error).message }
  finally { workspace.loading = false }
}
export function startPolling() { void refresh(); if (!timer) timer = setInterval(() => void refresh(), 5000) }
export function stopPolling() { if (timer) clearInterval(timer); timer = null; workspace.data = null }
export const notification = reactive({ text: '' })
let toastTimer: ReturnType<typeof setTimeout>
export function toast(text: string) { notification.text = text; clearTimeout(toastTimer); toastTimer = setTimeout(() => { notification.text = '' }, 3500) }
export function when(value?: number | null) { return value ? new Date(value * 1000).toLocaleString('zh-CN', { hour12: false }) : '—' }
export function ago(value: number) {
  if (!value) return '等待心跳'
  const seconds = Math.max(0, Math.floor(Date.now() / 1000 - value))
  return seconds < 5 ? '刚刚' : seconds < 60 ? `${seconds} 秒前` : seconds < 3600 ? `${Math.floor(seconds / 60)} 分钟前` : `${Math.floor(seconds / 3600)} 小时前`
}
