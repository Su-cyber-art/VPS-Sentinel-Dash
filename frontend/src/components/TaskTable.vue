<script setup lang="ts">
import Icon from './Icon.vue'
import StatusBadge from './StatusBadge.vue'
import { actions, type Task } from '../types'
import { when } from '../stores/workspace'
defineProps<{ tasks: Task[] }>()
defineEmits<{ detail: [id: string] }>()
</script>
<template><div v-if="tasks.length" class="table-wrap"><table class="data-table"><thead><tr><th>任务</th><th>节点</th><th>状态</th><th>创建时间</th><th>结果</th></tr></thead><tbody><tr v-for="task in tasks" :key="task.id"><td><strong class="medium">{{ actions[task.action] }}</strong><small class="table-sub">{{ task.source === 'schedule' ? '定时任务' : '手动任务' }}</small></td><td>{{ task.node_name || '已移除节点' }}</td><td><StatusBadge :status="task.status" /><small v-if="task.cancel_requested && task.status === 'running'" class="table-sub">正在请求取消</small></td><td class="muted mono">{{ when(task.created) }}</td><td><button class="btn plain" aria-label="查看任务结果" @click="$emit('detail', task.id)"><Icon name="arrow" /></button></td></tr></tbody></table></div><div v-else class="empty"><Icon name="clock" /><h3>还没有任务记录</h3><p>在节点详情中执行哨兵操作，结果会保存在这里。</p></div></template>
