const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];

const state = {
  inputType: "text",
  lastResponse: null,
  audio: null,
  sessionId: localStorage.getItem("t7_session_id") || crypto.randomUUID(),
};
localStorage.setItem("t7_session_id", state.sessionId);

function setMessage(element, message, success = false) {
  element.textContent = message;
  element.classList.toggle("is-success", success);
}

function errorMessage(error, fallback = "请求失败，请稍后重试") {
  return error?.body?.message || error?.message || fallback;
}

async function api(path, options = {}) {
  const response = await fetch(path, options);
  let body = {};
  try {
    body = await response.json();
  } catch {
    body = {};
  }
  if (!response.ok) {
    const error = new Error(body.message || body.detail || `HTTP ${response.status}`);
    error.body = body;
    error.status = response.status;
    throw error;
  }
  return body;
}

async function loadConfig() {
  const status = $("#systemStatus");
  try {
    const config = await api("/api/config");
    status.classList.add(config.t0_available ? "is-online" : "is-offline");
    status.textContent = config.t0_available ? "服务已连接" : "T0 暂不可用";
    const languages = config.capabilities?.languages || ["zh-CN", "en"];
    const select = $("#targetLanguage");
    const labels = { "zh-CN": "中文", en: "English", th: "ไทย" };
    select.innerHTML = languages
      .map((code) => `<option value="${code}">${labels[code] || code}</option>`)
      .join("");
    const lang = new URLSearchParams(location.search).get("lang");
    if (lang && languages.includes(lang)) select.value = lang;
  } catch {
    status.classList.add("is-offline");
    status.textContent = "网络不可用";
  }
}

function readQrParameters() {
  const params = new URLSearchParams(location.search);
  const exhibitId = params.get("exhibit_id");
  if (!exhibitId) return;
  $("#exhibitId").value = exhibitId;
  $("#exhibitLabel").textContent = exhibitId;
  $("#exhibitBadge").hidden = false;
}

function activateInput(type) {
  state.inputType = type;
  $$(".input-tab").forEach((tab) => {
    const active = tab.dataset.type === type;
    tab.classList.toggle("is-active", active);
    tab.setAttribute("aria-selected", String(active));
  });
  $$(".input-pane").forEach((pane) => {
    pane.hidden = pane.dataset.pane !== type;
  });
}

async function uploadSelectedFile(input) {
  const file = input.files?.[0];
  if (!file) throw new Error("请先选择文件");
  const form = new FormData();
  form.append("file", file);
  return api("/api/media", { method: "POST", body: form });
}

async function buildUserInput() {
  if (state.inputType === "text") {
    const text = $("#questionText").value.trim();
    if (!text) throw new Error("请输入你的问题");
    return { type: "text", text };
  }
  if (state.inputType === "exhibit_id") {
    const exhibitId = $("#exhibitId").value.trim();
    if (!exhibitId) throw new Error("请输入展品编号");
    return { type: "exhibit_id", exhibit_id: exhibitId };
  }
  const input = state.inputType === "image" ? $("#imageInput") : $("#audioInput");
  const uploaded = await uploadSelectedFile(input);
  return { type: state.inputType, media_url: uploaded.media_url };
}

function renderCitations(citations = []) {
  const container = $("#citationList");
  container.innerHTML = "";
  citations.forEach((citation, index) => {
    const card = document.createElement("article");
    card.className = "citation-card";
    const title = document.createElement("strong");
    title.textContent = `${index + 1}. ${citation.title || "未命名资料"}`;
    const source = document.createElement("small");
    source.textContent = citation.section || citation.source_id || "资料来源";
    const excerpt = document.createElement("p");
    excerpt.textContent = citation.excerpt || "该来源用于支撑本次回答。";
    card.append(title, source, excerpt);
    if (citation.uri) {
      try {
        const url = new URL(citation.uri, location.origin);
        if (["http:", "https:"].includes(url.protocol)) {
          const link = document.createElement("a");
          link.href = url.href;
          link.target = "_blank";
          link.rel = "noopener noreferrer";
          link.textContent = "查看原始资料";
          card.append(link);
        }
      } catch {
        // 无效来源地址不渲染为链接，仍保留引用文字。
      }
    }
    container.append(card);
  });
}

function renderResponse(response) {
  state.lastResponse = response;
  $("#answerText").textContent = response.answer;
  $("#traceChip").textContent = `trace ${response.trace_id}`;
  $("#traceChip").title = response.trace_id;
  renderCitations(response.citations);
  const warnings = $("#warningList");
  warnings.innerHTML = "";
  (response.warnings || []).forEach((warning) => {
    const item = document.createElement("div");
    item.className = "warning-item";
    item.textContent = warning;
    warnings.append(item);
  });
  state.audio = response.audio;
  $("#playButton").textContent = response.audio ? "▶ 播放讲解" : "▶ 浏览器朗读";
  $("#resultSection").hidden = false;
  $("#resultSection").scrollIntoView({ behavior: "smooth", block: "start" });
  const history = JSON.parse(localStorage.getItem("t7_recent_queries") || "[]");
  history.unshift({
    trace_id: response.trace_id,
    answer: response.answer,
    created_at: response.created_at,
  });
  localStorage.setItem("t7_recent_queries", JSON.stringify(history.slice(0, 5)));
}

async function submitGuide(event) {
  event.preventDefault();
  const message = $("#formMessage");
  const button = $("#submitButton");
  setMessage(message, "");
  button.disabled = true;
  button.querySelector("span").textContent = "正在组织讲解…";
  const requestId = crypto.randomUUID();
  try {
    const input = await buildUserInput();
    const body = {
      request_id: requestId,
      session_id: state.sessionId,
      source_language: "auto",
      target_language: $("#targetLanguage").value,
      input,
      audience: {
        region: "global",
        age_band: $("#ageBand").value,
        knowledge_level: $("#knowledgeLevel").value,
        style: $("#storyStyle").value,
      },
      options: {
        top_k: 5,
        return_audio: $("#returnAudio").checked,
        include_graph_context: true,
        debug: false,
      },
    };
    const response = await api("/api/guide/query", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Request-ID": requestId,
        "Idempotency-Key": requestId,
      },
      body: JSON.stringify(body),
    });
    renderResponse(response);
  } catch (error) {
    setMessage(message, errorMessage(error));
  } finally {
    button.disabled = false;
    button.querySelector("span").textContent = "开始智能讲解";
  }
}

function playAnswer() {
  const response = state.lastResponse;
  if (!response) return;
  if (state.audio?.url && !state.audio.url.startsWith("mock://")) {
    const audio = new Audio(state.audio.url);
    audio.play().catch(() => speakWithBrowser(response.answer, response.target_language));
    return;
  }
  speakWithBrowser(response.answer, response.target_language);
}

function speakWithBrowser(text, language) {
  if (!("speechSynthesis" in window)) {
    setMessage($("#formMessage"), "当前浏览器不支持语音朗读");
    return;
  }
  speechSynthesis.cancel();
  const utterance = new SpeechSynthesisUtterance(text);
  utterance.lang = language || "zh-CN";
  speechSynthesis.speak(utterance);
}

async function sendFeedback(rating, correction = null) {
  const response = state.lastResponse;
  if (!response) return;
  const payload = {
    request_id: crypto.randomUUID(),
    trace_id: response.trace_id,
    session_id: state.sessionId,
    rating,
    correction: correction || null,
    tags: [],
  };
  try {
    await api("/api/feedback", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    setMessage($("#feedbackMessage"), "感谢反馈，已提交给项目组。", true);
  } catch (error) {
    queueFeedback(payload);
    setMessage($("#feedbackMessage"), "当前网络不稳定，反馈已在本机排队，联网后会重试。");
  }
}

function queueFeedback(payload) {
  const queue = JSON.parse(localStorage.getItem("t7_feedback_outbox") || "[]");
  queue.push(payload);
  localStorage.setItem("t7_feedback_outbox", JSON.stringify(queue.slice(-20)));
}

async function flushFeedbackQueue() {
  const queue = JSON.parse(localStorage.getItem("t7_feedback_outbox") || "[]");
  if (!queue.length) return;
  const remaining = [];
  for (const payload of queue) {
    try {
      await api("/api/feedback", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
    } catch {
      remaining.push(payload);
    }
  }
  localStorage.setItem("t7_feedback_outbox", JSON.stringify(remaining));
}

$$(".input-tab").forEach((tab) =>
  tab.addEventListener("click", () => activateInput(tab.dataset.type)),
);
$$(".suggestion").forEach((button) =>
  button.addEventListener("click", () => {
    activateInput("text");
    $("#questionText").value = button.textContent.trim();
    $("#questionText").focus();
  }),
);
$("#imageInput").addEventListener("change", (event) => {
  $("#imageFileName").textContent = event.target.files?.[0]?.name || "";
});
$("#audioInput").addEventListener("change", (event) => {
  $("#audioFileName").textContent = event.target.files?.[0]?.name || "";
});
$("#guideForm").addEventListener("submit", submitGuide);
$("#playButton").addEventListener("click", playAnswer);
$("#copyButton").addEventListener("click", async () => {
  if (!state.lastResponse) return;
  await navigator.clipboard.writeText(state.lastResponse.answer);
  $("#copyButton").textContent = "已复制";
  setTimeout(() => ($("#copyButton").textContent = "复制文字"), 1500);
});
$$(".feedback-button").forEach((button) =>
  button.addEventListener("click", () => {
    const rating = button.dataset.rating;
    if (rating === "down") {
      $(".correction-field").hidden = false;
      $("#correctionText").focus();
    } else {
      sendFeedback("up");
    }
  }),
);
$("#sendCorrection").addEventListener("click", () => {
  const correction = $("#correctionText").value.trim();
  if (!correction) {
    setMessage($("#feedbackMessage"), "请先填写需要改进的内容");
    return;
  }
  sendFeedback("down", correction);
});
window.addEventListener("online", flushFeedbackQueue);

readQrParameters();
loadConfig();
flushFeedbackQueue();
if ("serviceWorker" in navigator) navigator.serviceWorker.register("/sw.js");
