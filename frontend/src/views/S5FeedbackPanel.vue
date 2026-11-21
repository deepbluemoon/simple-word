<script setup lang="ts">
import { computed, ref } from 'vue'
import { sendFeedback } from '@/api/simpleWord'
import { getFeedbackVote, saveFeedbackVote } from '@/stores/feedbackVotes'

const props = defineProps<{ requestId: string; resultId: string; sentenceIndex: number; modelVersion: string; original: string; simple: string }>()
const vote = computed(() => getFeedbackVote(props.resultId, props.sentenceIndex))
const busy = ref(false)
const error = ref('')
const confirmation = ref('')
async function send(value: 'up' | 'down') {
  if (busy.value || vote.value === value) return
  const previous = vote.value
  busy.value = true; error.value = ''; confirmation.value = ''
  try {
    await sendFeedback(props.requestId, props.resultId, props.sentenceIndex, props.modelVersion, props.original, props.simple, value)
    saveFeedbackVote(props.resultId, props.sentenceIndex, value)
    confirmation.value = previous && previous !== value ? '의견을 변경했어요.' : '의견이 저장됐어요.'
  }
  catch { error.value = '의견을 보내지 못했어요. 다시 시도해 주세요.' }
  finally { busy.value = false }
}
</script>

<template>
  <div class="feedback" data-part="sentence-feedback">
    <span class="t-caption-sm muted">이 문장이 도움이 됐나요?</span>
    <button type="button" class="btn btn-secondary" :disabled="busy" :aria-pressed="vote === 'up'" @click="send('up')">👍 좋아요</button>
    <button type="button" class="btn btn-secondary" :disabled="busy" :aria-pressed="vote === 'down'" @click="send('down')">👎 아쉬워요</button>
    <span v-if="confirmation" class="feedback-success t-caption-sm" role="status">{{ confirmation }}</span><span v-if="error" class="error-message" role="alert">{{ error }}</span>
  </div>
</template>

<style scoped>
.feedback { display:flex;align-items:center;flex-wrap:wrap;gap:8px;margin-top:var(--spacing-md) }
.feedback .btn { height:34px;padding:0 12px;font-size:13px }
.feedback [aria-pressed="true"] { background:var(--color-ink);color:var(--color-white) }
.feedback-success { padding:6px 10px;border:1px solid var(--color-gray-300);border-radius:var(--rounded-full);background:var(--color-gray-100);color:var(--color-ink) }
.error-message { color:var(--color-error);font-size:13px }
</style>
