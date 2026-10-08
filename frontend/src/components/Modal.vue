<script setup lang="ts">
import { ref, watch, nextTick } from 'vue'
import Icon from './Icon.vue'
const props = defineProps<{ open: boolean; title: string; subtitle?: string; drawer?: boolean }>()
const emit = defineEmits<{ close: [] }>()
const dialog = ref<HTMLDialogElement>()
watch(() => props.open, async value => { await nextTick(); if (value && !dialog.value?.open) dialog.value?.showModal(); if (!value) dialog.value?.close() }, { immediate: true })
</script>
<template><dialog ref="dialog" :class="{ drawer }" :aria-label="title" @cancel.prevent="emit('close')"><div class="dialog-head"><div><h2>{{ title }}</h2><small v-if="subtitle">{{ subtitle }}</small></div><button class="btn plain" aria-label="关闭窗口" @click="emit('close')"><Icon name="close" /></button></div><div class="dialog-content"><slot /></div><div v-if="$slots.footer" class="dialog-footer"><slot name="footer" /></div></dialog></template>
