<template>
  <div class="page wide">
    <section class="api-hero"><div><p class="hero-kicker">개발자 안내</p><h1 class="t-display-xl">쉬운글 API 사용법</h1></div><p class="lede">공문서를 보내 쉬운 말 결과를 받고, 문장별 의견을 보낼 수 있어요. API는 같은 주소에서 사용할 수 있습니다.</p></section>
    <section class="section rules">
      <h2>공문서 바꾸기</h2><p><code>POST /simplify</code> 요청의 본문을 <code>multipart/form-data</code>로 보내고, 파일 필드 이름은 <code>file</code>로 지정하세요. TXT, DOCX, HWPX 파일을 지원하며 최대 크기는 5MB예요.</p>
      <div class="terminal-card"><div class="lights" aria-hidden="true"><i></i><i></i><i></i></div><pre><span class="c"># 예시: 파일을 올려 결과 받기</span>
curl -X POST http://localhost:8000/simplify \\
  -F 'file=@공문서.txt'</pre></div>
      <h3 class="section-title mt-xl">응답 예</h3>
      <pre class="code-block">{
  "model_version": "v1",
  "sentences": [
    { "original": "신청은 2026년 12월 31일까지 해야 합니다.",
      "simple": "2026년 12월 31일까지 신청하세요.", "fallback": false, "title": false }
  ]
}</pre>
      <p class="t-body-sm muted">제목으로 판정한 첫 줄에는 <code>title: true</code>가 붙으며, 원문 그대로 결과에 포함됩니다.</p>
      <h2 class="mt-xl">문장별 의견 보내기</h2><p><code>POST /feedback</code>에 바꾼 결과의 모델 버전과 문장, 의견을 JSON으로 보내세요.</p>
      <div class="terminal-card"><div class="lights" aria-hidden="true"><i></i><i></i><i></i></div><pre>curl -X POST http://localhost:8000/feedback \\
  -H 'Content-Type: application/json' \\
  -d '{"model_version":"v1","original":"원문","simple":"쉬운 말","vote":"up"}'</pre></div>
      <p class="t-body-sm muted mt-lg">의견은 <code>vote</code>에 <code>up</code> 또는 <code>down</code>을 넣어 주세요. 서버 상태와 모델 버전은 <code>GET /health</code>에서 확인할 수 있어요.</p>
    </section>
  </div>
</template>
<style scoped>
.api-hero{padding-top:56px;display:grid;grid-template-columns:minmax(0,1.2fr) minmax(0,1fr);gap:var(--spacing-xl) 40px;align-items:end}
.api-hero .lede{margin:0;font:400 18px/1.55 var(--font-sans);color:var(--color-gray-800)}
.rules{max-width:860px;margin:var(--spacing-xxl) auto 0}
.rules p{max-width:820px}
.terminal-card{position:relative;margin:var(--spacing-lg) 0;padding:var(--spacing-xl);border:1px solid var(--color-gray-200);border-radius:var(--rounded-lg);background:var(--color-gray-100);overflow:auto}
.lights{display:flex;gap:6px;margin-bottom:var(--spacing-lg)}.lights i{width:8px;height:8px;border-radius:50%;background:var(--color-gray-300)}.lights i:nth-child(2){background:var(--color-gray-400)}.lights i:nth-child(3){background:var(--color-gray-800)}
.terminal-card pre,.code-block{margin:0;white-space:pre-wrap;overflow-wrap:anywhere;font:400 13px/1.6 var(--font-mono)}
.code-block{padding:var(--spacing-xl);border-radius:var(--rounded-lg);background:var(--color-gray-100)}
.c{color:var(--color-gray-800)}
@media(max-width:768px){.api-hero{grid-template-columns:1fr;padding-top:32px}}
</style>
