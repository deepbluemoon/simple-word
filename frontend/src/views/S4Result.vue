<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { RouterLink } from 'vue-router'
import { findResult } from '@/stores/history'
import { groupParagraphs, groupSentenceParagraphs, readReaderSize, saveReaderSize, type ReaderSize } from '@/lib/reader'
import C1Rail from '@/components/common/C1Rail.vue'
import C5VerdictBadge from '@/components/common/C5VerdictBadge.vue'
import ComparisonView from '@/components/result/ComparisonView.vue'
import S5FeedbackPanel from './S5FeedbackPanel.vue'
import { diffWords } from '@/lib/textDiff'
import type { DifficultTerm, SentenceResult } from '@/api/simpleWord'
import type { DiffPart } from '@/lib/textDiff'

const props = defineProps<{ id: string }>()
type ViewMode = 'simple' | 'original' | 'sentences'
const result = computed(() => findResult(props.id))
const heading = ref<HTMLHeadingElement | null>(null)
const readerSize = ref<ReaderSize>(readReaderSize())
const viewMode = ref<ViewMode>('simple')
const selectedIndex = ref<number | null>(null)
const selectedTerm = ref<DifficultTerm | null>(null)
const viewTabButtons: (HTMLButtonElement | null)[] = []
const copyMessage = ref('')
const exportError = ref('')
const paragraphs = computed(() => groupParagraphs(result.value?.sentences ?? []))
const sentenceDiffs = computed(() => (result.value?.sentences ?? []).map((sentence) =>
  diffWords(sentence.original, outputSentence(sentence)),
))
function originalParts(parts: DiffPart[], terms: DifficultTerm[]) {
  const original = parts.map((part) => part.text).join('')
  const ranges: { start: number; end: number; changed: boolean }[] = []
  let offset = 0
  for (const part of parts) {
    ranges.push({ start: offset, end: offset + part.text.length, changed: part.kind === 'removed' })
    offset += part.text.length
  }
  const matches = terms.filter((term) => term.start >= 0 && term.end <= original.length && term.start < term.end)
    .sort((a, b) => a.start - b.start || b.end - a.end)
  const result: { text: string; highlighted: boolean; term?: DifficultTerm }[] = []
  let cursor = 0
  let partIndex = 0
  let termIndex = 0
  while (cursor < original.length) {
    while (termIndex < matches.length && matches[termIndex].end <= cursor) termIndex++
    const term = matches[termIndex]
    if (term?.start === cursor) {
      result.push({ text: original.slice(cursor, term.end), highlighted: true, term })
      cursor = term.end
      continue
    }
    while (partIndex < ranges.length && ranges[partIndex].end <= cursor) partIndex++
    const part = ranges[partIndex]
    const end = Math.min(part.end, term?.start != null && term.start > cursor ? term.start : original.length)
    result.push({ text: original.slice(cursor, end), highlighted: part.changed })
    cursor = end
  }
  return result
}
const documentParagraphs = computed(() => {
  let index = 0
  return groupSentenceParagraphs(result.value?.sentences ?? []).map((paragraph) =>
    paragraph.map((sentence) => {
      const sentenceIndex = index++
      const diff = sentenceDiffs.value[sentenceIndex]
      return {
        sentence,
        index: sentenceIndex,
        originalParts: originalParts(diff.original, sentence.terms ?? []),
        simpleParts: sentence.fallback || sentence.title
          ? [{ text: sentence.original, highlighted: false }]
          : diff.simple.map((part) => ({ text: part.text, highlighted: part.kind === 'added' })),
      }
    }),
  )
})
const selectedSentence = computed(() => selectedIndex.value == null ? null : result.value?.sentences[selectedIndex.value] ?? null)
const selectedTerms = computed(() => selectedSentence.value?.terms ?? [])
const changedCount = computed(() => result.value?.sentences.filter((sentence) => outputSentence(sentence) !== sentence.original).length ?? 0)
const easyText = computed(() => paragraphs.value.join('\n\n'))
const sideBySideText = computed(() => result.value?.sentences.map((sentence, index) => `문장 ${index + 1}\n원문: ${sentence.original}\n쉬운 말: ${outputSentence(sentence)}`).join('\n\n') ?? '')
function setViewMode(mode: ViewMode) {
  if (mode !== viewMode.value) selectedTerm.value = null
  viewMode.value = mode
  const index = (['simple', 'original', 'sentences'] as ViewMode[]).indexOf(mode)
  void nextTick(() => viewTabButtons[index]?.focus())
}
function outputSentence(sentence: SentenceResult) { return sentence.fallback || sentence.title ? sentence.original : sentence.simple }
function tabKeydown(event: KeyboardEvent) {
  const modes: ViewMode[] = ['simple', 'original', 'sentences']
  const current = modes.indexOf(viewMode.value)
  if (event.key === 'Home') setViewMode(modes[0])
  else if (event.key === 'End') setViewMode(modes.at(-1)!)
  else if (event.key === 'ArrowRight') setViewMode(modes[(current + 1) % modes.length])
  else if (event.key === 'ArrowLeft') setViewMode(modes[(current + modes.length - 1) % modes.length])
  else return
  event.preventDefault()
}
function selectSentence(event: MouseEvent | KeyboardEvent, index: number) {
  selectedIndex.value = index
  const termText = (event.target as HTMLElement).closest<HTMLElement>('[data-term]')?.dataset.term
  selectedTerm.value = result.value?.sentences[index].terms?.find((term) => term.text === termText) ?? null
}
function sourceLabel(source: string) {
  return source.split(', ').map((id) => result.value?.term_licenses?.[id] ?? id).join(' · ')
}

async function focusHeading() { await nextTick(); heading.value?.focus({ preventScroll: true }) }
onMounted(() => { void focusHeading() })
watch(() => props.id, () => { selectedIndex.value = null; selectedTerm.value = null; viewMode.value = 'simple'; void focusHeading() })
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
      <p class="source-notice">쉬운 말은 이해를 돕기 위한 것이며, 정확한 내용은 원문이 기준입니다.</p>
      <section class="section tight"><C1Rail :steps="[{ label: '공문서 올리기', state: 'done', info: { title: '올린 공문서', lines: [result.filename] } }, { label: '문장 나누기', state: 'done', info: { title: '나눈 문장', lines: [`${result.sentences.length}개 문장을 확인했어요.`] } }, { label: '쉬운 말로 바꾸기', state: 'done' }, { label: '완료', state: 'now' }]" /><p class="t-body-sm muted mt-md">{{ result.sentences.length }}개 문장 · 모델 {{ result.model_version }}</p></section>

      <section class="reader-toolbar" aria-label="결과 읽기와 내보내기">
        <div class="view-tabs" role="tablist" aria-label="결과 보기 방식">
          <button :ref="(el) => { viewTabButtons[0] = el as HTMLButtonElement }" id="simple-tab" type="button" role="tab" aria-controls="simple-panel" class="btn btn-secondary" :aria-selected="viewMode === 'simple'" :tabindex="viewMode === 'simple' ? 0 : -1" @click="setViewMode('simple')" @keydown="tabKeydown">쉬운 말로 읽기</button>
          <button :ref="(el) => { viewTabButtons[1] = el as HTMLButtonElement }" id="original-tab" type="button" role="tab" aria-controls="original-panel" class="btn btn-secondary" :aria-selected="viewMode === 'original'" :tabindex="viewMode === 'original' ? 0 : -1" @click="setViewMode('original')" @keydown="tabKeydown">원문 보기</button>
          <button :ref="(el) => { viewTabButtons[2] = el as HTMLButtonElement }" id="sentences-tab" type="button" role="tab" aria-controls="sentences-panel" class="btn btn-secondary" :aria-selected="viewMode === 'sentences'" :tabindex="viewMode === 'sentences' ? 0 : -1" @click="setViewMode('sentences')" @keydown="tabKeydown">문장별 보기</button>
        </div>
        <div class="reader-group" role="group" aria-label="글자 크기">
          <button type="button" class="btn btn-secondary" aria-label="글자 작게" :aria-pressed="readerSize === 'small'" @click="readerSize = 'small'">가−</button>
          <button type="button" class="btn btn-secondary" aria-label="보통 글자 크기" :aria-pressed="readerSize === 'medium'" @click="readerSize = 'medium'">가</button>
          <button type="button" class="btn btn-secondary" aria-label="글자 크게" :aria-pressed="readerSize === 'large'" @click="readerSize = 'large'">가+</button>
        </div>
        <button type="button" class="btn btn-secondary" @click="copySimple">쉬운 말 복사</button>
        <button type="button" class="btn btn-secondary" @click="downloadText(easyText, '쉬운말')">쉬운 말 .txt</button>
        <button type="button" class="btn btn-secondary" @click="downloadText(sideBySideText, '원문-쉬운말')">원문·쉬운 말 .txt</button>
        <span v-if="copyMessage" class="reader-status" role="status">{{ copyMessage }}</span>
        <span v-if="exportError" class="reader-status error-message" role="alert">{{ exportError }}</span>
      </section>

      <section v-if="viewMode === 'simple'" id="simple-panel" class="section tight document-layout" :class="`reader-${readerSize}`" aria-labelledby="simple-tab" role="tabpanel">
        <article class="document-page" aria-label="쉬운 말 문서">
          <p class="document-legend"><span class="change-swatch" aria-hidden="true" />노란 칸은 원문에서 바뀐 부분이에요. <span class="fallback-swatch" aria-hidden="true">원문 유지</span> 점선 밑줄은 원문을 그대로 둔 문장이에요.</p>
          <p v-for="(paragraph, paragraphIndex) in documentParagraphs" :key="paragraphIndex" class="document-paragraph">
            <template v-for="item in paragraph" :key="item.index">
              <span tabindex="0" role="button" :aria-pressed="selectedIndex === item.index" class="document-sentence" :class="{ selected: selectedIndex === item.index, fallback: item.sentence.fallback }" :aria-current="selectedIndex === item.index ? 'true' : undefined" :data-sentence="item.index" @click="selectSentence($event, item.index)" @keydown.enter.prevent="selectSentence($event, item.index)" @keydown.space.prevent="selectSentence($event, item.index)">
                <template v-for="(part, partIndex) in item.simpleParts" :key="partIndex">
                  <mark v-if="part.highlighted"><span class="visually-hidden">바뀐 부분: </span>{{ part.text }}</mark><template v-else>{{ part.text }}</template>
                </template>
                <span v-if="item.sentence.title" class="title-preserved">제목·원문 유지</span><span v-else-if="item.sentence.fallback" class="visually-hidden">원문 유지. </span>
              </span><span aria-hidden="true"> </span>
            </template>
          </p>
        </article>
        <aside class="clause-note" aria-label="선택한 문장 메모">
          <template v-if="selectedSentence">
            <h2 class="t-heading-sm">선택한 문장</h2>
            <dl><dt>원문</dt><dd>{{ selectedSentence.original }}</dd></dl>
            <div v-if="selectedTerms.length" class="term-list"><span class="t-caption-sm muted">문장 속 어려운 용어</span><button v-for="term in selectedTerms" :key="term.start" type="button" class="term-choice" :aria-pressed="selectedTerm?.text === term.text" @click="selectedTerm = term">{{ term.text }} → {{ term.easy.join(', ') }}</button></div>
            <p v-if="selectedTerm" class="term-meaning">뜻: {{ selectedTerm.easy.join(', ') }}<small>출처: {{ sourceLabel(selectedTerm.source) }}</small></p>
            <p v-if="selectedSentence.fallback" class="fallback-reason">{{ reasonText(selectedSentence.fallback_reason) }}</p>
            <S5FeedbackPanel :key="selectedIndex ?? -1" :request-id="result.request_id ?? result.id" :result-id="result.id" :sentence-index="selectedIndex!" :model-version="result.model_version" :original="selectedSentence.original" :simple="outputSentence(selectedSentence)" />
          </template>
          <p v-else class="t-body-sm muted">문장을 누르거나 키보드로 선택하면 원문과 의견을 볼 수 있어요.</p>
        </aside>
      </section>
      <section v-else-if="viewMode === 'original'" id="original-panel" class="section tight document-layout" :class="`reader-${readerSize}`" aria-labelledby="original-tab" role="tabpanel">
        <article class="document-page" aria-label="원문 문서">
          <p class="document-legend"><span class="change-swatch" aria-hidden="true" />노란 칸은 바뀐 부분 또는 어려운 용어예요. 아래에 쉬운 뜻을 표시해요. <span v-for="([source, license]) in Object.entries(result.term_licenses ?? {})" :key="source">{{ license }}</span></p>
          <p v-for="(paragraph, paragraphIndex) in documentParagraphs" :key="paragraphIndex" class="document-paragraph">
            <template v-for="item in paragraph" :key="item.index">
              <span tabindex="0" role="button" :aria-pressed="selectedIndex === item.index" class="document-sentence" :class="{ selected: selectedIndex === item.index }" :aria-current="selectedIndex === item.index ? 'true' : undefined" :data-sentence="item.index" @click="selectSentence($event, item.index)" @keydown.enter.prevent="selectSentence($event, item.index)" @keydown.space.prevent="selectSentence($event, item.index)">
                <template v-for="(part, partIndex) in item.originalParts" :key="partIndex">
                  <ruby v-if="part.term" class="term-ruby" :data-term="part.term.text"><mark><span class="visually-hidden">{{ part.term.text }}, 뜻: {{ part.term.easy.join(', ') }}. 출처: {{ sourceLabel(part.term.source) }}. </span><span aria-hidden="true">{{ part.text }}</span></mark><rt aria-hidden="true">뜻: {{ part.term.easy.join(', ') }}</rt></ruby>
                  <mark v-else-if="part.highlighted"><span class="visually-hidden">바뀐 부분: </span>{{ part.text }}</mark><template v-else>{{ part.text }}</template>
                </template>
                <span v-if="item.sentence.fallback" class="visually-hidden">원문 유지. </span>
              </span><span aria-hidden="true"> </span>
            </template>
          </p>
        </article>
        <aside class="clause-note" aria-label="선택한 문장 메모">
          <template v-if="selectedSentence">
            <h2 class="t-heading-sm">선택한 문장</h2>
            <h3 v-if="selectedTerm" class="t-heading-sm">{{ selectedTerm.text }}</h3>
            <p v-if="selectedTerm" class="term-meaning">뜻: {{ selectedTerm.easy.join(', ') }}<small>출처: {{ sourceLabel(selectedTerm.source) }}</small></p>
            <div v-if="selectedTerms.length" class="term-list"><span class="t-caption-sm muted">문장 속 어려운 용어</span><button v-for="term in selectedTerms" :key="term.start" type="button" class="term-choice" :aria-pressed="selectedTerm?.text === term.text" @click="selectedTerm = term">{{ term.text }} → {{ term.easy.join(', ') }}</button></div>
            <dl><dt>원문</dt><dd>{{ selectedSentence.original }}</dd><dt>쉬운 말 전체</dt><dd>{{ outputSentence(selectedSentence) }}</dd></dl>
            <p v-if="selectedSentence.fallback" class="fallback-reason">{{ reasonText(selectedSentence.fallback_reason) }}</p>
            <S5FeedbackPanel :key="selectedIndex ?? -1" :request-id="result.request_id ?? result.id" :result-id="result.id" :sentence-index="selectedIndex!" :model-version="result.model_version" :original="selectedSentence.original" :simple="outputSentence(selectedSentence)" />
          </template>
          <p v-else class="t-body-sm muted">문장을 누르거나 키보드로 선택하면 원문과 의견을 볼 수 있어요.</p>
        </aside>
      </section>
      <section v-else id="sentences-panel" class="section tight sentence-list" :class="`reader-${readerSize}`" aria-labelledby="sentences-tab" role="tabpanel">
        <header class="comparison-summary"><h2 class="t-heading-md">문장별 비교</h2><span class="t-body-sm muted">{{ changedCount }} / {{ result.sentences.length }}개 문장에서 말이 바뀌었어요</span></header>
        <article v-for="(sentence, index) in result.sentences" :key="index" class="card sentence-card" :data-sentence="index">
          <div class="sentence-head"><h2 class="t-heading-sm">문장 {{ index + 1 }}</h2><C5VerdictBadge :fallback="sentence.fallback" :title="sentence.title" /></div>
          <ComparisonView :diff="sentenceDiffs[index]" />
          <p v-if="sentence.fallback" class="fallback-reason" data-part="fallback-reason">{{ reasonText(sentence.fallback_reason) }}</p>
          <S5FeedbackPanel :request-id="result.request_id ?? result.id" :result-id="result.id" :sentence-index="index" :model-version="result.model_version" :original="sentence.original" :simple="outputSentence(sentence)" />
        </article>
      </section>
      <span class="visually-hidden" role="status" aria-live="polite">{{ selectedIndex == null ? '' : `문장 ${selectedIndex + 1} 선택됨${selectedTerm ? `, 어려운 용어 ${selectedTerm.text}` : ''}` }}</span>
    </template>
  </div>
</template>

<style scoped>
.reader-toolbar { display:flex;align-items:center;flex-wrap:wrap;gap:8px;margin:var(--spacing-lg) 0;padding:12px;border:1px solid var(--color-gray-200);border-radius:var(--rounded-lg);background:var(--color-gray-100) }
.reader-group { display:flex;gap:4px }
.reader-group .btn { min-width:40px;padding:0 10px }
.reader-group [aria-pressed="true"] { background:var(--color-ink);color:var(--color-white) }
.reader-status { font-size:13px }
.source-notice { margin:var(--spacing-md) 0;color:var(--color-gray-800);font-size:.95em }
.view-tabs { display:flex;gap:4px;padding:4px;border:1px solid var(--color-gray-200);border-radius:var(--rounded-md);background:var(--color-gray-100) }
.view-tabs [aria-selected="true"] { background:var(--color-ink);color:var(--color-white) }
.sentence-list { display:grid;gap:var(--spacing-lg) }
.comparison-summary { display:flex;align-items:baseline;justify-content:space-between;gap:var(--spacing-md);flex-wrap:wrap;padding:0 2px }
.sentence-card { display:grid;gap:var(--spacing-md);padding:var(--spacing-xl) }
.sentence-head { display:flex;align-items:center;justify-content:space-between;gap:12px }
.fallback-reason { margin:0;color:var(--color-gray-800);font-size:.9em }
.title-preserved { display:inline-block;margin-left:6px;padding:2px 6px;border:1px solid var(--color-gray-300);border-radius:var(--rounded-full);font-size:11px;line-height:1.4;white-space:nowrap }
.document-layout { display:grid;grid-template-columns:minmax(0,1fr) 248px;gap:var(--spacing-xl);align-items:start }
.document-page { min-width:0;padding:var(--spacing-xl);border:1px solid var(--color-gray-200);border-radius:var(--rounded-lg);background:var(--color-white) }
.document-legend { display:flex;align-items:center;flex-wrap:wrap;gap:6px;margin:0 0 var(--spacing-lg);font-size:12px;color:var(--color-gray-800) }
.change-swatch { width:14px;height:14px;border-radius:2px;background:var(--color-highlight) }
.fallback-swatch { border-bottom:1px dashed var(--color-gray-800);font-size:12px }
.document-paragraph { margin:0 0 1.1em;font-size:inherit;line-height:2;white-space:pre-wrap;overflow-wrap:anywhere }
.document-paragraph:last-child { margin-bottom:0 }
.document-sentence { display:inline;padding:0;border:0;border-radius:2px;background:transparent;color:var(--color-ink);font:inherit;line-height:inherit;text-align:left;cursor:pointer }
.document-sentence:hover,.document-sentence.selected { outline:1px solid var(--color-gray-400);outline-offset:2px }
.document-sentence:focus-visible { outline:2px solid var(--color-ink);outline-offset:2px }
.document-sentence mark { padding:0 2px;border-radius:2px;background:var(--color-highlight);color:var(--color-ink);box-decoration-break:clone;-webkit-box-decoration-break:clone }
.term-ruby { ruby-position:under;ruby-align:start }
.term-ruby mark { display:inline-block }
.term-ruby rt { color:var(--color-gray-800);font-size:.68em;line-height:1.2;white-space:normal }
.term-list { display:flex;flex-wrap:wrap;align-items:center;gap:6px;margin:var(--spacing-md) 0 }
.term-choice { border:1px solid var(--color-gray-300);border-radius:var(--rounded-full);padding:4px 9px;background:var(--color-gray-100);color:var(--color-ink);font:inherit;font-size:var(--font-size-sm);cursor:pointer }
.term-choice[aria-pressed="true"] { border-color:var(--color-ink);background:var(--color-white) }
.term-meaning { margin:var(--spacing-sm) 0;color:var(--color-gray-800) }
.term-meaning small { display:block;margin-top:4px }
.document-sentence.fallback { text-decoration:underline dashed var(--color-gray-400);text-underline-offset:4px }
.clause-note { min-width:0;padding:var(--spacing-lg);border-radius:var(--rounded-md);background:var(--color-gray-100) }
.clause-note h2 { margin:0 0 var(--spacing-md) }
.clause-note dl { margin:0 }
.clause-note dt { margin:var(--spacing-sm) 0 2px;font-size:12px;color:var(--color-gray-800) }
.clause-note dd { margin:0;overflow-wrap:anywhere }
.clause-note .feedback { display:flex;flex-wrap:wrap }
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
  .reader-toolbar > button,.view-tabs { flex:1 1 calc(50% - 8px);min-width:0;white-space:normal;line-height:1.3;padding:8px }
  .reader-group { flex:1 1 100%;justify-content:flex-start }
  .sentence-card,.document-page { padding:14px }
}
@media(max-width:640px) { .document-layout { grid-template-columns:minmax(0,1fr);gap:var(--spacing-md) }.clause-note { margin-left:4px } }
</style>
