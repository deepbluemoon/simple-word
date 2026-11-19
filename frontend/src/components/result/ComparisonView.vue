<script setup lang="ts">
defineProps<{ original: string; simple: string }>()
</script>

<template>
  <div class="compare" data-part="comparison">
    <section><div class="col-head">원문</div><blockquote>{{ original }}</blockquote></section>
    <section><div class="col-head">쉬운 말</div><blockquote>{{ simple }}</blockquote></section>
  </div>
</template>
