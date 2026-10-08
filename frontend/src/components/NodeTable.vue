<script setup lang="ts">
import Icon from './Icon.vue'
import StatusBadge from './StatusBadge.vue'
import type { SentinelNode } from '../types'
import { ago } from '../stores/workspace'
defineProps<{ nodes: SentinelNode[]; selectable?: boolean; selected?: string[]; filtered?: boolean }>()
defineEmits<{ detail: [id: string]; enroll: []; select: [id: string] }>()
</script>
<template>
  <div v-if="nodes.length" class="table-wrap"><table class="data-table"><thead><tr><th v-if="selectable">选择</th><th>节点 / 主机</th><th>出口 IP / 地区</th><th>连接状态</th><th>最近心跳</th><th>操作</th></tr></thead><tbody><tr v-for="node in nodes" :key="node.id"><td v-if="selectable"><input type="checkbox" :aria-label="'选择 ' + node.name" :checked="selected?.includes(node.id)" @change="$emit('select', node.id)"></td><td><div class="node-name"><span class="node-symbol"><Icon name="server" /></span><div><strong>{{ node.name }}</strong><small>{{ node.hostname || '等待 Agent 上报' }}</small></div></div></td><td><span class="mono">{{ node.metrics.public_ip || '尚未检测' }}</span><small class="table-sub">{{ node.region || node.metrics.country || '地区未设置' }}</small></td><td><StatusBadge :status="node.online ? 'online' : 'offline'" /></td><td class="muted">{{ ago(node.seen) }}</td><td><button class="btn plain" :aria-label="'管理 ' + node.name" @click="$emit('detail', node.id)"><Icon name="arrow" /></button></td></tr></tbody></table></div>
  <div v-else class="empty"><Icon name="server" /><h3>{{ filtered ? '没有匹配的节点' : '从第一个节点开始' }}</h3><p>{{ filtered ? '调整搜索词或连接状态筛选。' : '生成接入令牌，让服务器连接到你的控制台。' }}</p><button v-if="!filtered" class="btn primary" @click="$emit('enroll')"><Icon name="plus" />接入第一个节点</button></div>
</template>
