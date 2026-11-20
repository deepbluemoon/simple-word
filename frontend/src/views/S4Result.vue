<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { RouterLink } from 'vue-router'
import { findResult } from '@/stores/history'
import { groupParagraphs, readReaderSize, saveReaderSize, type ReaderSize } from '@/lib/reader'
import C1Rail from '@/components/common/C1Rail.vue'
import C5VerdictBadge from '@/components/common/C5VerdictBadge.vue'
import ComparisonView from '@/components/result/ComparisonView.vue'
import S5FeedbackPanel from './S5FeedbackPanel.vue'

const props = defineProps<{ id: string }>()
const result = computed(() => findResult(props.id))
const heading = ref<HTMLHeadingElement | null>(null)
const readerSize = ref<ReaderSize>(readReaderSize())
const simpleOnly = ref(false)
const copyMessage = ref('')
const exportError = ref('')
const paragraphs = computed(() => groupParagraphs(result.value?.sentences ?? []))
const changedCount = computed(() => result.value?.sentences.filter((sentence) => sentence.original !== sentence.simple).length ?? 0)
const easyText = computed(() => paragraphs.value.join('\n\n'))
const sideBySideText = computed(() => result.value?.sentences.map((sentence, index) => `문장 ${index + 1}\n원문: ${sentence.original}\n쉬운 말: ${sentence.simple}`).join('\n\n') ?? '')

async function focusHeading() { await nextTick(); heading.value?.focus({ preventScroll: true }) }
onMounted(() => { void focusHeading() })
watch(() => props.id, () => { void focusHeading() })
watch(readerSize, saveReaderSize)

async function copySimple() {
  try { await navigator.clipboard.writeText(easyText.value); copyMessage.value = '쉬운 말을 복사했어요.'; exportError.value = '' }
  catch { exportError.value = '복사할 수 없어요. 브라우저의 클립보드 권한을 확인해 주세요.' }
}
function downloadText(contents: string, suffix: string) {
  if (!result.value) return
  const base = result.value.filename.replace(/\.[^./\\]+$/, '').replace(/[\\/:*?"<>|]/g, '_') || '공문서'
  const url = URL.createObjectURL(new Blob([contents], { type: 'text/plain;charset=utf-8' }))
  const link = document.createElement('a')
  link.href = url; link.download = `${base}-${suffix}.txt`; link.click()
  URL.revokeObjectURL(url)
}
function reasonText(reason?: string | null) {
  if (reason === 'numbers') return '숫자나 날짜를 안전하게 지키려고 원문을 유지했어요.'
  if (reason === 'preserve') return '보존해야 하는 용어를 지키려고 원문을 유지했어요.'
  if (reason === 'length') return '문장이 길어 원문을 유지했어요.'
  return '안전 검사를 통과하지 못해 원문을 유지했어요.'
}
</script>

<template>
  <div class="page wide">
    <div v-if="!result" class="page narrow">
      <div class="page-head"><h1 class="t-display-xl">이 결과를 찾을 수 없어요</h1></div>
      <section class="section tight"><p>최근 결과가 이 브라우저에 저장되어 있지 않아요.</p><RouterLink class="btn btn-primary" to="/">공문서 올리기</RouterLink></section>
    </div>
    <template v-else>
      <div class="page-head"><div><p class="t-caption-sm muted">{{ result.filename }} · {{ new Date(result.created_at).toLocaleString('ko-KR') }}</p><h1 ref="heading" tabindex="-1" class="t-display-xl">쉬운 말로 바꾼 결과</h1></div><RouterLink class="btn btn-secondary" to="/">새 공문서 올리기</RouterLink></div>
      <section class="section tight"><C1Rail :steps="[{ label: '공문서 올리기', state: 'done', info: { title: '올린 공문서', lines: [result.filename] } }, { label: '문장 나누기', state: 'done', info: { title: '나눈 문장', lines: [`${result.sentences.length}개 문장을 확인했어요.`] } }, { label: '쉬운 말로 바꾸기', state: 'done' }, { label: '완료', state: 'now' }]" /><p class="t-body-sm muted mt-md">{{ result.sentences.length }}개 문장 · 모델 {{ result.model_version }}</p></section>

      <section class="reader-toolbar" aria-label="결과 읽기와 내보내기">
        <div class="reader-group" role="group" aria-label="글자 크기">
          <button type="button" class="btn btn-secondary" aria-label="글자 작게" :aria-pressed="readerSize === 'small'" @click="readerSize = 'small'">가−</button>
          <button type="button" class="btn btn-secondary" aria-label="보통 글자 크기" :aria-pressed="readerSize === 'medium'" @click="readerSize = 'medium'">가</button>
          <button type="button" class="btn btn-secondary" aria-label="글자 크게" :aria-pressed="readerSize === 'large'" @click="readerSize = 'large'">가+</button>
        </div>
        <button type="button" class="btn btn-secondary" :aria-pressed="simpleOnly" @click="simpleOnly = !simpleOnly">{{ simpleOnly ? '원문과 함께 보기' : '쉬운 말만 보기' }}</button>
        <button type="button" class="btn btn-secondary" @click="copySimple">쉬운 말 복사</button>
        <button type="button" class="btn btn-secondary" @click="downloadText(easyText, '쉬운말')">쉬운 말 .txt</button>
        <button type="button" class="btn btn-secondary" @click="downloadText(sideBySideText, '원문-쉬운말')">원문·쉬운 말 .txt</button>
        <span v-if="copyMessage" class="reader-status" role="status">{{ copyMessage }}</span>
        <span v-if="exportError" class="reader-status error-message" role="alert">{{ exportError }}</span>
      </section>

      <section v-if="simpleOnly" class="section tight easy-reading" :class="`reader-${readerSize}`" aria-label="쉬운 말 이어 읽기">
        <article v-for="(paragraph, index) in paragraphs" :key="index" class="card reading-paragraph"><p>{{ paragraph }}</p></article>
      </section>
      <section v-else class="section tight sentence-list" :class="`reader-${readerSize}`" aria-label="문장별 바꾼 결과">
        <header class="comparison-summary"><h2 class="t-heading-md">문장별 비교</h2><span class="t-body-sm muted">{{ changedCount }} / {{ result.sentences.length }}개 문장에서 말이 바뀌었어요</span></header>
        <article v-for="(sentence, index) in result.sentences" :key="index" class="card sentence-card" :data-sentence="index">
          <div class="sentence-head"><h2 class="t-heading-sm">문장 {{ index + 1 }}</h2><C5VerdictBadge :fallback="sentence.fallback" /></div>
          <ComparisonView :original="sentence.original" :simple="sentence.simple" />
          <p v-if="sentence.fallback" class="fallback-reason" data-part="fallback-reason">{{ reasonText(sentence.fallback_reason) }}</p>
          <S5FeedbackPanel :model-version="result.model_version" :original="sentence.original" :simple="sentence.simple" />
        </article>
      </section>
    </template>
  </div>
</template>

<style scoped>
.reader-toolbar { display:flex;align-items:center;flex-wrap:wrap;gap:8px;margin:var(--spacing-lg) 0;padding:12px;border:1px solid var(--color-gray-200);border-radius:var(--rounded-lg);background:var(--color-gray-100) }
.reader-group { display:flex;gap:4px }
.reader-group .btn { min-width:40px;padding:0 10px }
.reader-group [aria-pressed="true"] { background:var(--color-ink);color:var(--color-white) }
.reader-status { font-size:13px }
.sentence-list,.easy-reading { display:grid;gap:var(--spacing-lg) }
.comparison-summary { display:flex;align-items:baseline;justify-content:space-between;gap:var(--spacing-md);flex-wrap:wrap;padding:0 2px }
.sentence-card { display:grid;gap:var(--spacing-md);padding:var(--spacing-xl) }
.sentence-head { display:flex;align-items:center;justify-content:space-between;gap:12px }
.fallback-reason { margin:0;color:var(--color-gray-800);font-size:.9em }
.reading-paragraph { padding:var(--spacing-xl) }
.reading-paragraph p { margin:0;line-height:1.9 }
.reader-small { font-size:14px }
.reader-medium { font-size:16px }
.reader-large { font-size:19px }
.reader-small :deep(.compare blockquote) { font-size:14px }
.reader-medium :deep(.compare blockquote) { font-size:16px }
.reader-large :deep(.compare blockquote) { font-size:19px }
.reader-small :deep(.feedback) { font-size:13px }
.reader-large :deep(.feedback) { font-size:17px }
.error-message { color:var(--color-error) }
@media(max-width:400px) {
  .page-head { align-items:flex-start;flex-direction:column }
  .reader-toolbar > button { flex:1 1 calc(50% - 8px);min-width:0;white-space:normal;line-height:1.3;padding:8px }
  .reader-group { flex:1 1 100%;justify-content:flex-start }
  .sentence-card,.reading-paragraph { padding:14px }
}
</style>
