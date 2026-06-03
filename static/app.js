const leftFile = document.querySelector("#leftFile");
const loginGate = document.querySelector("#loginGate");
const loginForm = document.querySelector("#loginForm");
const loginEmail = document.querySelector("#loginEmail");
const loginCode = document.querySelector("#loginCode");
const loginCodeLabel = document.querySelector("#loginCodeLabel");
const loginStatus = document.querySelector("#loginStatus");
const accountEmail = document.querySelector("#accountEmail");
const accountRole = document.querySelector("#accountRole");
const logoutButton = document.querySelector("#logoutButton");
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
const parameterPanel = document.querySelector("#parameterPanel");
const parameterCount = document.querySelector("#parameterCount");
const parameterRows = document.querySelector("#parameterRows");
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
const qaDocStatus = document.querySelector("#qaDocStatus");
const useCorpus = document.querySelector("#useCorpus");
const modelMode = document.querySelector("#modelMode");
const apiKeyInput = document.querySelector("#apiKeyInput");
const modelNote = document.querySelector("#modelNote");
const llmStatus = document.querySelector("#llmStatus");
const compareQuota = document.querySelector("#compareQuota");
const qaQuota = document.querySelector("#qaQuota");
const feedbackDialog = document.querySelector("#feedbackDialog");
const feedbackForm = document.querySelector("#feedbackForm");
const feedbackOpenButton = document.querySelector("#feedbackOpenButton");
const feedbackCloseButton = document.querySelector("#feedbackCloseButton");
const feedbackType = document.querySelector("#feedbackType");
const feedbackContact = document.querySelector("#feedbackContact");
const feedbackMessage = document.querySelector("#feedbackMessage");
const feedbackContextNote = document.querySelector("#feedbackContextNote");
const feedbackResultButton = document.querySelector("#feedbackResultButton");
const settingsButton = document.querySelector("#settingsButton");
const settingsClose = document.querySelector("#settingsClose");
const settingsOverlay = document.querySelector("#settingsOverlay");
const settingsDrawer = document.querySelector("#settingsDrawer");
const noticeBar = document.querySelector("#noticeBar");
const noticeClose = document.querySelector("#noticeClose");
const feedbackFab = document.querySelector("#feedbackFab");
const adminSection = document.querySelector("#adminSection");
const adminOpenButton = document.querySelector("#adminOpenButton");
const adminDialog = document.querySelector("#adminDialog");
const adminCloseButton = document.querySelector("#adminCloseButton");
const adminTabs = document.querySelectorAll(".admin-tab");
const adminUsage = document.querySelector("#adminUsage");
const adminUploads = document.querySelector("#adminUploads");
const adminFeedback = document.querySelector("#adminFeedback");
const leftSize = document.querySelector("#leftSize");
const rightSize = document.querySelector("#rightSize");
const qaSize = document.querySelector("#qaSize");
const modelBadge = document.querySelector("#modelBadge");

let currentResults = [];
let currentParameterRows = [];
let currentFilter = "actionable";
let currentQaDocId = "";
let selectedResultIndex = -1;
let feedbackContext = {};
let lastQaQuestion = "";
let currentUser = null;
let adminEmail = "";
let quotas = JSON.parse(localStorage.getItem("regCopilotQuotas") || '{"compare":10,"qa":20}');

renderQuotas();
initSession();

document.querySelectorAll(".tab").forEach((tab) => {
  tab.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach((node) => node.classList.remove("active"));
    document.querySelectorAll(".page").forEach((node) => node.classList.remove("active"));
    tab.classList.add("active");
    document.querySelector(`#${tab.dataset.target}`).classList.add("active");
  });
});

loginForm.addEventListener("submit", login);
logoutButton.addEventListener("click", logout);
loginEmail.addEventListener("input", updateLoginCodeLabel);

function updateLoginCodeLabel() {
  const isAdmin = adminEmail && loginEmail.value.trim().toLowerCase() === adminEmail;
  loginCodeLabel.textContent = isAdmin ? "管理员密码" : "测试邀请码";
  loginCode.placeholder = isAdmin ? "请输入管理员密码" : "向管理员获取";
}

document.querySelectorAll(".filter-chip").forEach((chip) => {
  chip.addEventListener("click", () => {
    document.querySelectorAll(".filter-chip").forEach((node) => node.classList.remove("active"));
    chip.classList.add("active");
    currentFilter = chip.dataset.filter;
    renderResults(currentResults);
  });
});

function formatFileSize(bytes) {
  if (!bytes && bytes !== 0) return "";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function setupDropzone(input, nameEl, sizeEl, onSelected) {
  const zone = input.closest(".dropzone");
  if (!zone) return;
  const prompt = zone.querySelector(".dropzone-prompt");
  const done = zone.querySelector(".dropzone-done");

  const render = () => {
    const file = input.files[0];
    if (file) {
      if (nameEl) nameEl.textContent = file.name;
      if (sizeEl) sizeEl.textContent = formatFileSize(file.size);
      zone.classList.add("filled");
      if (prompt) prompt.hidden = true;
      if (done) done.hidden = false;
    } else {
      zone.classList.remove("filled");
      if (prompt) prompt.hidden = false;
      if (done) done.hidden = true;
    }
  };

  input.addEventListener("change", () => {
    render();
    if (input.files[0] && typeof onSelected === "function") onSelected();
  });

  zone.addEventListener("dragover", (event) => {
    event.preventDefault();
    zone.classList.add("dragover");
  });
  zone.addEventListener("dragleave", () => zone.classList.remove("dragover"));
  zone.addEventListener("drop", (event) => {
    event.preventDefault();
    zone.classList.remove("dragover");
    const file = event.dataTransfer?.files?.[0];
    if (!file) return;
    if (!/\.(pdf|docx|txt|md)$/i.test(file.name || "")) return;
    const transfer = new DataTransfer();
    transfer.items.add(file);
    input.files = transfer.files;
    input.dispatchEvent(new Event("change"));
  });
}

setupDropzone(leftFile, leftName, leftSize);
setupDropzone(rightFile, rightName, rightSize);
setupDropzone(qaFile, qaFileName, qaSize, uploadQaDocument);

function toggleDrawer(open) {
  if (!settingsDrawer) return;
  settingsDrawer.classList.toggle("open", open);
  settingsDrawer.setAttribute("aria-hidden", open ? "false" : "true");
  settingsOverlay.hidden = !open;
  settingsButton.setAttribute("aria-expanded", open ? "true" : "false");
}

settingsButton.addEventListener("click", () => toggleDrawer(!settingsDrawer.classList.contains("open")));
settingsClose.addEventListener("click", () => toggleDrawer(false));
settingsOverlay.addEventListener("click", () => toggleDrawer(false));
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && settingsDrawer.classList.contains("open")) toggleDrawer(false);
});

if (localStorage.getItem("regCopilotNoticeClosed") === "1") {
  noticeBar.hidden = true;
}
noticeClose.addEventListener("click", () => {
  noticeBar.hidden = true;
  localStorage.setItem("regCopilotNoticeClosed", "1");
});

compareButton.addEventListener("click", async () => {
  if (!consumeQuota("compare")) return;
  if (!leftFile.files[0] || !rightFile.files[0]) {
    refundQuota("compare");
    showStatus("请先选择两份文件（PDF / Word .docx / txt）。", true);
    return;
  }

  const formData = new FormData();
  formData.append("left", leftFile.files[0]);
  formData.append("right", rightFile.files[0]);

  compareButton.disabled = true;
  showStatus("正在解析文件并匹配条款（扫描件需 OCR，可能稍慢）...");
  resultsBox.innerHTML = "";
  resultCount.textContent = "0";
  parameterPanel.hidden = true;
  parameterRows.innerHTML = "";
  selectedResultIndex = -1;
  feedbackResultButton.disabled = true;

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
    currentParameterRows = payload.parameter_matrix || [];
    selectedResultIndex = -1;
    renderSummary(payload.left, payload.right);
    renderConclusion(payload.conclusion);
    renderParameterMatrix(currentParameterRows);
    renderResults(currentResults);
    showStatus(`完成：共发现 ${currentResults.length} 条匹配/差异记录，抽取 ${currentParameterRows.length} 条关键参数。`);
    const firstVisible = filteredResults(currentResults)[0];
    if (firstVisible) {
      selectResult(firstVisible.index);
    }
  } catch (error) {
    refundQuota("compare");
    showStatus(error.message, true);
  } finally {
    compareButton.disabled = false;
  }
});

modelMode.addEventListener("change", () => {
  const byok = modelMode.value === "byok";
  apiKeyInput.hidden = !byok;
  modelNote.textContent = byok
    ? "将使用你自己的 LLM API Key 调用，不占用测试额度；密钥只用于本次请求、不会保存。"
    : "内置模型由平台统一调用。测试账号使用次数有限，主要是出于 LLM 模型成本的考虑。";
  setModelBadge(byok ? "byok" : "auto");
});

function setModelBadge(tier) {
  if (!modelBadge) return;
  modelBadge.classList.remove("local", "pro");
  if (tier === "local") {
    modelBadge.classList.add("local");
    modelBadge.textContent = "📁 本地检索";
  } else if (tier === "byok") {
    modelBadge.textContent = "🔑 自有模型";
  } else {
    modelBadge.textContent = "🤖 内置模型";
  }
}

setModelBadge(modelMode.value === "byok" ? "byok" : "auto");

feedbackOpenButton.addEventListener("click", () => openFeedback("general"));
feedbackResultButton.addEventListener("click", () => {
  if (selectedResultIndex < 0) return;
  openFeedback("compare_result", buildCompareFeedbackContext(currentResults[selectedResultIndex], selectedResultIndex));
});
feedbackCloseButton.addEventListener("click", () => feedbackDialog.close());
feedbackForm.addEventListener("submit", submitFeedback);

if (feedbackFab) {
  feedbackFab.addEventListener("click", () => {
    toggleDrawer(false);
    openFeedback("general");
  });
}
if (adminOpenButton) {
  adminOpenButton.addEventListener("click", () => {
    toggleDrawer(false);
    openAdmin();
  });
}
if (adminCloseButton) {
  adminCloseButton.addEventListener("click", () => adminDialog.close());
}
adminTabs.forEach((tab) => {
  tab.addEventListener("click", () => switchAdminTab(tab.dataset.admin));
});

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
  const visible = filteredResults(results);
  resultCount.textContent = `${visible.length}/${results.length}`;
  resultsBox.innerHTML = "";
  if (!visible.length) {
    const empty = document.createElement("div");
    empty.className = "empty-state";
    empty.textContent = "当前筛选下没有差异。";
    resultsBox.append(empty);
    return;
  }
  visible.forEach(({ item, index }) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "result-item";
    button.dataset.index = String(index);
    button.addEventListener("click", () => selectResult(index));

    const badges = document.createElement("div");
    badges.className = "badges";
    badges.append(makeBadge(item.change_type));
    badges.append(makeBadge(`风险 ${item.risk}`, riskClass(item.risk)));
    badges.append(makeBadge(`匹配 ${Math.round((item.score || 0) * 100)}%`));
    if (isParameterResult(item)) {
      badges.append(makeBadge("含参数", "param-badge"));
    }

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

function filteredResults(results) {
  return results
    .map((item, index) => ({ item, index }))
    .filter(({ item }) => {
      if (currentFilter === "all") return true;
      if (currentFilter === "high") return item.risk === "高";
      if (currentFilter === "parameter") return isParameterResult(item);
      return isActionableResult(item);
    });
}

function isActionableResult(item) {
  return ["阈值/数值变化", "测试方法变化", "适用范围变化", "引用标准变化", "定义变化", "内容修改"].includes(item.change_type);
}

function isParameterResult(item) {
  return item.change_type === "阈值/数值变化" || (item.summary || "").includes("数值") || (item.summary || "").includes("单位");
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
  selectedResultIndex = index;
  feedbackResultButton.disabled = false;

  [...resultsBox.querySelectorAll(".result-item")].forEach((node, nodeIndex) => {
    node.classList.toggle("active", Number(node.dataset.index) === index);
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

function renderParameterMatrix(rows) {
  parameterRows.innerHTML = "";
  parameterCount.textContent = String(rows.length);
  parameterPanel.hidden = rows.length === 0;
  rows.forEach((row) => {
    const tr = document.createElement("tr");
    if (row.changed) tr.classList.add("changed-param");

    const parameter = document.createElement("td");
    parameter.textContent = row.parameter;

    const left = document.createElement("td");
    left.append(makeValueBlock(row.left_values || "未识别", row.left_context));

    const right = document.createElement("td");
    right.append(makeValueBlock(row.right_values || "未识别", row.right_context));

    const location = document.createElement("td");
    location.textContent = [row.left_location && `左 ${row.left_location}`, row.right_location && `右 ${row.right_location}`]
      .filter(Boolean)
      .join(" / ");

    const risk = document.createElement("td");
    risk.append(makeBadge(row.risk, riskClass(row.risk)));
    risk.append(makeBadge(row.change_type));

    tr.append(parameter, left, right, location, risk);
    parameterRows.append(tr);
  });
}

function makeValueBlock(value, context) {
  const wrap = document.createElement("div");
  wrap.className = "value-block";
  const strong = document.createElement("strong");
  strong.textContent = value;
  wrap.append(strong);
  if (context) {
    const small = document.createElement("small");
    small.textContent = context;
    wrap.append(small);
  }
  return wrap;
}

async function uploadQaDocument() {
  if (!qaFile.files[0]) {
    showQaStatus("请先选择一份法规文件（PDF / Word .docx / txt）。", true);
    return;
  }

  const formData = new FormData();
  formData.append("document", qaFile.files[0]);
  qaFile.disabled = true;
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
    showQaStatus(`已载入：${payload.filename}，${payload.pages} 页，识别 ${payload.clauses} 个条款，可以直接提问。`);
    appendChat("assistant", `已载入 ${payload.filename}。现在可以针对这份法规提问。`);
  } catch (error) {
    showQaStatus(error.message, true);
  } finally {
    qaFile.disabled = false;
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
  if (modelMode.value === "byok" && !apiKeyInput.value.trim()) {
    appendChat("assistant", "你选择了“使用我自己的 LLM”，请先在右上角设置里填写你的 API Key。");
    return;
  }
  if (!consumeQuota("qa")) return;

  askButton.disabled = true;
  lastQaQuestion = question;
  appendChat("user", question);
  const waiting = appendChat("assistant", useCorpus.checked ? "正在检索本地法规库..." : "正在检索已上传法规...");
  qaResults.innerHTML = "";
  questionInput.value = "";

  try {
    const body = useCorpus.checked ? { question } : { question, doc_id: currentQaDocId };
    body.use_llm = true;
    if (modelMode.value === "byok") {
      body.api_key = apiKeyInput.value.trim();
    }
    const response = await fetch("/api/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const payload = await response.json();
    if (!response.ok || payload.error) {
      throw new Error(payload.error || "检索失败。");
    }
    setAnswerContent(waiting, payload.answer);
    appendLlmMeta(waiting, payload.llm);
    addFeedbackAction(
      waiting,
      "反馈这次问答",
      "qa_answer",
      {
        question: payload.question || lastQaQuestion,
        answer: payload.answer,
        llm: payload.llm || {},
        use_corpus: useCorpus.checked,
        doc_id: currentQaDocId,
        top_results: (payload.results || []).slice(0, 3),
      }
    );
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
      user: currentUser?.email || "",
      type: feedbackType.value,
      contact: feedbackContact.value,
      message,
      context: feedbackContext,
    }),
  });
  const payload = await response.json();
  if (!response.ok || payload.error) {
    alert(payload.error || "反馈提交失败。");
    return;
  }
  feedbackMessage.value = "";
  feedbackContext = {};
  renderFeedbackContext();
  feedbackDialog.close();
  appendChat("assistant", payload.message || "反馈已提交。");
}

async function initSession() {
  try {
    const response = await fetch("/api/session");
    const payload = await response.json();
    adminEmail = (payload.admin_email || "").trim().toLowerCase();
    updateLoginCodeLabel();
    renderLlmStatus(payload.llm);
    setCurrentUser(payload.user);
  } catch (error) {
    renderLlmStatus(null);
    setCurrentUser(null);
  }
}

function renderLlmStatus(config) {
  if (!llmStatus) return;
  if (!config) {
    llmStatus.textContent = "模型状态：无法读取配置";
    llmStatus.classList.add("error");
    return;
  }
  if (!config.enabled) {
    llmStatus.textContent = "内置模型暂未启用，问答会回退到本地规则检索。";
    llmStatus.classList.add("error");
    return;
  }
  llmStatus.classList.remove("error");
  llmStatus.textContent = "内置模型已就绪，可直接开始问答。";
}

async function login(event) {
  event.preventDefault();
  loginStatus.hidden = true;
  const response = await fetch("/api/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      email: loginEmail.value.trim(),
      code: loginCode.value,
    }),
  });
  const payload = await response.json();
  if (!response.ok || payload.error) {
    showLoginStatus(payload.error || "登录失败。", true);
    return;
  }
  loginCode.value = "";
  setCurrentUser(payload.user);
}

async function logout() {
  await fetch("/api/logout", { method: "POST" });
  setCurrentUser(null);
}

function setCurrentUser(user) {
  currentUser = user;
  loginGate.hidden = Boolean(user);
  accountEmail.textContent = user?.email || "-";
  accountRole.textContent = user ? (user.role === "admin" ? "管理员" : "测试用户") : "未登录";
  const isAdmin = Boolean(user) && user.role === "admin";
  if (feedbackFab) feedbackFab.hidden = !user;
  if (adminSection) adminSection.hidden = !isAdmin;
}

const ADMIN_ACTION_LABEL = {
  login: "登录",
  upload: "上传法规",
  compare: "法规对比",
  ask: "问答检索",
  answer: "Agent 输出",
};

function formatTimestamp(value) {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("zh-CN", { hour12: false });
}

function openAdmin() {
  if (!adminDialog) return;
  adminDialog.showModal();
  switchAdminTab("usage");
}

function switchAdminTab(name) {
  adminTabs.forEach((tab) => tab.classList.toggle("active", tab.dataset.admin === name));
  adminUsage.hidden = name !== "usage";
  adminUploads.hidden = name !== "uploads";
  adminFeedback.hidden = name !== "feedback";
  adminUsage.classList.toggle("active", name === "usage");
  adminUploads.classList.toggle("active", name === "uploads");
  adminFeedback.classList.toggle("active", name === "feedback");
  // Always re-fetch the active tab so each open/switch shows fresh server data
  // (avoids stale views when other testers added records meanwhile).
  if (name === "usage") loadAdminUsage();
  else if (name === "uploads") loadAdminUploads();
  else if (name === "feedback") loadAdminFeedback();
}

async function loadAdminUsage() {
  adminUsage.innerHTML = '<p class="admin-empty">加载中…</p>';
  try {
    const res = await fetch("/api/admin/usage", { cache: "no-store" });
    if (res.status === 401 || res.status === 403) {
      adminUsage.innerHTML = '<p class="admin-empty">无法读取：当前账号非管理员或登录已过期，请重新登录管理员账号。</p>';
      return;
    }
    const data = await res.json();
    const rows = data.usage || [];
    if (!rows.length) {
      adminUsage.innerHTML = '<p class="admin-empty">暂无使用记录。</p>';
      return;
    }
    const body = rows
      .map((row) => {
        const action = ADMIN_ACTION_LABEL[row.action] || row.action || "-";
        return `<tr><td>${formatTimestamp(row.at)}</td><td>${escapeHtml(row.user || "-")}</td>` +
          `<td><span class="admin-badge ${escapeHtml(row.action || "")}">${escapeHtml(action)}</span></td>` +
          `<td>${escapeHtml(row.detail || "")}</td></tr>`;
      })
      .join("");
    adminUsage.innerHTML =
      `<table class="admin-table"><thead><tr><th>时间</th><th>用户</th><th>操作</th><th>详情</th></tr></thead><tbody>${body}</tbody></table>`;
  } catch (error) {
    adminUsage.innerHTML = '<p class="admin-empty">加载失败。</p>';
  }
}

async function loadAdminUploads() {
  adminUploads.innerHTML = '<p class="admin-empty">加载中…</p>';
  try {
    const res = await fetch("/api/admin/uploads", { cache: "no-store" });
    if (res.status === 401 || res.status === 403) {
      adminUploads.innerHTML = '<p class="admin-empty">无法读取：当前账号非管理员或登录已过期，请重新登录管理员账号。</p>';
      return;
    }
    const data = await res.json();
    const rows = data.documents || [];
    if (!rows.length) {
      adminUploads.innerHTML = '<p class="admin-empty">暂无归档法规。</p>';
      return;
    }
    const body = rows
      .map((row) => {
        const uploaders = (row.uploaded_by || []).join("、") || "-";
        return `<tr><td>${escapeHtml(row.name || "-")}</td><td>${row.pages || 0} 页 / ${row.clauses || 0} 条</td>` +
          `<td>${formatFileSize(row.size_bytes || 0)}</td><td>${escapeHtml(uploaders)}</td>` +
          `<td>${formatTimestamp(row.first_uploaded_at)}</td><td>${row.access_count || 0}</td></tr>`;
      })
      .join("");
    adminUploads.innerHTML =
      `<table class="admin-table"><thead><tr><th>法规名称</th><th>规模</th><th>大小</th><th>上传者</th><th>首次归档</th><th>命中</th></tr></thead><tbody>${body}</tbody></table>`;
  } catch (error) {
    adminUploads.innerHTML = '<p class="admin-empty">加载失败。</p>';
  }
}

async function loadAdminFeedback() {
  adminFeedback.innerHTML = '<p class="admin-empty">加载中…</p>';
  try {
    const res = await fetch("/api/admin/feedback", { cache: "no-store" });
    if (res.status === 401 || res.status === 403) {
      adminFeedback.innerHTML = '<p class="admin-empty">无法读取：当前账号非管理员或登录已过期，请重新登录管理员账号。</p>';
      return;
    }
    const data = await res.json();
    const rows = data.feedback || [];
    if (!rows.length) {
      adminFeedback.innerHTML = '<p class="admin-empty">暂无测试反馈。</p>';
      return;
    }
    const body = rows
      .map(
        (row) =>
          `<tr><td>${formatTimestamp(row.created_at)}</td><td>${escapeHtml(row.user || "-")}</td>` +
          `<td>${escapeHtml(row.type || "-")}</td><td>${escapeHtml(row.message || "")}</td>` +
          `<td>${escapeHtml(row.contact || "")}</td></tr>`
      )
      .join("");
    adminFeedback.innerHTML =
      `<table class="admin-table"><thead><tr><th>时间</th><th>用户</th><th>类型</th><th>内容</th><th>联系方式</th></tr></thead><tbody>${body}</tbody></table>`;
  } catch (error) {
    adminFeedback.innerHTML = '<p class="admin-empty">加载失败。</p>';
  }
}

function showLoginStatus(message, isError) {
  loginStatus.hidden = false;
  loginStatus.textContent = message;
  loginStatus.classList.toggle("error", isError);
}

function appendChat(role, text) {
  const node = document.createElement("div");
  node.className = `chat-message ${role}`;
  node.textContent = text;
  chatMessages.append(node);
  chatMessages.scrollTop = chatMessages.scrollHeight;
  return node;
}

const ANSWER_UNIT = "%|mm|cm|km/h|km|kg|kN|daN|N·m|Nm|kPa|MPa|dB\\(A\\)|dB|kW|°C|℃|°F|g/km|g·GA|ppm|lux|lx|bar|cd|ms|min|V|A|W|s|h|°|N|m|g|页|条";

function escapeHtml(value) {
  return String(value).replace(/[&<>"]/g, (ch) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
  }[ch]));
}

function formatAnswer(text) {
  let html = escapeHtml(text);
  html = html.replace(/\*\*([^*]+)\*\*/g, '<span class="answer-key">$1</span>');
  html = html.replace(/\[(\d+)\]/g, '<sup class="answer-cite">[$1]</sup>');
  const unitRe = new RegExp("([-+]?\\d+(?:[.,]\\d+)?\\s?(?:" + ANSWER_UNIT + "))", "g");
  html = html.replace(unitRe, '<span class="answer-number">$1</span>');
  return html;
}

function setAnswerContent(node, text) {
  node.textContent = "";
  const body = document.createElement("div");
  body.className = "answer-body";
  body.innerHTML = formatAnswer(text || "");
  node.append(body);
}

function appendLlmMeta(parent, llm) {
  if (!llm) return;
  const meta = document.createElement("small");
  meta.className = "llm-answer-meta";
  if (llm.used) {
    meta.textContent = "已调用 AI 模型生成，结论基于检索到的法规原文。";
    setModelBadge(modelMode.value === "byok" ? "byok" : "auto");
  } else {
    meta.classList.add("fallback");
    meta.textContent = "⚠ 未调用 AI 模型，本结果来自本地规则检索，准确性较低，请以原文为准。";
    setModelBadge("local");
  }
  parent.append(meta);
}

function openFeedback(source = "general", context = {}) {
  feedbackContext = {
    source,
    page: document.querySelector(".tab.active")?.textContent?.trim() || "",
    captured_at: new Date().toISOString(),
    ...context,
  };
  if (source === "compare_result") feedbackType.value = "diff_quality";
  if (source === "qa_answer") feedbackType.value = "answer_quality";
  if (source === "parameter_row") feedbackType.value = "parameter_quality";
  renderFeedbackContext();
  feedbackDialog.showModal();
}

function renderFeedbackContext() {
  if (!feedbackContext || !feedbackContext.source) {
    feedbackContextNote.textContent = "当前反馈未绑定具体结果。";
    return;
  }
  const labels = {
    general: "通用反馈",
    compare_result: "已绑定当前对比差异",
    qa_answer: "已绑定当前问答答案",
    parameter_row: "已绑定当前参数行",
  };
  const summary = feedbackContext.heading || feedbackContext.question || feedbackContext.source;
  feedbackContextNote.textContent = `${labels[feedbackContext.source] || "已绑定上下文"}：${summary}`;
}

function buildCompareFeedbackContext(item, index) {
  return {
    result_index: index,
    change_type: item?.change_type || "",
    risk: item?.risk || "",
    score: item?.score || 0,
    heading: item?.left?.heading || item?.right?.heading || "",
    page: pageText(item || {}),
    summary: item?.summary || "",
    evidence: item?.evidence || [],
    left_excerpt: (item?.left?.text || "").slice(0, 1200),
    right_excerpt: (item?.right?.text || "").slice(0, 1200),
  };
}

function addFeedbackAction(parent, label, source, context) {
  const action = document.createElement("button");
  action.type = "button";
  action.className = "message-feedback-button";
  action.textContent = label;
  action.addEventListener("click", () => openFeedback(source, context));
  parent.append(action);
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

    const action = document.createElement("button");
    action.type = "button";
    action.className = "inline-feedback-button";
    action.textContent = "反馈这条依据";
    action.addEventListener("click", () => openFeedback("qa_answer", { question: lastQaQuestion, top_results: [item] }));

    card.append(title, meta, heading, text, action);
    qaResults.append(card);
  });
}
