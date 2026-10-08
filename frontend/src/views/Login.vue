<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { auth, login } from '../stores/auth'
import Icon from '../components/Icon.vue'
const router = useRouter(), username = ref('admin'), password = ref(''), error = ref(''), busy = ref(false)
async function submit() { busy.value = true; error.value = ''; try { await login(username.value, password.value); password.value = ''; await router.replace(auth.must_change_password ? '/change-password' : '/') } catch (e) { error.value = (e as Error).message } finally { busy.value = false } }
</script>
<template><main class="login-shell"><section class="login-intro"><div class="brand"><img src="/favicon.svg" alt=""><div><strong>VPS Sentinel</strong><small>CONTROL PLANE</small></div></div><h1>每一个节点，<br>都在掌控之中。</h1><p>连接分散各地的服务器。<br>在一个清晰的控制台中，了解状态、安排任务、追踪结果。</p><div class="login-caption">YOUR INFRASTRUCTURE. ONE CLEAR VIEW.</div><div class="login-orbit" /></section><section class="login-form-wrap"><form class="login-form" @submit.prevent="submit"><h2>欢迎回来</h2><p>登录 VPS Sentinel，查看哨兵与节点状态。</p><div v-if="!auth.configured" class="note">主控尚未初始化。请完成一键安装，或使用管理员初始化命令。</div><div class="field"><label for="username">用户名</label><input id="username" v-model="username" required maxlength="64" autocomplete="username"></div><div class="field"><label for="password">密码</label><input id="password" v-model="password" type="password" required maxlength="256" autocomplete="current-password" placeholder="输入安装脚本打印的初始密码"></div><div class="form-error" role="alert">{{ error }}</div><button class="btn primary" :disabled="busy || !auth.configured">{{ busy ? '正在登录…' : '进入控制台' }}<Icon name="arrow" /></button><div class="login-foot">私有部署 · 数据由你掌控</div></form></section></main></template>
