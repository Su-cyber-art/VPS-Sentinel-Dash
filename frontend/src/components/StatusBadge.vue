<script setup lang="ts">
defineProps<{ status: string }>()
const labels: Record<string, string> = { online: '在线', offline: '离线', queued: '待执行', running: '执行中', succeeded: '已完成', failed: '失败', cancelled: '已取消' }
</script>
<template><span class="status" :class="status"><span class="dot" :class="{ off: ['offline', 'queued', 'cancelled'].includes(status) }" />{{ labels[status] || status }}</span></template>
