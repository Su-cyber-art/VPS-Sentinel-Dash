<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { router } from './router'
import { loadSession } from './stores/auth'
import { notification } from './stores/workspace'
const error = ref('')
function reload() { window.location.reload() }
async function handleAuth() { await loadSession(true); await router.replace('/') }
router.onError(value => { error.value = value.message || '无法连接后端' })
onMounted(() => window.addEventListener('sentinel:auth', handleAuth))
onUnmounted(() => window.removeEventListener('sentinel:auth', handleAuth))
</script>
<template>
  <div v-if="error" class="boot"><p>{{ error }}</p><button class="btn" @click="reload">重新连接</button></div>
  <RouterView v-else />
  <div id="toast" role="status" aria-live="polite" :class="{ visible: notification.text }">{{ notification.text }}</div>
</template>
