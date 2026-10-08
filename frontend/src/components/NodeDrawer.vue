<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { api } from '../api'
import { actions, type Action, type Policy, type Region } from '../types'
import { workspace, refresh, toast } from '../stores/workspace'
import Modal from './Modal.vue'
import StatusBadge from './StatusBadge.vue'
import Icon from './Icon.vue'
const props = defineProps<{ id: string | null }>()
const emit = defineEmits<{ close: []; task: [id: string] }>()
const node = computed(() => workspace.data?.nodes.find(n => n.id === props.id))
const regions = ref<Region[]>([]), error = ref(''), busy = ref(false), confirmDelete = ref(false)
const form = reactive({ name: '', region: '', group_name: '', policy: { google: false, trust: false, interval_minutes: 0, scheduled_action: 'snapshot', region_path: '' } as Policy })
const actionKeys = Object.keys(actions) as Action[]
watch(() => props.id, async id => {
  error.value = ''; confirmDelete.value = false
  if (!id || !node.value) return
  Object.assign(form, { name: node.value.name, region: node.value.region, group_name: node.value.group_name, policy: { ...node.value.policy } })
  if (!regions.value.length) try { regions.value = (await api<{ regions: Region[] }>('/regions')).regions } catch (e) { error.value = (e as Error).message }
}, { immediate: true })
function canRun(action: Action) {
  if (!node.value?.capabilities.includes(action)) return false
  if (action === 'google' || action === 'trust') return node.value.policy[action]
  return action !== 'patrol' || node.value.policy.google || node.value.policy.trust
}
async function run(action: Action) {
  busy.value = true; error.value = ''
  try { const result = await api<{ id: string }>('/nodes/' + props.id + '/jobs', 'POST', { action }); await refresh(); emit('close'); emit('task', result.id) }
  catch (e) { error.value = (e as Error).message } finally { busy.value = false }
}
async function save() {
  busy.value = true; error.value = ''
  try { await api('/nodes/' + props.id, 'PATCH', form); await refresh(); toast('策略已保存，下次心跳同步到节点') }
  catch (e) { error.value = (e as Error).message } finally { busy.value = false }
}
async function remove() {
  busy.value = true
  try { await api('/nodes/' + props.id, 'DELETE'); emit('close'); await refresh(); toast('节点已移除，凭证已撤销') }
  catch (e) { error.value = (e as Error).message } finally { busy.value = false }
}
</script>
<template><Modal :open="!!id" :title="node?.name || '节点详情'" :subtitle="node ? `${node.platform || '等待系统信息'} · Agent ${node.version || '—'}` : ''" drawer @close="emit('close')">
  <template v-if="node"><div class="detail-metrics"><div class="detail-metric"><small>连接状态</small><strong><StatusBadge :status="node.online ? 'online' : 'offline'" /></strong></div><div class="detail-metric"><small>一分钟负载</small><strong>{{ node.metrics.load_1m ?? '—' }}</strong></div><div class="detail-metric"><small>磁盘使用率</small><strong>{{ node.metrics.disk_used_percent != null ? node.metrics.disk_used_percent + '%' : '—' }}</strong></div></div>
  <h3>哨兵操作</h3><div class="task-buttons mt-12"><button v-for="action in actionKeys" :key="action" class="btn" :disabled="busy || !canRun(action)" @click="run(action)"><Icon :name="action === 'logs' ? 'list' : 'play'" />{{ actions[action] }}</button></div><p class="mt-12">已安装的模块才可执行。区域访问和本地站点访问需先启用；任务会在 Agent 下一次心跳时领取。</p>
  <div v-if="error" class="form-error mt-12" role="alert">{{ error }}</div>
  <div class="section-label">节点信息与执行策略</div><form @submit.prevent="save"><fieldset :disabled="busy"><div class="form-grid"><div class="field"><label for="node-name">节点名称</label><input id="node-name" v-model="form.name" required maxlength="80"></div><div class="field"><label for="node-group">分组</label><input id="node-group" v-model="form.group_name" required maxlength="80"></div><div class="field"><label for="node-region">地区标签</label><input id="node-region" v-model="form.region" maxlength="80" placeholder="例如 日本 · 东京"></div><div class="field"><label for="node-target">哨兵目标地区</label><select id="node-target" v-model="form.policy.region_path"><option v-for="region in regions" :key="region.path" :value="region.path">{{ region.name }}</option></select></div></div>
  <label class="toggle-line"><span><strong>区域访问模块</strong><small>使用上游 Google 访问逻辑。定位改善效果未经验证。</small></span><input v-model="form.policy.google" type="checkbox"></label><label class="toggle-line"><span><strong>本地站点访问模块</strong><small>使用上游 Trust 访问逻辑。请求成功不代表信誉提升。</small></span><input v-model="form.policy.trust" type="checkbox"></label>
  <div class="form-grid"><div class="field"><label for="scheduled-action">定时任务</label><select id="scheduled-action" v-model="form.policy.scheduled_action"><option v-for="action in actionKeys.filter(a => a !== 'logs')" :key="action" :value="action">{{ actions[action] }}</option></select></div><div class="field"><label for="task-interval">执行周期（分钟）</label><input id="task-interval" v-model.number="form.policy.interval_minutes" type="number" min="0" max="1440" step="1" required><small>0 为关闭；启用后最少 5 分钟。</small></div></div><button class="btn primary" type="submit">{{ busy ? '正在保存…' : '保存节点策略' }}</button></fieldset></form>
  <div class="section-label">节点连接凭证</div><p>移除节点会撤销其凭证。已启动的本地进程可能继续运行；需要停止操作时，请先取消对应任务。</p><div class="actions mt-12"><template v-if="confirmDelete"><button class="btn" @click="confirmDelete = false">返回</button><button class="btn danger" :disabled="busy" @click="remove">确认移除节点</button></template><button v-else class="btn danger" @click="confirmDelete = true">移除节点</button></div></template>
</Modal></template>
