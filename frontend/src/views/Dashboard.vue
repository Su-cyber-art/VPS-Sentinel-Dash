<script setup lang="ts">
import { computed, ref } from 'vue'
import { workspace } from '../stores/workspace'
import PageHeading from '../components/PageHeading.vue'
import NodeTable from '../components/NodeTable.vue'
import TaskTable from '../components/TaskTable.vue'
import EventsList from '../components/EventsList.vue'
import EnrollmentDialog from '../components/EnrollmentDialog.vue'
import NodeDrawer from '../components/NodeDrawer.vue'
import TaskDialog from '../components/TaskDialog.vue'
import Icon from '../components/Icon.vue'
const enroll = ref(false), node = ref<string | null>(null), task = ref<string | null>(null)
const data = computed(() => workspace.data)
const online = computed(() => data.value?.nodes.filter(n => n.online).length || 0)
const total = computed(() => data.value?.nodes.length || 0)
const percentage = computed(() => total.value ? Math.round(online.value / total.value * 100) : 0)
const taskCount = computed(() => Object.values(data.value?.counts || {}).reduce((sum, count) => sum + count, 0))
const maxActivity = computed(() => Math.max(1, ...(data.value?.hours || [])))
const metrics = computed(() => [
  { label: '在线节点', value: online.value, unit: `/ ${total.value}`, note: total.value ? '当前已连接 Agent' : '等待节点接入', icon: 'server' },
  { label: '覆盖地区', value: new Set(data.value?.nodes.map(n => n.region || n.metrics.country).filter(Boolean)).size, unit: '', note: '按节点地区标签统计', icon: 'globe' },
  { label: '24h 任务', value: taskCount.value, unit: '', note: `${data.value?.counts.succeeded || 0} 项完成 · ${data.value?.counts.failed || 0} 项失败`, icon: 'activity' },
  { label: '待处理任务', value: data.value?.pending_count || 0, unit: '', note: 'Agent 会自动领取并回传结果', icon: 'clock' },
])
</script>
<template><PageHeading title="运行概览" subtitle="随时了解你的服务器，以及正在发生的事。" add @enroll="enroll = true" /><template v-if="data"><div class="metrics"><section v-for="metric in metrics" :key="metric.label" class="metric"><div class="metric-top">{{ metric.label }}<span class="metric-icon"><Icon :name="metric.icon" /></span></div><div class="metric-value">{{ metric.value }}<span>{{ metric.unit }}</span></div><div class="metric-bottom">{{ metric.note }}</div></section></div><div class="grid-two"><div class="stack"><section class="card"><div class="card-head"><div><h2>我的节点 <span class="pill-count">{{ total }}</span></h2><p>服务器的最新连接状态</p></div><RouterLink to="/nodes" class="btn plain">管理节点 <Icon name="arrow" /></RouterLink></div><NodeTable :nodes="data.nodes.slice(0, 6)" @detail="node = $event" @enroll="enroll = true" /><div class="table-footer"><span>页面自动同步 · Agent 15 秒心跳</span><span>{{ total }} 个节点</span></div></section><section class="card"><div class="card-head"><h2>最近任务</h2><RouterLink to="/tasks" class="btn plain">全部记录 <Icon name="arrow" /></RouterLink></div><TaskTable :tasks="data.jobs.slice(0, 4)" @detail="task = $event" /></section></div><div class="stack side-stack"><section class="card health"><h2>连接健康度</h2><div class="health-number"><strong>{{ total ? percentage : '—' }}</strong><small>{{ total ? '% 节点在线' : '尚无节点' }}</small></div><div class="health-meter" :aria-label="`节点在线率 ${percentage}%`"><span v-for="n in 24" :key="n" :class="{ on: n <= Math.round(percentage / 100 * 24) }" /></div><div class="legend"><span>{{ online }} 在线</span><span>{{ total - online }} 离线</span></div><div class="tip"><strong>{{ total && online === total ? '所有节点连接正常' : 'Agent 主动连接主控' }}</strong>查看心跳、下发哨兵操作，执行结果自动回到面板。</div></section><section class="card activity"><div class="activity-title"><h2>任务活动</h2><small>过去 24 小时</small></div><div class="chart" role="img" :aria-label="`过去 24 小时共 ${taskCount} 个任务`"><span v-for="(count, index) in data.hours" :key="index" class="chart-bar" :style="{ height: Math.max(3, count / maxActivity * 100) + '%' }" :title="`${23 - index} 小时前：${count} 项`" /></div><div class="chart-labels"><span>24h 前</span><span>12h 前</span><span>现在</span></div></section><section class="card"><div class="card-head"><h2>最新动态</h2><RouterLink to="/events" class="btn plain" aria-label="全部事件"><Icon name="arrow" /></RouterLink></div><EventsList :events="data.events.slice(0, 3)" /></section></div></div></template><div v-else class="empty">正在连接主控…</div><EnrollmentDialog :open="enroll" @close="enroll = false" /><NodeDrawer :id="node" @close="node = null" @task="task = $event" /><TaskDialog :id="task" @close="task = null" /></template>
