<script setup lang="ts">
import Icon from './Icon.vue'
import type { AuditEvent } from '../types'
import { when } from '../stores/workspace'
defineProps<{ events: AuditEvent[] }>()
</script>
<template><div v-if="events.length" class="events"><div v-for="event in events" :key="event.id" class="event"><span class="event-indicator"><Icon :name="event.kind.includes('failed') || event.kind.includes('offline') ? 'bell' : 'check'" /></span><div><p>{{ event.message }}</p><small>{{ when(event.created) }}</small></div></div></div><div v-else class="empty"><h3>一切准备就绪</h3><p>节点接入和操作结果会记录在这里。</p></div></template>
