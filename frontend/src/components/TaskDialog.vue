<script setup lang="ts">
import { ref, watch, computed, onUnmounted } from 'vue'
import { api } from '../api'
import { actions, type Task } from '../types'
import { when, toast, refresh } from '../stores/workspace'
import Modal from './Modal.vue'
import StatusBadge from './StatusBadge.vue'
const props = defineProps<{ id: string | null }>()
defineEmits<{ close: [] }>()
const task = ref<Task | null>(null), error = ref(''), busy = ref(false)
let timer: ReturnType<typeof setInterval> | undefined
const result = computed(() => typeof task.value?.result?.text === 'string' ? task.value.result.text : JSON.stringify(task.value?.result, null, 2))
async function load() { const id = props.id; if (!id) return; try { const value = await api<Task>('/jobs/' + id); if (props.id === id) { task.value = value; error.value = '' } } catch (e) { error.value = (e as Error).message } }
watch(() => props.id, id => { clearInterval(timer); task.value = null; error.value = ''; if (id) { void load(); timer = setInterval(() => { if (task.value && ['queued', 'running'].includes(task.value.status)) void load() }, 2000) } }, { immediate: true })
onUnmounted(() => clearInterval(timer))
async function cancel() { busy.value = true; try { await api('/jobs/' + props.id + '/cancel', 'POST'); await load(); await refresh(); toast('取消指令已提交') } catch (e) { error.value = (e as Error).message } finally { busy.value = false } }
</script>
<template><Modal :open="!!id" :title="task ? actions[task.action] : '任务详情'" :subtitle="task ? task.node_name + ' · ' + when(task.created) : ''" @close="$emit('close')"><div v-if="error" class="form-error" role="alert">{{ error }}</div><template v-if="task"><div class="spread"><StatusBadge :status="task.status" /><span class="mono muted">{{ task.id.slice(0, 12) }}</span></div><div class="section-label">执行结果</div><pre v-if="task.result">{{ result }}</pre><div v-else class="empty"><p>{{ task.status === 'queued' ? '等待 Agent 领取任务，离线节点会在恢复后领取。' : task.cancel_requested ? '已请求 Agent 终止任务，等待回传确认。' : 'Agent 正在执行，结果会自动更新。' }}</p></div></template><p v-else>正在读取任务…</p><template #footer><button v-if="task && ['queued', 'running'].includes(task.status)" class="btn danger" :disabled="busy || !!task.cancel_requested" @click="cancel">{{ task.cancel_requested ? '已请求取消' : '取消任务' }}</button><button class="btn" @click="load">刷新结果</button><button class="btn primary" @click="$emit('close')">完成</button></template></Modal></template>
