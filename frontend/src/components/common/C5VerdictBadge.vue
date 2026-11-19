<script setup lang="ts">
defineProps<{ fallback: boolean }>()
</script>

<template><span class="verdict" data-c="C5" :data-fallback="fallback"><span class="cat">{{ fallback ? '원문 유지' : '쉬운 말로 바꿈' }}</span></span></template>
