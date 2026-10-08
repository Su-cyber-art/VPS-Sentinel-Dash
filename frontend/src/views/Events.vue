<script setup lang="ts">
import { workspace } from '../stores/workspace'
import PageHeading from '../components/PageHeading.vue'
import EventsList from '../components/EventsList.vue'
</script>
<template><PageHeading title="事件日志" subtitle="节点连接、配置调整与操作记录。" /><section class="card"><div class="card-head"><h2>最近 200 条事件</h2><small>记录保留 30 天</small></div><EventsList :events="workspace.data?.events || []" /></section></template>
