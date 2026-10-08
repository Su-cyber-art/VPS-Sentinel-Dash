<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { changePassword, logout } from '../stores/auth'
import Icon from '../components/Icon.vue'
const router = useRouter(), current = ref(''), password = ref(''), confirm = ref(''), error = ref(''), busy = ref(false)
async function submit() {
  if (password.value !== confirm.value) { error.value = '两次输入的新密码不一致'; return }
  busy.value = true; error.value = ''
  try { await changePassword(current.value, password.value); current.value = ''; password.value = ''; confirm.value = ''; await router.replace('/') }
  catch (e) { error.value = (e as Error).message } finally { busy.value = false }
}
async function exit() { try { await logout(); await router.replace('/login') } catch (e) { error.value = (e as Error).message } }
</script>
<template><main class="password-page"><form class="password-card" @submit.prevent="submit"><span class="security-icon"><Icon name="shield" /></span><div class="eyebrow">首次登录</div><h1>设置你的专属密码</h1><p class="muted">完成密码修改后，才能查看节点和执行哨兵操作。</p><div class="field"><label for="initial-password">初始 / 当前密码</label><input id="initial-password" v-model="current" type="password" required autocomplete="current-password" maxlength="256"></div><div class="field"><label for="new-password">新密码</label><input id="new-password" v-model="password" type="password" minlength="12" maxlength="256" required autocomplete="new-password" placeholder="至少 12 个字符，与初始密码不同"></div><div class="field"><label for="confirm-password">确认新密码</label><input id="confirm-password" v-model="confirm" type="password" minlength="12" maxlength="256" required autocomplete="new-password"></div><div class="form-error" role="alert">{{ error }}</div><button class="btn primary full-width" :disabled="busy">{{ busy ? '正在保存…' : '修改密码并进入面板' }}<Icon name="arrow" /></button><button type="button" class="btn plain full-width mt-12" @click="exit">退出登录</button></form></main></template>
