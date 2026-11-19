<script setup lang="ts">
import { ref } from 'vue'
import { sendFeedback } from '@/api/simpleWord'

const props = defineProps<{ modelVersion: string; original: string; simple: string }>()
const vote = ref<'up' | 'down' | null>(null)
const busy = ref(false)
const error = ref('')
async function send(value: 'up' | 'down') {
  if (busy.value) return
  busy.value = true; error.value = ''
  try { await sendFeedback(props.modelVersion, props.original, props.simple, value); vote.value = value }
  catch { error.value = '의견을 보내지 못했어요. 다시 시도해 주세요.' }
  finally { busy.value = false }
}
</script>

<template>
  <div class="feedback" data-part="sentence-feedback">
    <span class="t-caption-sm muted">이 문장이 도움이 됐나요?</span>
    <button type="button" class="btn btn-secondary" :disabled="busy" :aria-pressed="vote === 'up'" @click="send('up')">👍 좋아요</button>
    <button type="button" class="btn btn-secondary" :disabled="busy" :aria-pressed="vote === 'down'" @click="send('down')">👎 아쉬워요</button>
    <span v-if="vote" class="t-caption-sm" role="status">의견을 보냈어요.</span><span v-if="error" class="error-message" role="alert">{{ error }}</span>
  </div>
</template>

<style scoped>
.feedback { display:flex;align-items:center;flex-wrap:wrap;gap:8px;margin-top:var(--spacing-md) }
.feedback .btn { height:34px;padding:0 12px;font-size:13px }
.feedback [aria-pressed="true"] { background:var(--color-ink);color:var(--color-on-primary) }
.error-message { color:var(--color-danger);font-size:13px }
</style>
