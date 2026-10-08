<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { api } from '../api'
import { toast, when } from '../stores/workspace'
import Modal from './Modal.vue'
import Icon from './Icon.vue'
const props = defineProps<{ open: boolean }>()
defineEmits<{ close: [] }>()
const name = ref(''), busy = ref(false), error = ref('')
const enrollment = ref<{ token: string; expires: number; master_url: string } | null>(null)
const origin = computed(() => enrollment.value?.master_url || window.location.origin)
const command = computed(() => `curl -fsSL '${origin.value}/downloads/install.sh' -o sentinel-install.sh\nsudo bash sentinel-install.sh --role agent --master '${origin.value}'`)
watch(() => props.open, value => { if (value) { name.value = ''; enrollment.value = null; error.value = '' } })
async function create() { busy.value = true; error.value = ''; try { enrollment.value = await api('/enrollments', 'POST', { name: name.value }) } catch (e) { error.value = (e as Error).message } finally { busy.value = false } }
async function copy(value: string) { try { await navigator.clipboard.writeText(value); toast('已复制') } catch { toast('浏览器未允许复制，请选中文本复制') } }
</script>
<template><Modal :open="open" title="接入新节点" subtitle="将服务器上的 Agent 连接到主控。" @close="$emit('close')">
  <form v-if="!enrollment" @submit.prevent="create"><div class="field"><label for="enroll-name">节点名称</label><input id="enroll-name" v-model="name" maxlength="80" required placeholder="例如 Tokyo · Production 01"></div><p>接入令牌有效期为 15 分钟，每个令牌只能注册一台节点。</p><div class="form-error" role="alert">{{ error }}</div><button class="btn primary mt-20" :disabled="busy">{{ busy ? '正在生成…' : '生成接入令牌' }}<Icon name="arrow" /></button></form>
  <template v-else><div class="section-label first-label">01 / 在目标 Linux 服务器运行</div><pre>{{ command }}</pre><button class="btn" @click="copy(command)"><Icon name="copy" />复制安装命令</button><div class="section-label">02 / 按安装提示粘贴令牌</div><div class="token-box"><code data-testid="enrollment-token">{{ enrollment.token }}</code><button class="btn icon-only" aria-label="复制令牌" @click="copy(enrollment.token)"><Icon name="copy" /></button></div><p class="mt-12">有效期至 {{ when(enrollment.expires) }}。安装程序会自动安装依赖和哨兵模块，注册后节点将在此显示。</p><div class="note">主控地址需能从目标节点访问。支持 HTTP 或 HTTPS；使用反代域名时，在主控配置中填写外部访问地址。</div></template>
  <template #footer><button class="btn" @click="$emit('close')">{{ enrollment ? '完成' : '取消' }}</button></template>
</Modal></template>
