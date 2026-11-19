<script setup lang="ts">
defineProps<{
  status: { model_versions: { version: string; roles: string[] }[] } | null
  loading?: boolean
  failed?: boolean
}>()
defineEmits<{ refresh: [] }>()
</script>

<template>
  <div class="status-block" data-c="C11" :data-state="failed ? 'failed' : status ? 'ready' : 'loading'">
    <div class="row">
      <span v-if="status" class="status ready"><i aria-hidden="true" /><span class="state-text">서버 연결됨</span></span>
      <span v-else-if="failed" class="status down"><i aria-hidden="true" /><span class="state-text">서버 상태를 확인하지 못했어요</span></span>
      <span v-else class="status"><span class="muted">서버 상태를 확인하고 있어요…</span></span>
      <button type="button" class="btn btn-secondary" :aria-busy="loading || undefined" @click="$emit('refresh')">{{ loading ? '확인 중…' : '상태 다시 확인' }}</button>
    </div>
    <p v-if="status" class="status-note">모델 버전: {{ status.model_versions.map((model) => model.version).join(', ') || '등록된 버전 없음' }}</p>
    <p v-else-if="failed" class="status-note">잠시 뒤 다시 확인해 주세요.</p>
  </div>
</template>
