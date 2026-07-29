const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];

const STATUS_LABELS = {
  draft: "草稿",
  in_review: "待审核",
  approved: "已批准",
  published: "已发布",
  rejected: "已驳回",
  archived: "已归档",
};

let adminToken = sessionStorage.getItem("t7_admin_token") || "";

function setMessage(element, message, success = false) {
  element.textContent = message;
  element.classList.toggle("is-success", success);
}

async function adminApi(path, options = {}) {
  const headers = new Headers(options.headers || {});
  headers.set("X-Admin-Token", adminToken);
  const response = await fetch(path, { ...options, headers });
  let body = {};
  try {
    body = await response.json();
  } catch {
    body = {};
  }
  if (!response.ok) {
    throw new Error(body.message || body.detail || `HTTP ${response.status}`);
  }
  return body;
}

function showWorkspace() {
  $("#adminLogin").hidden = true;
  $("#adminWorkspace").hidden = false;
  loadContent();
}

function showLogin(message = "") {
  $("#adminLogin").hidden = false;
  $("#adminWorkspace").hidden = true;
  setMessage($("#loginMessage"), message);
}

function switchView(view) {
  $$(".admin-tab[data-view]").forEach((tab) =>
    tab.classList.toggle("is-active", tab.dataset.view === view),
  );
  $$("[data-view-pane]").forEach((pane) => {
    pane.hidden = pane.dataset.viewPane !== view;
  });
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function nextActions(item) {
  const map = {
    draft: [["提交审核", "in_review"]],
    in_review: [
      ["批准", "approved"],
      ["驳回", "rejected"],
      ["退回草稿", "draft"],
    ],
    approved: [
      ["发布", "published"],
      ["退回草稿", "draft"],
    ],
    published: [["归档", "archived"]],
    rejected: [["重新编辑", "draft"]],
    archived: [["恢复草稿", "draft"]],
  };
  return map[item.status] || [];
}

function renderContent(items) {
  const list = $("#contentList");
  list.innerHTML = "";
  $("#contentEmpty").hidden = items.length !== 0;
  items.forEach((item) => {
    const article = document.createElement("article");
    article.className = "content-item";
    const actions = nextActions(item)
      .map(
        ([label, status]) =>
          `<button class="secondary-button compact" data-status="${status}" type="button">${label}</button>`,
      )
      .join("");
    article.innerHTML = `
      <div>
        <h3>${escapeHtml(item.topic)}</h3>
        <div class="content-meta">
          <span class="status-tag">${STATUS_LABELS[item.status] || item.status}</span>
          <span>${escapeHtml(item.platform)}</span>
          <span>${escapeHtml(item.target_language)}</span>
          <span>trace ${escapeHtml(item.trace_id.slice(0, 12))}</span>
        </div>
        <p class="content-text">${escapeHtml(item.content)}</p>
      </div>
      <div class="content-actions">
        ${
          item.status !== "published"
            ? '<button class="secondary-button compact" data-edit type="button">编辑正文</button>'
            : ""
        }
        ${actions}
      </div>
    `;
    article.querySelectorAll("[data-status]").forEach((button) =>
      button.addEventListener("click", () =>
        updateContent(item.id, { status: button.dataset.status }),
      ),
    );
    const edit = article.querySelector("[data-edit]");
    if (edit) {
      edit.addEventListener("click", () => {
        const revised = prompt("编辑内容正文", item.content);
        if (revised && revised.trim() && revised !== item.content) {
          updateContent(item.id, { content: revised.trim(), note: "后台人工编辑" });
        }
      });
    }
    list.append(article);
  });
}

async function loadContent() {
  try {
    const status = $("#statusFilter").value;
    const query = status ? `?status=${encodeURIComponent(status)}` : "";
    const body = await adminApi(`/api/admin/content${query}`);
    renderContent(body.items);
  } catch (error) {
    if (String(error.message).includes("令牌")) {
      sessionStorage.removeItem("t7_admin_token");
      adminToken = "";
      showLogin(error.message);
    } else {
      $("#contentEmpty").hidden = false;
      $("#contentEmpty").textContent = error.message;
    }
  }
}

async function updateContent(id, update) {
  try {
    await adminApi(`/api/admin/content/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(update),
    });
    await loadContent();
  } catch (error) {
    alert(error.message);
  }
}

$("#loginForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  adminToken = $("#adminToken").value;
  try {
    await adminApi("/api/admin/content?limit=1");
    sessionStorage.setItem("t7_admin_token", adminToken);
    showWorkspace();
  } catch (error) {
    setMessage($("#loginMessage"), error.message);
  }
});

$$(".admin-tab[data-view]").forEach((tab) =>
  tab.addEventListener("click", () => switchView(tab.dataset.view)),
);
$("#logoutButton").addEventListener("click", () => {
  sessionStorage.removeItem("t7_admin_token");
  adminToken = "";
  showLogin();
});
$("#refreshContent").addEventListener("click", loadContent);
$("#statusFilter").addEventListener("change", loadContent);

$("#generateForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const button = $("#generateButton");
  button.disabled = true;
  setMessage($("#generateMessage"), "");
  try {
    await adminApi("/api/admin/content/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        topic: $("#contentTopic").value.trim(),
        target_language: $("#contentLanguage").value,
        platform: $("#contentPlatform").value,
        max_length: Number($("#contentMaxLength").value),
        audience: {
          region: "global",
          age_band: "adult",
          knowledge_level: "general",
          style: $("#contentStyle").value,
        },
      }),
    });
    setMessage($("#generateMessage"), "已生成并保存为草稿。", true);
    $("#generateForm").reset();
    await loadContent();
    switchView("content");
  } catch (error) {
    setMessage($("#generateMessage"), error.message);
  } finally {
    button.disabled = false;
  }
});

$("#knowledgeForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const button = $("#ingestButton");
  button.disabled = true;
  setMessage($("#knowledgeMessage"), "");
  try {
    const body = await adminApi("/api/admin/knowledge/ingest", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        documents: [
          {
            source_id: $("#sourceId").value.trim(),
            source_uri: $("#sourceUri").value.trim(),
            media_type: $("#mediaType").value,
            title: $("#sourceTitle").value.trim(),
            authorization_status: $("#authorizationStatus").value,
            metadata: {},
          },
        ],
        publish: $("#publishKnowledge").checked,
      }),
    });
    setMessage(
      $("#knowledgeMessage"),
      `已提交：${body.status || "accepted"}，接收 ${body.accepted_count ?? 0} 条。`,
      true,
    );
    $("#knowledgeForm").reset();
  } catch (error) {
    setMessage($("#knowledgeMessage"), error.message);
  } finally {
    button.disabled = false;
  }
});

if (adminToken) showWorkspace();
