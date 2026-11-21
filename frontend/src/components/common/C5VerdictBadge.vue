<script setup lang="ts">
defineProps<{ fallback: boolean; title?: boolean }>()
</script>

<template><span class="verdict" data-c="C5" :data-fallback="fallback"><span class="cat">{{ title ? '제목·원문 유지' : fallback ? '원문 유지' : '쉬운 말로 바꿈' }}</span></span></template>

<style scoped>
.verdict[data-fallback="true"] .cat { border-color:var(--color-gray-300);background:var(--color-white);color:var(--color-gray-800) }
</style>
