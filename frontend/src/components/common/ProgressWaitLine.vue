<script setup lang="ts">
import { computed } from 'vue'
const props = withDefaults(defineProps<{ elapsedSec: number | null; expected?: string }>(), { expected: '문장 수에 따라 잠시 걸릴 수 있어요' })
const elapsed = computed(() => props.elapsedSec == null ? '' : `${String(Math.floor(props.elapsedSec / 60)).padStart(2, '0')}:${String(props.elapsedSec % 60).padStart(2, '0')}`)
</script>

<template><div class="rail-wait" data-part="wait-line"><span v-if="elapsedSec != null">지난 시간 <span class="clock" data-part="elapsed">{{ elapsed }}</span></span><span class="muted" data-part="expected"> · {{ expected }}</span></div></template>
