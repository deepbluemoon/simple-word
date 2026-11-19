const form = document.querySelector("#upload-form");
const status = document.querySelector("#status");
const results = document.querySelector("#results");
const sentenceList = document.querySelector("#sentences");

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const button = form.querySelector("button");
  button.disabled = true;
  status.textContent = "문서를 바꾸고 있습니다…";
  results.hidden = true;
  try {
    const response = await fetch("/simplify", { method: "POST", body: new FormData(form) });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "문서를 처리하지 못했습니다.");
    sentenceList.replaceChildren(...data.sentences.map((sentence) => renderSentence(data.model_version, sentence)));
    results.hidden = false;
    status.textContent = `${data.sentences.length}개 문장을 바꿨습니다.`;
  } catch (error) {
    status.textContent = error.message;
  } finally {
    button.disabled = false;
  }
});

function renderSentence(modelVersion, sentence) {
  const card = document.createElement("article");
  card.className = "sentence";
  const columns = document.createElement("div");
  columns.className = "sentence-columns";
  for (const text of [sentence.original, sentence.simple]) {
    const cell = document.createElement("p");
    cell.textContent = text;
    columns.append(cell);
  }
  const votes = document.createElement("div");
  votes.className = "vote-buttons";
  for (const [vote, label] of [["up", "👍 좋아요"], ["down", "👎 싫어요"]]) {
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = label;
    button.setAttribute("aria-label", `${sentence.original}: ${label}`);
    button.addEventListener("click", async () => {
      try {
        const response = await fetch("/feedback", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ model_version: modelVersion, ...sentence, vote }),
        });
        if (!response.ok) throw new Error();
        votes.querySelectorAll("button").forEach((item) => item.setAttribute("aria-pressed", String(item === button)));
        status.textContent = "평가를 저장했습니다.";
      } catch {
        status.textContent = "평가를 저장하지 못했습니다.";
      }
    });
    votes.append(button);
  }
  card.append(columns, votes);
  return card;
}
