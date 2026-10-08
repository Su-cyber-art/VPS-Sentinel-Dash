<script setup lang="ts">
import { ref, computed } from 'vue'
import { workspace } from '../stores/workspace'
import PageHeading from '../components/PageHeading.vue'
import TaskTable from '../components/TaskTable.vue'
import TaskDialog from '../components/TaskDialog.vue'
const selected = ref<string | null>(null), filter = ref('all')
const tasks = computed(() => workspace.data?.jobs.filter(t => filter.value === 'all' || t.status === filter.value) || [])
</script>
<template><PageHeading title="任务记录" subtitle="追踪任务执行过程，查看结果与失败原因。" /><section class="card"><div class="card-head"><div><h2>最近 200 个任务</h2><p>记录保留 30 天</p></div><select v-model="filter" aria-label="筛选任务状态"><option value="all">全部状态</option><option value="queued">待执行</option><option value="running">执行中</option><option value="succeeded">已完成</option><option value="failed">失败</option><option value="cancelled">已取消</option></select></div><TaskTable :tasks="tasks" @detail="selected = $event" /></section><TaskDialog :id="selected" @close="selected = null" /></template>
