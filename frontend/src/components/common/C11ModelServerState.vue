<script setup lang="ts">
defineProps<{
  status: { model_versions: { version: string; roles: string[] }[] } | null
  loading?: boolean
  failed?: boolean
  slow?: boolean
}>()
defineEmits<{ refresh: [] }>()
</script>

<template>
  <div class="status-block" data-c="C11" :data-state="failed ? 'failed' : status ? 'ready' : 'loading'">
    <div class="row">
      <span class="status" :class="failed ? 'maintenance' : slow ? 'slow' : status ? 'ready' : 'checking'" aria-live="polite"><i aria-hidden="true" /><span class="state-text">{{ failed ? '점검 중' : slow ? '응답이 지연되고 있어요' : status ? '서버 정상' : '서버 상태 확인 중' }}</span></span>
      <button type="button" class="btn btn-secondary" :aria-busy="loading || undefined" @click="$emit('refresh')">{{ loading ? '확인 중…' : '상태 다시 확인' }}</button>
    </div>
    <p v-if="status" class="status-note">모델 버전: {{ status.model_versions.map((model) => model.version).join(', ') || '등록된 버전 없음' }}</p>
    <p v-else-if="failed" class="status-note">잠시 뒤 다시 확인해 주세요.</p>
  </div>
</template>

<style scoped>
.status.ready i { background:var(--color-success);border-color:var(--color-success) }
.status.slow i { background:var(--color-warning);border-color:var(--color-warning) }
.status.maintenance i { background:var(--color-error);border-color:var(--color-error) }
.status.checking i { background:var(--color-gray-300);border-color:var(--color-gray-800) }
</style>
