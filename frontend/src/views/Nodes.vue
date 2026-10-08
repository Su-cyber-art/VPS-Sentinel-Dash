<script setup lang="ts">
import { computed, ref } from 'vue'
import { api } from '../api'
import { actions, type Action } from '../types'
import { workspace, refresh, toast } from '../stores/workspace'
import PageHeading from '../components/PageHeading.vue'
import NodeTable from '../components/NodeTable.vue'
import NodeDrawer from '../components/NodeDrawer.vue'
import EnrollmentDialog from '../components/EnrollmentDialog.vue'
import TaskDialog from '../components/TaskDialog.vue'
import Icon from '../components/Icon.vue'
const query = ref(''), status = ref('all'), selected = ref<string[]>([]), action = ref<Action>('snapshot')
const node = ref<string | null>(null), task = ref<string | null>(null), enroll = ref(false), busy = ref(false)
const actionKeys = Object.keys(actions) as Action[]
const nodes = computed(() => workspace.data?.nodes.filter(n => (status.value === 'all' || n.online === (status.value === 'online')) && [n.name, n.hostname, n.region, n.group_name, n.metrics.public_ip].join(' ').toLowerCase().includes(query.value.toLowerCase())) || [])
function select(id: string) { selected.value = selected.value.includes(id) ? selected.value.filter(x => x !== id) : [...selected.value, id] }
async function batch() { busy.value = true; try { const value = await api<{ results: { id?: string; error?: string }[] }>('/jobs/batch', 'POST', { action: action.value, node_ids: selected.value }); const failed = value.results.filter(r => r.error); toast(`已提交 ${value.results.length - failed.length} 个任务${failed.length ? `；${failed.length} 个失败：${failed[0]!.error}` : ''}`); await refresh() } catch (e) { toast((e as Error).message) } finally { busy.value = false } }
</script>
<template><PageHeading title="节点管理" subtitle="连接服务器、配置策略，远程执行哨兵操作。" add @enroll="enroll = true" /><section class="card"><div class="filters"><div class="search"><Icon name="search" /><input v-model="query" aria-label="搜索节点" placeholder="搜索名称、IP、主机或分组…"></div><select v-model="status" aria-label="筛选连接状态"><option value="all">全部状态</option><option value="online">在线</option><option value="offline">离线</option></select></div><div v-if="selected.length" class="batch-toolbar"><span>已选 {{ selected.length }} 个节点</span><select v-model="action" aria-label="批量操作"><option v-for="key in actionKeys" :key="key" :value="key">{{ actions[key] }}</option></select><button class="btn primary" :disabled="busy" @click="batch">批量执行</button><button class="btn plain" @click="selected = []">清除选择</button></div><NodeTable :nodes="nodes" selectable :selected="selected" :filtered="!!query || status !== 'all'" @select="select" @detail="node = $event" @enroll="enroll = true" /></section><EnrollmentDialog :open="enroll" @close="enroll = false" /><NodeDrawer :id="node" @close="node = null" @task="task = $event" /><TaskDialog :id="task" @close="task = null" /></template>
