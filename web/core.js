// 화면과 상관없는 순수 함수. 브라우저에서는 window.SimpleWordCore, node 테스트에서는 require 로 쓴다.
(function (root) {
  const MAX_BYTES = 5 * 1024 * 1024;
  const EXTENSIONS = [".txt", ".docx", ".hwpx", ".pdf"];

  function formatSize(bytes) {
    if (bytes < 1024) return `${bytes}B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)}KB`;
    return `${(bytes / 1024 / 1024).toFixed(1)}MB`;
  }

  // 올리기 전에 막을 수 있는 오류. 문제가 없으면 null.
  function validateFile(file) {
    if (!file) return "파일을 선택해 주세요.";
    const name = file.name.toLowerCase();
    if (!EXTENSIONS.some((ext) => name.endsWith(ext))) return "지원하지 않는 파일 형식입니다. .txt, .docx, .hwpx, .pdf 파일만 올릴 수 있습니다.";
    if (file.size > MAX_BYTES) return `파일이 너무 큽니다(${formatSize(file.size)}). 5MB 이하 파일만 올릴 수 있습니다.`;
    if (file.size === 0) return "빈 파일입니다. 내용이 있는 파일을 골라 주세요.";
    return null;
  }

  // API 오류(상태 코드 + 영어 detail)를 화면에 보일 한국어 문장으로. status 0 = 연결 실패.
  function translateError(status, detail) {
    const d = typeof detail === "string" ? detail : "";
    if (status === 0) return "서버에 연결하지 못했습니다. 인터넷 연결을 확인한 뒤 다시 시도해 주세요.";
    if (status === 429) return "지금 이용하는 분이 많습니다. 잠시 뒤 다시 시도해 주세요.";
    if (status === 422) return "파일을 선택해 주세요.";
    if (status === 413) return "파일이 너무 큽니다. 5MB 이하 파일만 올릴 수 있습니다.";
    if (status === 400) {
      let m;
      if (d.startsWith("Supported files")) return "지원하지 않는 파일 형식입니다. .txt, .docx, .hwpx, .pdf 파일만 올릴 수 있습니다.";
      if (d === "File exceeds 5 MB limit") return "파일이 너무 큽니다. 5MB 이하 파일만 올릴 수 있습니다.";
      if (d === "File is empty") return "빈 파일입니다. 내용이 있는 파일을 골라 주세요.";
      if (d.startsWith("Unpacked document exceeds")) return "문서 안의 내용이 너무 큽니다(압축을 풀면 20MB 초과). 문서를 나눠서 올려 주세요.";
      if ((m = d.match(/^PDF exceeds (\d+)-page limit/))) return `PDF가 ${m[1]}쪽을 넘습니다. 나눠서 올려 주세요.`;
      if ((m = d.match(/^Document exceeds (\d+)-sentence limit/))) return `문장이 ${m[1]}개를 넘어 한 번에 바꿀 수 없습니다. 문서를 나눠서 올려 주세요.`;
      if ((m = d.match(/^Invalid (\w+) file/))) return `${m[1]} 파일을 읽지 못했습니다. 파일이 손상되었거나 암호가 걸려 있을 수 있습니다.`;
      return "이 파일은 처리할 수 없습니다. 다른 파일로 다시 시도해 주세요.";
    }
    if (status >= 500) return "서버에 문제가 생겨 문서를 바꾸지 못했습니다. 잠시 뒤 다시 시도해 주세요.";
    return "문서를 처리하지 못했습니다. 다시 시도해 주세요.";
  }

  // 요약 줄: 전체 문장 수, 바뀐 문장 수(쉬운 말이 원문과 다름), 원문 유지 수(fallback=true).
  function summarize(data) {
    const sentences = (data && data.sentences) || [];
    const kept = sentences.filter((s) => s.fallback === true).length;
    const changed = sentences.filter((s) => s.fallback !== true && s.simple.trim() !== s.original.trim()).length;
    return { total: sentences.length, changed, kept, modelVersion: (data && data.model_version) || "알 수 없음" };
  }

  function plainText(sentences) {
    return sentences.map((s) => s.simple).join("\n") + "\n";
  }

  function downloadName(fileName) {
    const base = (fileName || "문서").replace(/\.[^.]+$/, "");
    return `${base}-쉬운말.txt`;
  }

  const api = { MAX_BYTES, EXTENSIONS, formatSize, validateFile, translateError, summarize, plainText, downloadName };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.SimpleWordCore = api;
})(typeof window !== "undefined" ? window : globalThis);
