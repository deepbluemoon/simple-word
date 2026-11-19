const { formatSize, validateFile, translateError, summarize, plainText, downloadName } = window.SimpleWordCore;

const $ = (selector) => document.querySelector(selector);
const form = $("#upload-form");
const input = $("#file");
const dropZone = $("#drop-zone");
const submit = $("#submit");
const progress = $("#progress");
const progressText = $("#progress-text");
const statusLine = $("#status");
const errorLine = $("#error");
const results = $("#results");
const list = $("#sentences");
let selected = null;
let current = null; // 마지막 응답

function showError(message) {
  errorLine.textContent = message;
  errorLine.hidden = !message;
}

function choose(file) {
  selected = file || null;
  showError("");
  $("#file-info").hidden = !selected;
  if (!selected) return;
  $("#file-name").textContent = selected.name;
  $("#file-size").textContent = formatSize(selected.size);
  const problem = validateFile(selected);
  if (problem) showError(problem);
}

input.addEventListener("change", () => choose(input.files[0]));
for (const type of ["dragenter", "dragover"]) {
  dropZone.addEventListener(type, (event) => {
    event.preventDefault();
    dropZone.classList.add("dragging");
  });
}
for (const type of ["dragleave", "drop"]) {
  dropZone.addEventListener(type, () => dropZone.classList.remove("dragging"));
}
dropZone.addEventListener("drop", (event) => {
  event.preventDefault();
  if (event.dataTransfer.files.length) choose(event.dataTransfer.files[0]);
});

function setBusy(busy) {
  submit.disabled = busy;
  submit.classList.toggle("loading", busy);
  submit.querySelector(".button-label").textContent = busy ? "바꾸는 중…" : "쉽게 바꾸기";
  form.setAttribute("aria-busy", String(busy));
  progress.hidden = !busy;
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const problem = validateFile(selected);
  if (problem) {
    showError(problem);
    input.focus();
    return;
  }
  showError("");
  statusLine.textContent = "";
  setBusy(true);
  const started = Date.now();
  const timer = setInterval(() => {
    progressText.textContent = `문서를 읽고 쉬운 말로 바꾸고 있습니다… ${Math.round((Date.now() - started) / 1000)}초`;
  }, 1000);
  try {
    const body = new FormData();
    body.append("file", selected);
    let response;
    try {
      response = await fetch("/simplify", { method: "POST", body });
    } catch {
      throw new Error(translateError(0));
    }
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(translateError(response.status, data.detail));
    current = { ...data, fileName: selected.name };
    render(current);
    statusLine.textContent = `${data.sentences.length}개 문장을 바꿨습니다.`;
    $("#results-title").focus();
  } catch (error) {
    showError(error.message);
  } finally {
    clearInterval(timer);
    progressText.textContent = "문서를 읽고 쉬운 말로 바꾸고 있습니다…";
    setBusy(false);
  }
});

function render(data) {
  const s = summarize(data);
  $("#summary").replaceChildren(
    ...[["문장", s.total], ["바뀐 문장", s.changed], ["원문 유지", s.kept], ["모델", s.modelVersion]].map(([label, value]) => {
      const item = document.createElement("span");
      item.className = "summary-item";
      item.innerHTML = `<span class="summary-label"></span> <strong></strong>`;
      item.querySelector(".summary-label").textContent = label;
      item.querySelector("strong").textContent = value;
      return item;
    }),
  );
  list.replaceChildren(...data.sentences.map((sentence, i) => renderSentence(data.model_version, sentence, i)));
  results.hidden = false;
}

function cell(kind, label, text) {
  const box = document.createElement("div");
  box.className = `cell ${kind}`;
  const heading = document.createElement("span");
  heading.className = "cell-label";
  heading.textContent = label;
  const p = document.createElement("p");
  p.textContent = text;
  box.append(heading, p);
  return box;
}

function renderSentence(modelVersion, sentence, index) {
  const card = document.createElement("li");
  card.className = "sentence";
  const simple = cell("simple", "쉬운 말", sentence.simple);
  if (sentence.fallback === true) {
    card.classList.add("kept");
    const badge = document.createElement("span");
    badge.className = "badge";
    badge.textContent = "원문 유지";
    badge.title = "숫자나 법령·제도 이름이 바뀔 위험이 있어 원문을 그대로 두었습니다.";
    simple.querySelector(".cell-label").after(badge);
  }
  const columns = document.createElement("div");
  columns.className = "columns";
  columns.append(cell("original", "원문", sentence.original), simple);

  const votes = document.createElement("div");
  votes.className = "votes";
  votes.setAttribute("role", "group");
  votes.setAttribute("aria-label", `${index + 1}번째 문장 평가`);
  const note = document.createElement("span");
  note.className = "vote-note";
  note.setAttribute("aria-live", "polite");
  for (const [vote, icon, label] of [["up", "👍", "좋아요"], ["down", "👎", "싫어요"]]) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "vote-button";
    button.dataset.vote = vote;
    button.setAttribute("aria-pressed", "false");
    button.innerHTML = `<span aria-hidden="true">${icon}</span> `;
    button.append(label);
    button.addEventListener("click", async () => {
      button.disabled = true;
      try {
        const response = await fetch("/feedback", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ model_version: modelVersion, original: sentence.original, simple: sentence.simple, vote }),
        });
        if (!response.ok) throw new Error();
        votes.querySelectorAll(".vote-button").forEach((item) => item.setAttribute("aria-pressed", String(item === button)));
        note.textContent = "평가를 저장했습니다. 고맙습니다.";
      } catch {
        note.textContent = "평가를 저장하지 못했습니다. 다시 눌러 주세요.";
      } finally {
        button.disabled = false;
      }
    });
    votes.append(button);
  }
  votes.append(note);
  card.append(columns, votes);
  return card;
}

document.querySelectorAll(".tabs button").forEach((tab) => {
  tab.addEventListener("click", () => {
    document.querySelectorAll(".tabs button").forEach((item) => item.setAttribute("aria-pressed", String(item === tab)));
    list.dataset.view = tab.dataset.view;
  });
});

async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text);
  } catch {
    const area = document.createElement("textarea"); // clipboard API가 막힌 환경(http 등)
    area.value = text;
    document.body.append(area);
    area.select();
    document.execCommand("copy");
    area.remove();
  }
}

$("#copy").addEventListener("click", async () => {
  if (!current) return;
  await copyText(plainText(current.sentences));
  statusLine.textContent = "쉬운 말 전체를 복사했습니다.";
});

$("#download").addEventListener("click", () => {
  if (!current) return;
  const url = URL.createObjectURL(new Blob([plainText(current.sentences)], { type: "text/plain;charset=utf-8" }));
  const link = document.createElement("a");
  link.href = url;
  link.download = downloadName(current.fileName);
  document.body.append(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
  statusLine.textContent = `${link.download} 파일을 내려받았습니다.`;
});
