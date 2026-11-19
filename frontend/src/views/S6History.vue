<script setup lang="ts">
import { ref } from 'vue'
import { RouterLink } from 'vue-router'
import { readHistory } from '@/stores/history'

const items = ref(readHistory())
function clearHistory() { localStorage.removeItem('simple-word.recent-results'); items.value = [] }
</script>

<template>
  <div class="page narrow">
    <div class="page-head"><div><p class="t-caption-sm muted">이 브라우저에 저장된 결과</p><h1 class="t-display-xl">최근 결과</h1></div><button v-if="items.length" class="btn btn-secondary" type="button" @click="clearHistory">기록 지우기</button></div>
    <section v-if="items.length" class="section tight history-list"><article v-for="item in items" :key="item.id" class="card history-item"><div><h2 class="t-heading-sm">{{ item.filename }}</h2><p class="t-caption-sm muted">{{ new Date(item.created_at).toLocaleString('ko-KR') }} · {{ item.sentences.length }}개 문장</p></div><RouterLink class="btn btn-secondary" :to="`/results/${item.id}`">결과 보기</RouterLink></article></section>
    <section v-else class="section tight card empty"><h2 class="t-heading-md">저장된 결과가 없어요</h2><p class="t-body-sm muted">공문서를 올리면 최근 결과를 이 브라우저에 저장해요.</p><RouterLink class="btn btn-primary" to="/">공문서 올리기</RouterLink></section>
  </div>
</template>

<style scoped>
.history-list { display:grid;gap:var(--spacing-sm) }
.history-item { display:flex;align-items:center;justify-content:space-between;gap:var(--spacing-md);padding:var(--spacing-lg) }
.history-item p { margin:4px 0 0 }
.empty { padding:var(--spacing-xxl);display:grid;justify-items:start;gap:var(--spacing-md) }
@media(max-width:600px) { .history-item { align-items:flex-start;flex-direction:column } }
</style>
