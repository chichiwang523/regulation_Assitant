const leftFile = document.querySelector("#leftFile");
const rightFile = document.querySelector("#rightFile");
const leftName = document.querySelector("#leftName");
const rightName = document.querySelector("#rightName");
const compareButton = document.querySelector("#compareButton");
const statusBox = document.querySelector("#status");
const summary = document.querySelector("#summary");
const conclusionPanel = document.querySelector("#conclusionPanel");
const conclusionMeta = document.querySelector("#conclusionMeta");
const conclusionHeadline = document.querySelector("#conclusionHeadline");
const conclusionStats = document.querySelector("#conclusionStats");
const conclusionFindings = document.querySelector("#conclusionFindings");
const conclusionCaveats = document.querySelector("#conclusionCaveats");
const leftSummary = document.querySelector("#leftSummary");
const rightSummary = document.querySelector("#rightSummary");
const resultsBox = document.querySelector("#results");
const resultCount = document.querySelector("#resultCount");
const detailTitle = document.querySelector("#detailTitle");
const detailMeta = document.querySelector("#detailMeta");
const leftText = document.querySelector("#leftText");
const rightText = document.querySelector("#rightText");
const analysisText = document.querySelector("#analysisText");
const evidence = document.querySelector("#evidence");
const questionInput = document.querySelector("#questionInput");
const askButton = document.querySelector("#askButton");
const qaResults = document.querySelector("#qaResults");
const chatMessages = document.querySelector("#chatMessages");
const qaFile = document.querySelector("#qaFile");
const qaFileName = document.querySelector("#qaFileName");
const uploadQaDocButton = document.querySelector("#uploadQaDocButton");
const qaDocStatus = document.querySelector("#qaDocStatus");
const useCorpus = document.querySelector("#useCorpus");
const modelMode = document.querySelector("#modelMode");
const apiKeyInput = document.querySelector("#apiKeyInput");
const modelNote = document.querySelector("#modelNote");
const compareQuota = document.querySelector("#compareQuota");
const qaQuota = document.querySelector("#qaQuota");
const feedbackDialog = document.querySelector("#feedbackDialog");
const feedbackForm = document.querySelector("#feedbackForm");
const feedbackOpenButton = document.querySelector("#feedbackOpenButton");
const feedbackCloseButton = document.querySelector("#feedbackCloseButton");
const feedbackType = document.querySelector("#feedbackType");
const feedbackContact = document.querySelector("#feedbackContact");
const feedbackMessage = document.querySelector("#feedbackMessage");

let currentResults = [];
let currentQaDocId = "";
let quotas = JSON.parse(localStorage.getItem("regCopilotQuotas") || '{"compare":10,"qa":20}');

renderQuotas();

document.querySelectorAll(".tab").forEach((tab) => {
  tab.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach((node) => node.classList.remove("active"));
    document.querySelectorAll(".page").forEach((node) => node.classList.remove("active"));
    tab.classList.add("active");
    document.querySelector(`#${tab.dataset.target}`).classList.add("active");
  });
});

leftFile.addEventListener("change", () => {
  leftName.textContent = leftFile.files[0]?.name || "未选择 PDF";
});

rightFile.addEventListener("change", () => {
  rightName.textContent = rightFile.files[0]?.name || "未选择 PDF";
});

qaFile.addEventListener("change", () => {
  qaFileName.textContent = qaFile.files[0]?.name || "未选择 PDF";
});

compareButton.addEventListener("click", async () => {
  if (!consumeQuota("compare")) return;
  if (!leftFile.files[0] || !rightFile.files[0]) {
    refundQuota("compare");
    showStatus("请先选择两份 PDF。", true);
    return;
  }

  const formData = new FormData();
  formData.append("left", leftFile.files[0]);
  formData.append("right", rightFile.files[0]);

  compareButton.disabled = true;
  showStatus("正在解析 PDF 并匹配条款...");
  resultsBox.innerHTML = "";
  resultCount.textContent = "0";

  try {
    const response = await fetch("/api/compare", {
      method: "POST",
      body: formData,
    });
    const payload = await response.json();
    if (!response.ok || payload.error) {
      throw new Error(payload.error || "对比失败。");
    }

    currentResults = payload.results || [];
    renderSummary(payload.left, payload.right);
    renderConclusion(payload.conclusion);
    renderResults(currentResults);
    showStatus(`完成：共发现 ${currentResults.length} 条匹配/差异记录。`);
    if (currentResults.length > 0) {
      selectResult(0);
    }
  } catch (error) {
    refundQuota("compare");
    showStatus(error.message, true);
  } finally {
    compareButton.disabled = false;
  }
});

modelMode.addEventListener("change", () => {
  const ownKey = modelMode.value === "byok";
  apiKeyInput.hidden = !ownKey;
  modelNote.textContent = ownKey
    ? "自有 API Key 模式：费用和效果取决于你的模型供应商；本 demo 不会上传或保存 Key。"
    : "平台模式示例：10 次对比 10 元，20 次问答 10 元。实际效果会受所选大模型影响。";
});

feedbackOpenButton.addEventListener("click", () => feedbackDialog.showModal());
feedbackCloseButton.addEventListener("click", () => feedbackDialog.close());
feedbackForm.addEventListener("submit", submitFeedback);

uploadQaDocButton.addEventListener("click", uploadQaDocument);
askButton.addEventListener("click", askQuestion);
questionInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter") {
    askQuestion();
  }
});

function showStatus(message, isError = false) {
  statusBox.hidden = false;
  statusBox.textContent = message;
  statusBox.classList.toggle("error", isError);
}

function showQaStatus(message, isError = false) {
  qaDocStatus.hidden = false;
  qaDocStatus.textContent = message;
  qaDocStatus.classList.toggle("error", isError);
}

function renderSummary(left, right) {
  summary.hidden = false;
  leftSummary.textContent = `${left.filename}，${left.pages} 页，识别 ${left.clauses} 个条款`;
  rightSummary.textContent = `${right.filename}，${right.pages} 页，识别 ${right.clauses} 个条款`;
}

function renderConclusion(conclusion) {
  if (!conclusion) return;
  conclusionPanel.hidden = false;
  conclusionMeta.textContent = `${conclusion.left} vs ${conclusion.right}`;
  conclusionHeadline.textContent = conclusion.headline;

  conclusionStats.innerHTML = "";
  Object.entries(conclusion.counts || {}).forEach(([label, count]) => {
    conclusionStats.append(makeBadge(`${label} ${count}`));
  });
  Object.entries(conclusion.risks || {}).forEach(([label, count]) => {
    conclusionStats.append(makeBadge(`风险${label} ${count}`, riskClass(label)));
  });

  conclusionFindings.innerHTML = "";
  (conclusion.key_findings || []).forEach((item) => {
    const li = document.createElement("li");
    li.textContent = `${item.type} / 风险${item.risk} / ${item.heading}：${item.summary}`;
    conclusionFindings.append(li);
  });

  conclusionCaveats.innerHTML = "";
  (conclusion.caveats || []).forEach((line) => {
    const li = document.createElement("li");
    li.textContent = line;
    conclusionCaveats.append(li);
  });
}

function renderResults(results) {
  resultCount.textContent = String(results.length);
  resultsBox.innerHTML = "";
  results.forEach((item, index) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "result-item";
    button.addEventListener("click", () => selectResult(index));

    const badges = document.createElement("div");
    badges.className = "badges";
    badges.append(makeBadge(item.change_type));
    badges.append(makeBadge(`风险 ${item.risk}`, riskClass(item.risk)));
    badges.append(makeBadge(`匹配 ${Math.round((item.score || 0) * 100)}%`));

    const title = document.createElement("div");
    title.className = "result-title";
    title.textContent = item.left?.heading || item.right?.heading || "未命名条款";

    const pages = document.createElement("div");
    pages.className = "result-pages";
    pages.textContent = pageText(item);

    button.append(badges, title, pages);
    resultsBox.append(button);
  });
}

function makeBadge(text, extraClass = "") {
  const badge = document.createElement("span");
  badge.className = `badge ${extraClass}`.trim();
  badge.textContent = text;
  return badge;
}

function riskClass(risk) {
  if (risk === "高") return "risk-high";
  if (risk === "中") return "risk-mid";
  return "risk-low";
}

function pageText(item) {
  const left = item.left ? `左 P${item.left.start_page}-${item.left.end_page}` : "左 无";
  const right = item.right ? `右 P${item.right.start_page}-${item.right.end_page}` : "右 无";
  return `${left} / ${right}`;
}

function selectResult(index) {
  const item = currentResults[index];
  if (!item) return;

  [...resultsBox.querySelectorAll(".result-item")].forEach((node, nodeIndex) => {
    node.classList.toggle("active", nodeIndex === index);
  });

  detailTitle.textContent = item.change_type;
  detailMeta.textContent = `${pageText(item)} / 匹配度 ${Math.round((item.score || 0) * 100)}%`;
  leftText.textContent = item.left?.text || "左侧未匹配到对应条款。";
  rightText.textContent = item.right?.text || "右侧未匹配到对应条款。";
  analysisText.textContent = item.summary || "暂无解释。";
  evidence.innerHTML = "";

  (item.evidence || []).forEach((line) => {
    const li = document.createElement("li");
    li.textContent = line;
    evidence.append(li);
  });
}

async function uploadQaDocument() {
  if (!qaFile.files[0]) {
    showQaStatus("请先选择一份法规 PDF。", true);
    return;
  }

  const formData = new FormData();
  formData.append("document", qaFile.files[0]);
  uploadQaDocButton.disabled = true;
  showQaStatus("正在载入法规...");

  try {
    const response = await fetch("/api/upload-document", {
      method: "POST",
      body: formData,
    });
    const payload = await response.json();
    if (!response.ok || payload.error) {
      throw new Error(payload.error || "载入失败。");
    }
    currentQaDocId = payload.doc_id;
    useCorpus.checked = false;
    showQaStatus(`已载入：${payload.filename}，${payload.pages} 页，识别 ${payload.clauses} 个条款。`);
    appendChat("assistant", `已载入 ${payload.filename}。现在可以针对这份法规提问。`);
  } catch (error) {
    showQaStatus(error.message, true);
  } finally {
    uploadQaDocButton.disabled = false;
  }
}

async function askQuestion() {
  const question = questionInput.value.trim();
  if (!question) {
    appendChat("assistant", "请输入一个法规问题。");
    return;
  }
  if (!useCorpus.checked && !currentQaDocId) {
    appendChat("assistant", "请先上传并载入一份法规 PDF，或勾选“改用本地法规库检索”。");
    return;
  }
  if (!consumeQuota("qa")) return;

  askButton.disabled = true;
  appendChat("user", question);
  const waiting = appendChat("assistant", useCorpus.checked ? "正在检索本地法规库..." : "正在检索已上传法规...");
  qaResults.innerHTML = "";
  questionInput.value = "";

  try {
    const body = useCorpus.checked ? { question } : { question, doc_id: currentQaDocId };
    const response = await fetch("/api/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const payload = await response.json();
    if (!response.ok || payload.error) {
      throw new Error(payload.error || "检索失败。");
    }
    waiting.textContent = payload.answer;
    renderQaResults(payload.results || []);
  } catch (error) {
    refundQuota("qa");
    waiting.textContent = error.message;
  } finally {
    askButton.disabled = false;
  }
}

function renderQuotas() {
  compareQuota.textContent = String(quotas.compare);
  qaQuota.textContent = String(quotas.qa);
  localStorage.setItem("regCopilotQuotas", JSON.stringify(quotas));
}

function consumeQuota(type) {
  if (modelMode.value === "byok") return true;
  if (quotas[type] <= 0) {
    const label = type === "compare" ? "对比" : "问答";
    const message = `${label}次数已用完。Demo 套餐示例：10 次对比 10 元，20 次问答 10 元；也可以切换到自有 API Key 模式。`;
    if (type === "compare") showStatus(message, true);
    else appendChat("assistant", message);
    return false;
  }
  quotas[type] -= 1;
  renderQuotas();
  return true;
}

function refundQuota(type) {
  if (modelMode.value === "byok") return;
  quotas[type] += 1;
  renderQuotas();
}

async function submitFeedback(event) {
  event.preventDefault();
  const message = feedbackMessage.value.trim();
  if (!message) return;
  const response = await fetch("/api/feedback", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      user: "demo.engineer@oem.local",
      type: feedbackType.value,
      contact: feedbackContact.value,
      message,
    }),
  });
  const payload = await response.json();
  if (!response.ok || payload.error) {
    alert(payload.error || "反馈提交失败。");
    return;
  }
  feedbackMessage.value = "";
  feedbackDialog.close();
  appendChat("assistant", payload.message || "反馈已提交。");
}

function appendChat(role, text) {
  const node = document.createElement("div");
  node.className = `chat-message ${role}`;
  node.textContent = text;
  chatMessages.append(node);
  chatMessages.scrollTop = chatMessages.scrollHeight;
  return node;
}

function renderQaResults(results) {
  qaResults.innerHTML = "";
  results.forEach((item) => {
    const card = document.createElement("article");
    card.className = "qa-card";

    const title = document.createElement("strong");
    title.textContent = `${item.code} / ${item.title}`;

    const meta = document.createElement("span");
    meta.className = "result-pages";
    meta.textContent = `${item.domain} / ${item.region} / ${item.page} / score ${item.score}`;

    const heading = document.createElement("p");
    heading.textContent = item.heading;

    const text = document.createElement("p");
    text.textContent = item.text;

    card.append(title, meta, heading, text);
    qaResults.append(card);
  });
}
