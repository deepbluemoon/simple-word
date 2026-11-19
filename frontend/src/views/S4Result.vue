<script setup lang="ts">
import { computed } from 'vue'
import { RouterLink } from 'vue-router'
import { findResult } from '@/stores/history'
import C1Rail from '@/components/common/C1Rail.vue'
import C5VerdictBadge from '@/components/common/C5VerdictBadge.vue'
import ComparisonView from '@/components/result/ComparisonView.vue'
import S5FeedbackPanel from './S5FeedbackPanel.vue'

const props = defineProps<{ id: string }>()
const result = computed(() => findResult(props.id))
</script>

<template>
  <div class="page wide">
    <div v-if="!result" class="page narrow">
      <div class="page-head"><h1 class="t-display-xl">이 결과를 찾을 수 없어요</h1></div>
      <section class="section tight"><p>최근 결과가 이 브라우저에 저장되어 있지 않아요.</p><RouterLink class="btn btn-primary" to="/">공문서 올리기</RouterLink></section>
    </div>
    <template v-else>
      <div class="page-head"><div><p class="t-caption-sm muted">{{ result.filename }} · {{ new Date(result.created_at).toLocaleString('ko-KR') }}</p><h1 class="t-display-xl">쉬운 말로 바꾼 결과</h1></div><RouterLink class="btn btn-secondary" to="/">새 공문서 올리기</RouterLink></div>
      <section class="section tight"><C1Rail :steps="[{ label: '공문서 올리기', state: 'done', info: { title: '올린 공문서', lines: [result.filename] } }, { label: '쉬운 말로 바꾸기', state: 'done', info: { title: '문장 바꾸기', lines: [`${result.sentences.length}개 문장을 확인했어요.`] } }, { label: '결과 확인', state: 'now' }]" /><p class="t-body-sm muted mt-md">{{ result.sentences.length }}개 문장 · 모델 {{ result.model_version }}</p></section>
      <section class="section tight sentence-list" aria-label="문장별 바꾼 결과">
        <article v-for="(sentence, index) in result.sentences" :key="index" class="card sentence-card" :data-sentence="index">
          <div class="sentence-head"><h2 class="t-heading-sm">문장 {{ index + 1 }}</h2><C5VerdictBadge :fallback="sentence.fallback" /></div>
          <ComparisonView :original="sentence.original" :simple="sentence.simple" />
          <S5FeedbackPanel :model-version="result.model_version" :original="sentence.original" :simple="sentence.simple" />
        </article>
      </section>
    </template>
  </div>
</template>

<style scoped>
.sentence-list { display:grid;gap:var(--spacing-lg) }
.sentence-card { display:grid;gap:var(--spacing-md);padding:var(--spacing-xl) }
.sentence-head { display:flex;align-items:center;justify-content:space-between;gap:12px }
</style>
