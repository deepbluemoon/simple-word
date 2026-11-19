<script setup lang="ts">
const emit = defineEmits<{ select: [file: File] }>()
const samples = [
  { id: 'notice', file: '주민 안내문 예시.txt', name: '주민 안내문', count: '3문장' },
  { id: 'application', file: '지원 신청서 예시.txt', name: '지원 신청서 안내', count: '3문장' },
  { id: 'facility', file: '시설 이용 안내 예시.txt', name: '시설 이용 안내', count: '3문장' },
]

async function select(sample: typeof samples[number]) {
  const response = await fetch(`/samples/${sample.id}.txt`)
  if (response.ok) emit('select', new File([await response.text()], sample.file, { type: 'text/plain' }))
}
</script>

<template>
  <div class="sfm" data-part="sample-motion">
    <div class="sfm-head"><p class="sfm-title"><span class="sfm-spark" aria-hidden="true">✦</span>예시 공문서로 먼저 해 볼 수 있어요</p><p class="sfm-hint">예시를 누르거나 파일 놓는 곳으로 끌어다 놓으세요</p></div>
    <div class="sfm-track" aria-label="공문서 예시">
      <ul class="sfm-row">
        <li v-for="sample in samples" :key="sample.id" class="sfm-card" draggable="true" @dragstart="$event.dataTransfer?.setData('text/plain', sample.id)" @click="select(sample)">
          <span class="sfm-doc" aria-hidden="true">▤</span><span class="sfm-kind">TXT</span><span class="sfm-name">{{ sample.name }}</span><span class="sfm-size">{{ sample.count }}</span><span class="sfm-tag">예시</span>
        </li>
      </ul>
    </div>
    <div class="sfm-foot"><div class="sfm-uses" role="group" aria-label="공문서 예시 고르기">
      <button v-for="sample in samples" :key="sample.id" type="button" class="sfm-use" @click="select(sample)"><span class="sfm-use-kind">TXT</span>{{ sample.name }}</button>
    </div></div>
  </div>
</template>

<style scoped>
.sfm { position:relative;display:flex;flex-direction:column;gap:var(--spacing-sm);margin-top:var(--spacing-sm);padding:var(--spacing-lg);border-radius:var(--rounded-lg);background:var(--color-paper);border:1px solid var(--color-hairline) }
.sfm-head { display:flex;flex-wrap:wrap;align-items:baseline;justify-content:space-between;gap:4px var(--spacing-md) }
.sfm-title { margin:0;display:inline-flex;align-items:center;gap:6px;color:var(--color-ink);font:600 15px/1.4 var(--font-sans) }
.sfm-spark { color:var(--color-risk-mid-line);font-size:14px }
.sfm-hint { margin:0;color:var(--color-body);font:400 13px/1.4 var(--font-sans) }
.sfm-track { overflow:hidden;padding:8px 0 10px }
.sfm-row { display:flex;gap:12px;width:max-content;margin:0;padding:0;list-style:none }
.sfm-card { display:inline-flex;align-items:center;gap:10px;height:52px;padding:0 14px 0 10px;border:1px solid var(--color-hairline-strong);border-radius:var(--rounded-md);background:var(--color-canvas);color:var(--color-ink);white-space:nowrap;font:400 14px/1 var(--font-sans);cursor:pointer }
.sfm-card:hover { border-color:var(--color-ink);transform:translateY(-2px) }
.sfm-doc { width:22px;color:var(--color-ink) }
.sfm-kind,.sfm-use-kind { display:inline-flex;align-items:center;justify-content:center;min-width:40px;height:22px;padding:0 6px;border-radius:6px;background:var(--color-ink);color:var(--color-on-primary);font:600 10px/1 var(--font-mono) }
.sfm-name { font-weight:600 }
.sfm-size { color:var(--color-body);font:400 12px/1 var(--font-sans) }
.sfm-tag { padding:3px 8px;border-radius:var(--rounded-full);background:var(--color-risk-mid);color:var(--color-risk-mid-ink);font:600 11px/1.2 var(--font-sans) }
.sfm-foot,.sfm-uses { display:flex;flex-wrap:wrap;gap:6px }
.sfm-use-kind { min-width:auto;height:18px;padding:0 5px }
.sfm-use { display:inline-flex;align-items:center;gap:6px;height:36px;padding:0 14px 0 8px;border:1px solid var(--color-ink);border-radius:var(--rounded-full);background:var(--color-canvas);color:var(--color-ink);font:600 14px/1 var(--font-sans);cursor:pointer }
.sfm-use:hover { background:var(--color-ink);color:var(--color-on-primary) }
@media(max-width:850px) { .sfm { padding:var(--spacing-md) }.sfm-track,.sfm-hint { display:none }.sfm-uses { flex-direction:column;width:100% }.sfm-use { width:100%;height:44px } }
</style>
