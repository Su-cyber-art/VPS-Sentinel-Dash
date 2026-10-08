<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api } from '../api'
import type { Settings } from '../types'
import { changePassword } from '../stores/auth'
import { toast } from '../stores/workspace'
import PageHeading from '../components/PageHeading.vue'
import Icon from '../components/Icon.vue'
const settings = ref<Settings | null>(null), error = ref(''), current = ref(''), password = ref(''), confirmation = ref(''), busy = ref(false)
const address = window.location.origin
onMounted(async () => { try { settings.value = await api('/settings') } catch (e) { error.value = (e as Error).message } })
async function notifications() { try { await api('/settings', 'PUT', { telegram_enabled: settings.value?.telegram_enabled }); toast('通知设置已保存') } catch (e) { error.value = (e as Error).message } }
async function change() {
  if (password.value !== confirmation.value) { error.value = '两次输入的新密码不一致'; return }
  busy.value = true; error.value = ''
  try { await changePassword(current.value, password.value); current.value = ''; password.value = ''; confirmation.value = ''; toast('密码已更新，其他会话已退出') }
  catch (e) { error.value = (e as Error).message } finally { busy.value = false }
}
</script>
<template><PageHeading title="控制台设置" subtitle="管理通知和访问凭证。" /><div v-if="error" class="banner-error" role="alert">{{ error }}</div><div class="settings-grid"><section class="card"><div class="card-head"><h2><Icon name="bell" />Telegram 通知</h2><span class="status" :class="{ offline: !settings?.telegram_configured }">{{ settings?.telegram_configured ? '已配置' : '未配置' }}</span></div><form class="settings-body" @submit.prevent="notifications"><p>在节点离线、恢复连接或任务失败时发送通知。节点操作在网页完成。</p><label v-if="settings" class="toggle-line"><span><strong>启用通知</strong><small>{{ settings.telegram_configured ? '主控已读取通知凭证' : '在主控环境文件中配置 TELEGRAM_BOT_TOKEN 与 TELEGRAM_CHAT_ID 后重启后端' }}</small></span><input v-model="settings.telegram_enabled" type="checkbox" :disabled="!settings.telegram_configured"></label><button class="btn primary" :disabled="!settings">保存通知设置</button></form></section><section class="card"><div class="card-head"><h2><Icon name="shield" />访问管理</h2></div><form class="settings-body" @submit.prevent="change"><p>修改密码后，其他设备上的登录会话将失效。</p><div class="field"><label for="current-password">当前密码</label><input id="current-password" v-model="current" type="password" required autocomplete="current-password"></div><div class="field"><label for="settings-password">新密码</label><input id="settings-password" v-model="password" type="password" minlength="12" maxlength="256" required autocomplete="new-password"></div><div class="field"><label for="settings-confirm">确认新密码</label><input id="settings-confirm" v-model="confirmation" type="password" minlength="12" maxlength="256" required autocomplete="new-password"></div><button class="btn" :disabled="busy">更新密码</button></form></section><section class="card"><div class="card-head"><h2>主控信息</h2></div><div class="settings-body"><div class="settings-row"><span class="muted">版本</span><span class="mono">{{ settings?.version || '—' }}</span></div><div class="settings-row"><span class="muted">Agent 接入地址</span><span class="mono">{{ settings?.public_url || address }}</span></div><div class="settings-row"><span class="muted">部署方式</span><span>独立前端与后端 · SQLite</span></div></div></section></div></template>
