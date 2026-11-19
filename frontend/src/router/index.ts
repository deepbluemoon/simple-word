import { createRouter, createWebHistory } from 'vue-router'

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'intake', component: () => import('@/views/S1Intake.vue'), meta: { title: '공문서 쉬운 말 바꾸기' } },
    { path: '/results/:id', name: 'result', component: () => import('@/views/S4Result.vue'), props: true, meta: { title: '바꾼 결과' } },
    { path: '/history', name: 'history', component: () => import('@/views/S6History.vue'), meta: { title: '최근 결과' } },
    { path: '/api-guide', name: 'api-guide', component: () => import('@/views/S9ApiGuide.vue'), meta: { title: 'API 사용법' } },
    { path: '/:pathMatch(.*)*', name: 'not-found', component: () => import('@/views/NotFound.vue'), meta: { title: '페이지를 찾을 수 없어요' } },
  ],
  scrollBehavior: () => ({ top: 0 }),
})

router.afterEach((to) => { document.title = `${String(to.meta.title ?? '쉬운글')} · 쉬운글` })
