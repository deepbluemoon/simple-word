// node --test tests/web  (tests/test_web_core.py 가 pytest 안에서 실행)
const test = require("node:test");
const assert = require("node:assert");
const core = require("../../web/core.js");

test("API 오류를 상태 코드별 한국어로, 요약 줄을 응답에서 계산", () => {
  assert.match(core.translateError(400, "File exceeds 5 MB limit"), /5MB 이하/);
  assert.match(core.translateError(400, "Document exceeds 100-sentence limit"), /100개를 넘어/);
  assert.match(core.translateError(400, "Invalid DOCX file: bad zip"), /^DOCX 파일을 읽지 못했습니다/);
  assert.match(core.translateError(400, "something new"), /처리할 수 없습니다/);
  assert.match(core.translateError(429, "Server is busy; retry shortly"), /잠시 뒤/);
  assert.match(core.translateError(500, "Model inference failed"), /서버에 문제/);
  assert.match(core.translateError(0), /연결하지 못했습니다/);
  assert.doesNotMatch(core.translateError(400, "Supported files: .txt"), /Supported/);  // 영어 detail 은 화면에 안 나감

  const data = { model_version: "v2", sentences: [
    { original: "가.", simple: "나.", fallback: false },
    { original: "다.", simple: "다.", fallback: false },
    { original: "100분의 20", simple: "100분의 20", fallback: true },
    { original: "라.", simple: "마." },  // fallback 필드가 없는 응답
  ] };
  assert.deepStrictEqual(core.summarize(data), { total: 4, changed: 2, kept: 1, modelVersion: "v2" });
  assert.strictEqual(core.plainText(data.sentences), "나.\n다.\n100분의 20\n마.\n");
  assert.strictEqual(core.downloadName("공문.hwpx"), "공문-쉬운말.txt");
  assert.strictEqual(core.validateFile({ name: "a.hwp", size: 10 }), "지원하지 않는 파일 형식입니다. .txt, .docx, .hwpx, .pdf 파일만 올릴 수 있습니다.");
  assert.match(core.validateFile({ name: "a.pdf", size: 6 * 1024 * 1024 }), /6\.0MB/);
  assert.strictEqual(core.validateFile({ name: "A.TXT", size: 10 }), null);
});
