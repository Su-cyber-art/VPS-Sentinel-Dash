<script setup lang="ts">
import Icon from './Icon.vue'
import { refresh, workspace, toast } from '../stores/workspace'
defineProps<{ title: string; subtitle: string; add?: boolean }>()
defineEmits<{ enroll: [] }>()
async function reload() { await refresh(); if (!workspace.error) toast('已同步最新状态') }
</script>
<template><div class="page-head"><div><h1>{{ title }}</h1><p>{{ subtitle }}</p></div><div class="actions"><button class="btn" aria-label="刷新数据" :disabled="workspace.loading" @click="reload"><Icon name="refresh" /><span class="refresh-text">刷新</span></button><button v-if="add" class="btn primary" @click="$emit('enroll')"><Icon name="plus" />接入节点</button></div></div></template>
