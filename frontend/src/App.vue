<script setup lang="ts">
import { ref, watch } from 'vue'
import { RouterLink, RouterView, useRoute } from 'vue-router'

const open = ref(false)
const route = useRoute()
watch(() => route.fullPath, () => { open.value = false })
</script>

<template>
  <a class="visually-hidden" href="#main">본문으로 건너뛰기</a>
  <header class="app-nav" :class="{ 'menu-open': open }">
    <nav class="primary-nav" aria-label="주 메뉴">
      <RouterLink to="/" class="brand" aria-label="쉬운글 처음으로">
        <span class="brand-mark" aria-hidden="true" data-part="brand-mark"></span><span>쉬운글</span>
      </RouterLink>
      <div class="links" role="group" aria-label="주요 메뉴">
        <RouterLink to="/">공문서 바꾸기</RouterLink>
        <RouterLink to="/history">최근 결과</RouterLink>
      </div>
      <span class="spacer" />
      <div class="right">
        <RouterLink to="/api-guide" class="btn btn-secondary">API 안내</RouterLink>
        <button type="button" class="burger" :aria-expanded="open" aria-controls="menu-panel" :aria-label="open ? '메뉴 닫기' : '메뉴 열기'" @click="open = !open">
          <svg width="24" height="25" viewBox="0 0 24 25" fill="none" aria-hidden="true"><path d="M3 9.5H21M3 15.5H21" stroke="currentColor" stroke-width="1.5" /></svg>
        </button>
      </div>
    </nav>
  </header>
  <div v-if="open" class="menu-scrim open" aria-hidden="true" @click="open = false" />
  <aside id="menu-panel" class="menu-panel" :class="{ open }" role="dialog" aria-modal="true" aria-label="전체 메뉴" :aria-hidden="!open">
    <div class="menu-head"><strong>메뉴</strong><button type="button" class="menu-close" aria-label="메뉴 닫기" @click="open = false">✕</button></div>
    <nav class="menu-body" aria-label="전체 메뉴 목록">
      <section class="menu-group"><h2>공문서</h2><ul><li><RouterLink to="/">쉬운 말로 바꾸기<small>공문서 파일을 올려요</small></RouterLink></li><li><RouterLink to="/history">최근 결과<small>이 브라우저에 저장된 결과</small></RouterLink></li></ul></section>
      <section class="menu-group"><h2>개발자</h2><ul><li><RouterLink to="/api-guide">API 사용법<small>/simplify · /feedback</small></RouterLink></li></ul></section>
    </nav>
    <p class="menu-foot">공문서 문장을 더 쉽게 읽도록 바꿔 드려요.</p>
  </aside>
  <main id="main"><RouterView /></main>
  <footer class="footer-section"><span>쉬운글 · 공문서를 쉬운 말로</span><nav><RouterLink to="/api-guide">API 안내</RouterLink><RouterLink to="/history">최근 결과</RouterLink></nav></footer>
</template>
