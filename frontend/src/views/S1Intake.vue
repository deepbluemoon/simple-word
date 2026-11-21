<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ApiError, loadHealth, simplify, type AnalysisResult } from '@/api/simpleWord'
import C1Rail from '@/components/common/C1Rail.vue'
import C11ModelServerState from '@/components/common/C11ModelServerState.vue'
import ProgressMeter from '@/components/common/ProgressMeter.vue'
import ProgressWaitLine from '@/components/common/ProgressWaitLine.vue'
import SampleFilesMotion from '@/components/common/SampleFilesMotion.vue'
import { saveResult } from '@/stores/history'

const router = useRouter()
const input = ref<HTMLInputElement | null>(null)
const dropzone = ref<HTMLElement | null>(null)
const file = ref<File | null>(null)
const mode = ref<'file' | 'text'>('file')
const pasteText = ref('')
const busy = ref(false)
const error = ref('')
const retrySeconds = ref(0)
const retryAvailable = ref(false)
const health = ref<Awaited<ReturnType<typeof loadHealth>> | null>(null)
const healthFailed = ref(false)
const healthLoading = ref(false)
const healthSlow = ref(false)
const progress = ref<number | null>(null)
const started = ref(0)
const elapsed = ref(0)
let ticker: ReturnType<typeof setInterval> | undefined

async function refreshHealth() {
  const startedAt = performance.now()
  healthLoading.value = true
  try { health.value = await loadHealth(); healthFailed.value = false; healthSlow.value = performance.now() - startedAt > 1500 }
  catch { healthFailed.value = true; healthSlow.value = false }
  finally { healthLoading.value = false }
}
onMounted(() => { void refreshHealth() })
onUnmounted(() => { clearInterval(ticker) })

function choose(f: File | undefined) {
  if (!f) return
  mode.value = 'file'; file.value = f; error.value = ''
}
function onDrop(event: DragEvent) {
  event.preventDefault()
  const id = event.dataTransfer?.getData('text/plain')
  const names: Record<string, string> = { notice: '주민 안내문 예시.txt', application: '지원 신청서 예시.txt', facility: '시설 이용 안내 예시.txt' }
  const name = names[id ?? '']
  if (name) {
    void fetch(`/samples/${id}.txt`).then((r) => { if (!r.ok) throw new Error(); return r.text() })
      .then((text) => choose(new File([text], name, { type: 'text/plain' })))
      .catch(() => { error.value = '예시 문서를 불러오지 못했어요. 다시 시도해 주세요.' })
  } else choose(event.dataTransfer?.files[0])
}
async function submit() {
  if (busy.value) return
  const uploadFile = mode.value === 'text'
    ? new File([new Blob([pasteText.value], { type: 'text/plain' })], '붙여넣은 공문서.txt', { type: 'text/plain' })
    : file.value
  if (!uploadFile) return
  if (mode.value === 'text' && !pasteText.value.trim()) { error.value = '공문서 내용을 붙여넣어 주세요.'; return }
  if (/\.pdf$/i.test(uploadFile.name)) { error.value = 'PDF 파일은 지원하지 않아요. TXT, DOCX, HWPX 파일을 올려 주세요.'; return }
  if (!/\.(txt|docx|hwpx)$/i.test(uploadFile.name)) { error.value = 'TXT, DOCX, HWPX 파일을 올려 주세요.'; return }
  if (uploadFile.size > 5 * 1024 * 1024) { error.value = '파일은 5MB 이하여야 해요.'; return }
  if (!uploadFile.size) { error.value = '내용이 비어 있어요. 공문서 내용을 넣어 주세요.'; return }
  busy.value = true; error.value = ''; retrySeconds.value = 0; retryAvailable.value = false
  progress.value = null; started.value = Date.now(); elapsed.value = 0
  ticker = setInterval(() => { elapsed.value = Math.floor((Date.now() - started.value) / 1000) }, 1000)
  try {
    const response = await simplify(uploadFile, (seconds) => { retrySeconds.value = seconds })
    const result: AnalysisResult = { ...response, id: crypto.randomUUID(), filename: uploadFile.name, created_at: new Date().toISOString() }
    saveResult(result); progress.value = 100
    await router.push(`/results/${result.id}`)
  } catch (cause) {
    error.value = cause instanceof ApiError ? cause.message : '서버에 연결하지 못했어요. 잠시 뒤 다시 시도해 주세요.'
    retryAvailable.value = cause instanceof ApiError && cause.status === 429
  } finally {
    busy.value = false; clearInterval(ticker)
  }
}
</script>

<template>
  <div class="page">
    <section class="hero" aria-labelledby="hero-h">
      <div class="hero-grid">
        <div class="hero-title"><p class="hero-kicker">공공기관 문서를 쉽게 읽도록</p><h1 id="hero-h" class="t-hero">공문서를<br />쉬운 말로 바꿔요</h1></div>
        <div class="hero-side"><p class="lede">안내문이나 신청 안내를 올리거나 붙여넣으면 문장마다 원문과 쉬운 말을 나란히 보여 드려요.</p><C11ModelServerState :status="health" :loading="healthLoading" :failed="healthFailed" :slow="healthSlow" @refresh="refreshHealth" /></div>
      </div>
    </section>

    <section class="composer-wrap" aria-labelledby="input-h">
      <div class="composer one"><form class="composer-main" @submit.prevent="submit">
        <div class="composer-head"><div><p class="t-caption-sm muted">공문서 입력</p><h2 id="input-h">쉬운 말로 바꿀 내용을 넣어 주세요</h2></div><span class="t-caption-sm muted">최대 5MB · 100문장</span></div>
        <div :class="['tabs', 'segmented', mode]" role="group" aria-label="공문서 입력 방법">
          <button type="button" class="tab" :aria-pressed="mode === 'file'" @click="mode = 'file'; error = ''">파일 올리기</button>
          <button type="button" class="tab" :aria-pressed="mode === 'text'" @click="mode = 'text'; error = ''">글 붙여넣기</button>
        </div>
        <div v-if="busy" class="section tight" aria-live="polite"><C1Rail :steps="[{ label: '공문서 올리기', state: 'done' }, { label: '문장 나누기', state: 'done' }, { label: '쉬운 말 변환', state: 'now' }, { label: '완료', state: 'wait' }]" /><ProgressMeter :percent="progress" label="문서 처리 진행률"><b>문장을 확인해 쉬운 말로 바꾸고 있어요</b></ProgressMeter><ProgressWaitLine :elapsed-sec="elapsed" expected="문장 수에 따라 잠시 걸릴 수 있어요" /></div>
        <div v-else-if="mode === 'file'" ref="dropzone" class="dropzone" data-part="dropzone" tabindex="0" role="button" :aria-label="file ? `선택한 파일 ${file.name}. 파일을 바꾸려면 누르세요` : '공문서 파일을 놓거나 눌러 고르세요'" @click="input?.click()" @keydown.enter="input?.click()" @keydown.space.prevent="input?.click()" @dragover.prevent @drop="onDrop">
          <input ref="input" data-part="file-input" class="visually-hidden" type="file" accept=".txt,.docx,.hwpx" aria-label="공문서 파일 선택" @click.stop @change="choose(($event.target as HTMLInputElement).files?.[0]); ($event.target as HTMLInputElement).value = ''" />
          <span class="drop-icon" aria-hidden="true">↑</span><strong>{{ file?.name ?? '파일을 이곳에 놓거나 눌러서 고르세요' }}</strong><span class="t-body-sm muted">TXT · DOCX · HWPX 파일을 올릴 수 있어요.</span>
        </div>
        <label v-else class="paste-input"><span class="t-body-sm-strong">공문서 내용</span><textarea v-model="pasteText" rows="8" maxlength="5000000" aria-label="쉬운 말로 바꿀 공문서 내용" aria-describedby="paste-hint paste-count" placeholder="공문서 내용을 여기에 붙여넣으세요."></textarea><span id="paste-hint" class="t-caption-sm muted">한 번에 최대 100문장까지 바꿀 수 있어요.</span><span id="paste-count" class="t-caption-sm muted">{{ pasteText.length.toLocaleString() }}자</span></label>
        <p v-if="error" class="error-message" role="alert">{{ error }}</p>
        <p v-if="retrySeconds > 0" class="retry-state" role="status" aria-live="polite">{{ retrySeconds }}초 뒤 자동으로 다시 시도해요.</p>
        <div class="composer-foot"><span class="t-body-sm muted">{{ mode === 'file' && file ? `${(file.size / 1024).toFixed(1)} KB · ` : '' }}최근 결과는 이 브라우저에 저장돼요.</span><button type="submit" class="btn btn-primary btn-lg" :disabled="busy || (mode === 'file' ? !file : !pasteText.trim())">{{ retryAvailable ? '다시 시도' : retrySeconds ? `자동 재시도 · ${retrySeconds}초` : '쉬운 말로 바꾸기' }}</button></div>
      </form></div>
      <SampleFilesMotion v-if="mode === 'file'" @select="choose" />
    </section>
  </div>
</template>

<style scoped>
.dropzone { min-height:180px;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:8px;border:1.5px dashed var(--color-gray-300);border-radius:var(--rounded-lg);background:var(--color-white);cursor:pointer;text-align:center;padding:24px }
.dropzone:hover,.dropzone:focus-visible { border-color:var(--color-ink);background:var(--color-gray-100) }
.drop-icon { display:grid;place-items:center;width:44px;height:44px;border-radius:50%;background:var(--color-gray-100);font-size:24px }
.error-message { margin:0;color:var(--color-error);font-weight:600 }
.paste-input { display:grid;gap:8px }
.paste-input textarea { width:100%;min-height:180px;padding:16px;border:1px solid var(--color-gray-300);border-radius:var(--rounded-lg);font:400 16px/1.7 var(--font-sans);resize:vertical }
.paste-input textarea:focus-visible { outline:none;border-color:var(--color-ink);box-shadow:0 0 0 3px var(--color-focus-ring) }
.retry-state { display:flex;align-items:center;flex-wrap:wrap;gap:12px;padding:12px;border-radius:var(--rounded-md);background:var(--color-error-soft) }
.tabs.segmented { position:relative;display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:4px;padding:4px;border:1px solid var(--color-gray-200);border-radius:var(--rounded-md);background:var(--color-gray-100);isolation:isolate }
.tabs.segmented::before { content:"";position:absolute;z-index:-1;inset:4px auto 4px 4px;width:calc(50% - 4px);border:1px solid var(--color-gray-200);border-radius:var(--rounded-sm);background:var(--color-white);transition:transform .18s ease-out }
.tabs.segmented.mode-text::before { transform:translateX(100%) }
.tabs.segmented .tab { height:40px;width:100%;padding:0 12px;border:0;border-radius:var(--rounded-sm);background:transparent;color:var(--color-gray-800);font-weight:500 }
.tabs.segmented .tab[aria-pressed="true"] { color:var(--color-ink);font-weight:700 }
@media(prefers-reduced-motion:reduce) { .tabs.segmented::before { transition:none } }
@media(max-width:400px) { .retry-state .btn { width:100% } }
</style>
