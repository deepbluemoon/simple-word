<script setup lang="ts">
import { loadSample, samples } from '@/lib/samples'

const emit = defineEmits<{ select: [file: File] }>()

async function select(sample: typeof samples[number]) {
  try { emit('select', await loadSample(sample)) } catch { /* selection can be retried */ }
}
</script>

<template>
  <div class="sfm" data-part="sample-motion">
    <div class="sfm-head"><p class="sfm-title"><span class="sfm-spark" aria-hidden="true">✦</span>예시 공문서로 먼저 해 볼 수 있어요</p><p class="sfm-hint">예시를 누르거나 파일 놓는 곳으로 끌어다 놓으세요</p></div>
    <div class="sfm-track" aria-label="공문서 예시">
      <ul class="sfm-row">
        <li v-for="sample in samples" :key="sample.id" class="sfm-card" draggable="true" @dragstart="$event.dataTransfer?.setData('text/plain', sample.id)" @click="select(sample)">
          <span class="sfm-doc" aria-hidden="true">▤</span><span class="sfm-kind">{{ sample.kind }}</span><span class="sfm-name">{{ sample.name }}</span><span class="sfm-size">{{ sample.count }}</span><span class="sfm-tag">예시</span>
        </li>
      </ul>
    </div>
    <div class="sfm-foot"><div class="sfm-uses" role="group" aria-label="공문서 예시 고르기">
      <button v-for="sample in samples" :key="sample.id" type="button" class="sfm-use" @click="select(sample)"><span class="sfm-use-kind">{{ sample.kind }}</span>{{ sample.name }}</button>
    </div></div>
  </div>
</template>

<style scoped>
.sfm { position:relative;display:flex;flex-direction:column;gap:var(--spacing-sm);margin-top:var(--spacing-sm);padding:var(--spacing-lg);border-radius:var(--rounded-lg);background:var(--color-gray-100);border:1px solid var(--color-gray-200) }
.sfm-head { display:flex;flex-wrap:wrap;align-items:baseline;justify-content:space-between;gap:4px var(--spacing-md) }
.sfm-title { margin:0;display:inline-flex;align-items:center;gap:6px;color:var(--color-ink);font:600 15px/1.4 var(--font-sans) }
.sfm-spark { color:var(--color-warning);font-size:14px }
.sfm-hint { margin:0;color:var(--color-gray-800);font:400 13px/1.4 var(--font-sans) }
.sfm-track { overflow:hidden;padding:8px 0 10px }
.sfm-row { display:flex;gap:12px;width:max-content;margin:0;padding:0;list-style:none }
.sfm-card { display:inline-flex;align-items:center;gap:10px;height:52px;padding:0 14px 0 10px;border:1px solid var(--color-gray-300);border-radius:var(--rounded-md);background:var(--color-white);color:var(--color-ink);white-space:nowrap;font:400 14px/1 var(--font-sans);cursor:pointer }
.sfm-card:hover { border-color:var(--color-ink);transform:translateY(-2px) }
.sfm-doc { width:22px;color:var(--color-ink) }
.sfm-kind,.sfm-use-kind { display:inline-flex;align-items:center;justify-content:center;min-width:40px;height:22px;padding:0 6px;border-radius:6px;background:var(--color-ink);color:var(--color-white);font:600 10px/1 var(--font-mono) }
.sfm-name { font-weight:600 }
.sfm-size { color:var(--color-gray-800);font:400 12px/1 var(--font-sans) }
.sfm-tag { padding:3px 8px;border-radius:var(--rounded-full);background:var(--color-warning);color:var(--color-ink);font:600 11px/1.2 var(--font-sans) }
.sfm-foot,.sfm-uses { display:flex;flex-wrap:wrap;gap:6px }
.sfm-use-kind { min-width:auto;height:18px;padding:0 5px }
.sfm-use { display:inline-flex;align-items:center;gap:6px;height:36px;padding:0 14px 0 8px;border:1px solid var(--color-ink);border-radius:var(--rounded-full);background:var(--color-white);color:var(--color-ink);font:600 14px/1 var(--font-sans);cursor:pointer }
.sfm-use:hover { background:var(--color-ink);color:var(--color-white) }
@media(max-width:850px) { .sfm { padding:var(--spacing-md) }.sfm-track,.sfm-hint { display:none }.sfm-uses { flex-direction:column;width:100% }.sfm-use { width:100%;height:44px } }
</style>
