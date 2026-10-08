<script setup lang="ts">
import { onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import Icon from './Icon.vue'
import { auth, logout } from '../stores/auth'
import { workspace, startPolling, stopPolling, toast } from '../stores/workspace'
const route = useRoute(), router = useRouter()
const navigation = [ ['/', '运行概览', 'grid'], ['/nodes', '节点管理', 'server'], ['/tasks', '任务记录', 'clock'], ['/events', '事件日志', 'list'], ['/settings', '控制台设置', 'settings'] ]
onMounted(startPolling)
onUnmounted(stopPolling)
async function signOut() { try { await logout(); await router.replace('/login') } catch (error) { toast((error as Error).message) } }
</script>
<template>
  <div class="shell">
    <aside class="sidebar">
      <RouterLink to="/" class="brand"><img src="/favicon.svg" alt=""><div><strong>VPS Sentinel</strong><small>CONTROL PLANE</small></div></RouterLink>
      <div class="nav-label">WORKSPACE</div>
      <nav aria-label="主导航"><RouterLink v-for="[url, label, icon] in navigation" :key="url" :to="url!" class="nav-link" :class="{ active: route.path === url }" :aria-current="route.path === url ? 'page' : undefined"><Icon :name="icon!" /><span>{{ label }}</span><span v-if="url === '/nodes'" class="count">{{ workspace.data?.nodes.length ?? 0 }}</span></RouterLink></nav>
      <div class="sidebar-bottom"><div class="system-status"><span class="dot" :class="{ off: workspace.error }" />{{ workspace.error ? '主控连接中断' : '主控已连接' }}</div><small>VPS SENTINEL / v{{ workspace.data?.version || '0.2.0' }}</small></div>
    </aside>
    <div class="shell-main">
      <header class="topbar"><div class="breadcrumb">工作空间 <Icon name="arrow" /><strong>{{ route.meta.title }}</strong></div><RouterLink to="/" class="mobile-brand"><img src="/favicon.svg" alt="">VPS Sentinel</RouterLink><div class="top-right"><span class="live"><span class="dot" :class="{ off: workspace.error }" />{{ workspace.error ? '等待重连' : '实时同步' }}</span><span class="avatar" :title="auth.username">{{ auth.username?.slice(0, 2).toUpperCase() }}</span><button class="btn plain" aria-label="退出登录" @click="signOut"><Icon name="logout" /></button></div></header>
      <main class="page"><div v-if="workspace.error" class="banner-error" role="alert">同步失败：{{ workspace.error }}</div><RouterView /><footer class="footer"><span>VPS Sentinel Dash · 每个节点，都在掌控之中</span><a href="https://github.com/Su-cyber-art/VPS-Sentinel-Dash" target="_blank" rel="noopener">开源项目 · AGPL-3.0</a></footer></main>
    </div>
  </div>
</template>
