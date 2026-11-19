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
const busy = ref(false)
const error = ref('')
const health = ref<Awaited<ReturnType<typeof loadHealth>> | null>(null)
const healthFailed = ref(false)
const healthLoading = ref(false)
const progress = ref(0)
const started = ref(0)
const elapsed = ref(0)
let ticker: ReturnType<typeof setInterval> | undefined
let progressTimer: ReturnType<typeof setInterval> | undefined

async function refreshHealth() {
  healthLoading.value = true
  try { health.value = await loadHealth(); healthFailed.value = false }
  catch { healthFailed.value = true }
  finally { healthLoading.value = false }
}
onMounted(() => { void refreshHealth() })
onUnmounted(() => { clearInterval(ticker); clearInterval(progressTimer) })

function choose(f: File | undefined) {
  if (!f) return
  file.value = f
  error.value = ''
}
function onDrop(event: DragEvent) {
  event.preventDefault()
  const id = event.dataTransfer?.getData('text/plain')
  if (id) {
    const fileNames: Record<string, string> = { notice: '주민 안내문 예시.txt', application: '지원 신청서 예시.txt', facility: '시설 이용 안내 예시.txt' }
    const name = fileNames[id]
    if (name) void fetch(`/samples/${id}.txt`).then((r) => r.text()).then((text) => choose(new File([text], name, { type: 'text/plain' })))
  } else choose(event.dataTransfer?.files[0])
}
async function submit() {
  if (!file.value || busy.value) return
  if (!/\.(txt|docx|hwpx|pdf)$/i.test(file.value.name)) { error.value = 'TXT, DOCX, HWPX, PDF 파일을 올려 주세요.'; return }
  if (file.value.size > 5 * 1024 * 1024) { error.value = '파일은 5MB 이하여야 해요.'; return }
  busy.value = true; error.value = ''; progress.value = 4; started.value = Date.now(); elapsed.value = 0
  ticker = setInterval(() => { elapsed.value = Math.floor((Date.now() - started.value) / 1000) }, 1000)
  progressTimer = setInterval(() => { progress.value = Math.min(92, progress.value + 3) }, 350)
  try {
    const response = await simplify(file.value)
    const result: AnalysisResult = { ...response, id: crypto.randomUUID(), filename: file.value.name, created_at: new Date().toISOString() }
    saveResult(result)
    progress.value = 100
    await router.push(`/results/${result.id}`)
  } catch (cause) {
    error.value = cause instanceof ApiError ? cause.message : '서버에 연결하지 못했어요. 잠시 뒤 다시 시도해 주세요.'
  } finally {
    busy.value = false; clearInterval(ticker); clearInterval(progressTimer)
  }
}
</script>

<template>
  <div class="page">
    <section class="hero" aria-labelledby="hero-h">
      <div class="hero-grid">
        <div class="hero-title"><p class="hero-kicker">공공기관 문서를 쉽게 읽도록</p><h1 id="hero-h" class="t-hero">공문서를<br />쉬운 말로 바꿔요</h1></div>
        <div class="hero-side"><p class="lede">안내문이나 신청 안내를 올리면 문장마다 원문과 쉬운 말을 나란히 보여 드려요.</p><C11ModelServerState :status="health" :loading="healthLoading" :failed="healthFailed" @refresh="refreshHealth" /></div>
      </div>
    </section>

    <section class="composer-wrap" aria-labelledby="input-h">
      <div class="composer one"><div class="composer-main">
        <div class="composer-head"><div><p class="t-caption-sm muted">공문서 파일</p><h2 id="input-h">파일을 올려 주세요</h2></div><span class="t-caption-sm muted">TXT · DOCX · HWPX · PDF, 5MB 이하</span></div>
        <div v-if="busy" class="section tight" aria-live="polite"><C1Rail :steps="[{ label: '공문서 올리기', state: 'done' }, { label: '쉬운 말로 바꾸기', state: 'now' }, { label: '결과 확인', state: 'wait' }]" /><ProgressMeter :percent="progress" label="쉬운 말로 바꾸는 진행률"><b>문장마다 쉬운 말로 바꾸고 있어요</b></ProgressMeter><ProgressWaitLine :elapsed-sec="elapsed" expected="문장 수에 따라 잠시 걸릴 수 있어요" /></div>
        <div v-else ref="dropzone" class="dropzone" data-part="dropzone" tabindex="0" role="button" :aria-label="file ? `선택한 파일 ${file.name}. 파일을 바꾸려면 누르세요` : '공문서 파일을 놓거나 눌러 고르세요'" @click="input?.click()" @keydown.enter="input?.click()" @keydown.space.prevent="input?.click()" @dragover.prevent @drop="onDrop">
          <input ref="input" data-part="file-input" class="visually-hidden" type="file" accept=".txt,.docx,.hwpx,.pdf" @click.stop @change="choose(($event.target as HTMLInputElement).files?.[0]); ($event.target as HTMLInputElement).value = ''" />
          <span class="drop-icon" aria-hidden="true">↑</span><strong>{{ file?.name ?? '파일을 이곳에 놓거나 눌러서 고르세요' }}</strong><span class="t-body-sm muted">공문서 파일은 이 요청을 처리하는 데 사용돼요.</span>
        </div>
        <p v-if="error" class="error-message" role="alert">{{ error }}</p>
        <div class="composer-foot"><span v-if="file" class="t-body-sm muted">{{ (file.size / 1024).toFixed(1) }} KB · 최근 결과는 이 브라우저에 저장돼요.</span><span v-else class="t-body-sm muted">공문서 원본 파일은 서버에 저장하지 않아요.</span><button type="button" class="btn btn-primary btn-lg" :disabled="!file || busy" @click="submit">쉬운 말로 바꾸기</button></div>
      </div></div>
      <SampleFilesMotion @select="choose" />
    </section>
  </div>
</template>

<style scoped>
.dropzone { min-height:180px;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:8px;border:1.5px dashed var(--color-hairline-strong);border-radius:var(--rounded-lg);background:var(--color-canvas);cursor:pointer;text-align:center;padding:24px }
.dropzone:hover,.dropzone:focus-visible { border-color:var(--color-ink);background:var(--color-paper) }
.drop-icon { display:grid;place-items:center;width:44px;height:44px;border-radius:50%;background:var(--color-surface-soft);font-size:24px }
.error-message { margin:0;color:var(--color-danger);font-weight:600 }
</style>
