<script setup lang="ts">
import { computed, ref, useId } from 'vue'
import { diffWords } from '@/lib/textDiff'

const props = defineProps<{ original: string; simple: string }>()
const diff = computed(() => diffWords(props.original, props.simple))
const helpId = `diff-help-${useId()}`
const originalPane = ref<HTMLElement | null>(null)
const simplePane = ref<HTMLElement | null>(null)
let syncing = false

function syncScroll(source: HTMLElement | null, target: HTMLElement | null) {
  if (!source || !target || syncing) return
  syncing = true
  const sourceRange = source.scrollHeight - source.clientHeight
  const targetRange = target.scrollHeight - target.clientHeight
  target.scrollTop = sourceRange > 0 ? source.scrollTop / sourceRange * targetRange : source.scrollTop
  const done = () => { syncing = false }
  if (typeof requestAnimationFrame === 'function') requestAnimationFrame(done)
  else setTimeout(done, 0)
}
</script>

<template>
  <p :id="helpId" class="visually-hidden">원문에서 빠진 말은 취소선, 쉬운 말에 더한 말은 밑줄로 표시해요. 같은 숫자와 날짜는 두 쪽에서 같은 색으로 표시해요.</p>
  <div class="compare" data-part="comparison" :aria-describedby="helpId">
    <section><div class="col-head">원문</div><blockquote ref="originalPane" tabindex="0" aria-label="원문 문장" @scroll="syncScroll(originalPane, simplePane)"><template v-for="(part, index) in diff.original" :key="index"><del v-if="part.kind === 'removed'" :class="{ 'diff-number': part.numeric }">{{ part.text }}</del><span v-else :class="{ 'diff-number': part.numeric, 'preserved-number': part.numeric }">{{ part.text }}</span></template></blockquote></section>
    <section><div class="col-head">쉬운 말</div><blockquote ref="simplePane" tabindex="0" aria-label="쉬운 말 문장" @scroll="syncScroll(simplePane, originalPane)"><template v-for="(part, index) in diff.simple" :key="index"><ins v-if="part.kind === 'added'" :class="{ 'diff-number': part.numeric }">{{ part.text }}</ins><span v-else :class="{ 'diff-number': part.numeric, 'preserved-number': part.numeric }">{{ part.text }}</span></template></blockquote></section>
  </div>
</template>

<style scoped>
.compare blockquote { max-height:300px;overflow:auto;overscroll-behavior:contain;white-space:pre-wrap;overflow-wrap:anywhere }
.compare del,.compare ins { text-decoration:none;border-radius:3px;padding:0 1px }
.compare del { background:#fdeceb;text-decoration:line-through;text-decoration-thickness:1px }
.compare ins { background:#e7f3e9;border-bottom:2px solid #26733a }
.compare .diff-number { background:#e6efff;border-radius:3px;box-decoration-break:clone;-webkit-box-decoration-break:clone }
.compare .preserved-number { border-bottom:2px solid #597eb8 }
@media(max-width:400px) { .compare { gap:12px }.compare blockquote { max-height:220px;padding:12px;font-size:14px } }
</style>
