(() => {
  const FIRESTORE_PROJECT_ID = "kikidoko";
  const FIRESTORE_API_KEY = "AIzaSyBrVNGOTueD6p5RNvsXiggisbETuTrNKbQ";
  const FEATURE_COLLECTION = "feature_requests";
  const FEATURE_PAGE_SIZE = 50;
  const RATE_LIMIT_MS = 5 * 60 * 1000;
  const REQUEST_LAST_KEY = "kikidoko:update_info:last";
  const REQUEST_FP_KEY = "kikidoko:update_info:fingerprint";
  const RECENT_UPDATE_LIMIT = 5;

  let featureEntries = [];
  let featureLimit = FEATURE_PAGE_SIZE;
  let groupedUpdateHistory = { latestKey: "", ordered: [] };
  let selectedUpdateMonthKey = "";
  let updateModalBound = false;

  function toNumber(value) {
    const n = Number(value);
    return Number.isFinite(n) ? n : 0;
  }

  function parseFirestoreValue(value) {
    if (!value || typeof value !== "object") return null;
    if ("stringValue" in value) return String(value.stringValue || "");
    if ("timestampValue" in value) return String(value.timestampValue || "");
    if ("integerValue" in value) return Number(value.integerValue || 0);
    if ("doubleValue" in value) return Number(value.doubleValue || 0);
    if ("arrayValue" in value) {
      const list = value.arrayValue?.values || [];
      return list.map((entry) => parseFirestoreValue(entry)).filter(Boolean);
    }
    return null;
  }

  function parseFeatureDocument(document) {
    const fields = document?.fields || {};
    const name = String(document?.name || "");
    const id = name.includes("/") ? name.slice(name.lastIndexOf("/") + 1) : "";
    return {
      id,
      messageRaw: String(parseFirestoreValue(fields.message_raw) || ""),
      createdAt: String(parseFirestoreValue(fields.created_at) || ""),
      status: String(parseFirestoreValue(fields.status) || "new"),
      clientFingerprint: String(parseFirestoreValue(fields.client_fingerprint) || ""),
    };
  }

  function firestoreBase() {
    return `https://firestore.googleapis.com/v1/projects/${FIRESTORE_PROJECT_ID}/databases/(default)/documents`;
  }

  async function fetchFeatureRequests(limit) {
    const endpoint = `${firestoreBase()}:runQuery?key=${encodeURIComponent(FIRESTORE_API_KEY)}`;
    const payload = {
      structuredQuery: {
        from: [{ collectionId: FEATURE_COLLECTION }],
        orderBy: [{ field: { fieldPath: "created_at" }, direction: "DESCENDING" }],
        limit: toNumber(limit || FEATURE_PAGE_SIZE),
      },
    };

    const response = await fetch(endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    if (!response.ok) {
      throw new Error(`feature_requests_fetch_failed:${response.status}`);
    }

    const rows = await response.json();
    if (!Array.isArray(rows)) return [];
    return rows
      .map((row) => row?.document)
      .filter(Boolean)
      .map(parseFeatureDocument)
      .filter((entry) => entry.messageRaw);
  }

  async function createFeatureRequest(payload) {
    const endpoint = `${firestoreBase()}/${FEATURE_COLLECTION}?key=${encodeURIComponent(FIRESTORE_API_KEY)}`;
    const response = await fetch(endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!response.ok) {
      const text = await response.text();
      throw new Error(`feature_requests_create_failed:${response.status}:${text}`);
    }
    return response.json();
  }

  function getFingerprint() {
    const current = window.localStorage.getItem(REQUEST_FP_KEY);
    if (current) return current;
    const fp = `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 12)}`;
    window.localStorage.setItem(REQUEST_FP_KEY, fp);
    return fp;
  }

  function buildFeatureRequestPayload(rawMessage) {
    return {
      fields: {
        message_raw: { stringValue: rawMessage },
        created_at: { timestampValue: new Date().toISOString() },
        client_fingerprint: { stringValue: getFingerprint() },
        status: { stringValue: "new" },
      },
    };
  }

  function setStatus(message, isError) {
    const el = document.getElementById("feature-request-status");
    if (!el) return;
    el.textContent = message || "";
    el.classList.toggle("error", Boolean(isError));
  }

  function formatDate(value) {
    if (!value) return "日時不明";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return "日時不明";
    return date.toLocaleString("ja-JP");
  }

  function renderFeatureRequests(entries) {
    const container = document.getElementById("feature-request-list");
    if (!container) return;
    container.innerHTML = "";

    if (!entries.length) {
      container.innerHTML = '<p class="empty">投稿はまだありません。</p>';
      return;
    }

    entries.slice(0, featureLimit).forEach((entry) => {
      const article = document.createElement("article");
      article.className = "request-item";
      article.innerHTML = `
        <p class="item-meta">${formatDate(entry.createdAt)}</p>
        <p class="item-text"></p>
      `;
      const text = article.querySelector(".item-text");
      if (text) text.textContent = entry.messageRaw;
      container.appendChild(article);
    });
  }

  function updateLoadMoreButton() {
    const wrap = document.getElementById("feature-request-more-wrap");
    const button = document.getElementById("feature-request-more");
    if (!wrap || !button) return;
    const canLoadMore = featureEntries.length >= featureLimit;
    wrap.hidden = !canLoadMore;
    button.disabled = false;
  }

  async function refreshFeatureRequests() {
    featureEntries = await fetchFeatureRequests(featureLimit);
    renderFeatureRequests(featureEntries);
    updateLoadMoreButton();
  }

  async function fetchUpdateHistory() {
    const response = await fetch(`/update-history.json?v=${Date.now()}`, { cache: "no-store" });
    if (!response.ok) {
      throw new Error(`update_history_fetch_failed:${response.status}`);
    }
    const json = await response.json();
    return Array.isArray(json?.entries) ? json.entries : [];
  }

  function monthKeyFromEntry(entry) {
    const date = new Date(String(entry?.timestamp || ""));
    if (Number.isNaN(date.getTime())) return "unknown";
    const month = String(date.getMonth() + 1).padStart(2, "0");
    return `${date.getFullYear()}-${month}`;
  }

  function monthLabel(key) {
    if (key === "unknown") return "日時不明";
    const [year, month] = key.split("-");
    if (!year || !month) return key;
    return `${year}年${Number(month)}月`;
  }

  function sortUpdateEntries(entries) {
    return [...entries].sort((a, b) => {
      const ta = new Date(String(a?.timestamp || "")).getTime() || 0;
      const tb = new Date(String(b?.timestamp || "")).getTime() || 0;
      return tb - ta;
    });
  }

  function groupUpdateHistory(entries) {
    const sorted = sortUpdateEntries(entries);
    const groups = new Map();

    sorted.forEach((entry) => {
      const key = monthKeyFromEntry(entry);
      const list = groups.get(key);
      if (list) {
        list.push(entry);
      } else {
        groups.set(key, [entry]);
      }
    });

    const orderedKeys = Array.from(groups.keys()).sort((a, b) => {
      if (a === "unknown") return 1;
      if (b === "unknown") return -1;
      return b.localeCompare(a);
    });

    return {
      latestKey: orderedKeys[0] || "",
      ordered: orderedKeys.map((key) => ({
        key,
        label: monthLabel(key),
        entries: groups.get(key) || [],
      })),
    };
  }

  function renderUpdateListItems(parent, entries) {
    entries.forEach((entry) => {
      const article = document.createElement("article");
      article.className = "update-item";
      const summary = String(entry?.summary || entry?.event || "更新");
      article.innerHTML = `
        <p class="item-meta">${formatDate(entry?.timestamp)}</p>
        <p class="item-text"></p>
      `;
      const text = article.querySelector(".item-text");
      if (text) text.textContent = summary;
      parent.appendChild(article);
    });
  }

  function renderRecentUpdates(entries) {
    const container = document.getElementById("update-history-recent");
    const moreWrap = document.getElementById("update-history-more-wrap");
    if (!container || !moreWrap) return;

    container.innerHTML = "";

    if (!entries.length) {
      container.innerHTML = '<p class="empty">更新履歴はまだありません。</p>';
      moreWrap.hidden = true;
      return;
    }

    const recentEntries = entries.slice(0, RECENT_UPDATE_LIMIT);
    renderUpdateListItems(container, recentEntries);
    moreWrap.hidden = entries.length <= RECENT_UPDATE_LIMIT;
  }

  function getSelectedMonthGroup() {
    return groupedUpdateHistory.ordered.find((group) => group.key === selectedUpdateMonthKey) || null;
  }

  function renderMonthPicker(groups) {
    const picker = document.getElementById("update-history-month-picker");
    if (!picker) return;

    picker.innerHTML = "";

    if (!groups.length) {
      picker.innerHTML = '<p class="empty">月別データがありません。</p>';
      return;
    }

    groups.forEach((group) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = `update-month-button${group.key === selectedUpdateMonthKey ? " is-active" : ""}`;
      button.textContent = `${group.label} (${group.entries.length}件)`;
      button.dataset.monthKey = group.key;
      button.setAttribute("aria-pressed", group.key === selectedUpdateMonthKey ? "true" : "false");
      button.addEventListener("click", () => {
        selectedUpdateMonthKey = group.key;
        renderMonthPicker(groupedUpdateHistory.ordered);
        renderSelectedMonthEntries(getSelectedMonthGroup());
      });
      picker.appendChild(button);
    });
  }

  function renderSelectedMonthEntries(group) {
    const container = document.getElementById("update-history-month-entries");
    if (!container) return;

    container.innerHTML = "";

    if (!group) {
      container.innerHTML = '<p class="empty">表示する更新履歴がありません。</p>';
      return;
    }

    const heading = document.createElement("h4");
    heading.className = "update-month-title";
    heading.textContent = `${group.label} の更新履歴`;
    container.appendChild(heading);

    renderUpdateListItems(container, group.entries);
  }

  function isModalOpen() {
    const modal = document.getElementById("update-history-modal");
    return Boolean(modal && !modal.hidden);
  }

  function openUpdateHistoryModal() {
    const modal = document.getElementById("update-history-modal");
    if (!modal || groupedUpdateHistory.ordered.length === 0) return;

    if (!selectedUpdateMonthKey) {
      selectedUpdateMonthKey = groupedUpdateHistory.latestKey || groupedUpdateHistory.ordered[0]?.key || "";
    }

    renderMonthPicker(groupedUpdateHistory.ordered);
    renderSelectedMonthEntries(getSelectedMonthGroup());

    modal.hidden = false;
    modal.setAttribute("aria-hidden", "false");
    document.body.classList.add("modal-open");
  }

  function closeUpdateHistoryModal() {
    const modal = document.getElementById("update-history-modal");
    if (!modal) return;
    modal.hidden = true;
    modal.setAttribute("aria-hidden", "true");
    document.body.classList.remove("modal-open");
  }

  function bindUpdateHistoryModalControls() {
    if (updateModalBound) return;

    const openButton = document.getElementById("update-history-more");
    const closeButton = document.getElementById("update-history-modal-close");
    const backdrop = document.getElementById("update-history-modal-backdrop");
    const modal = document.getElementById("update-history-modal");

    if (!openButton || !closeButton || !backdrop || !modal) return;

    openButton.addEventListener("click", () => {
      openUpdateHistoryModal();
    });

    closeButton.addEventListener("click", () => {
      closeUpdateHistoryModal();
    });

    backdrop.addEventListener("click", () => {
      closeUpdateHistoryModal();
    });

    document.addEventListener("keydown", (event) => {
      if (event.key !== "Escape") return;
      if (isModalOpen()) {
        closeUpdateHistoryModal();
      }
    });

    updateModalBound = true;
  }

  function renderUpdateHistoryError() {
    const recentContainer = document.getElementById("update-history-recent");
    const moreWrap = document.getElementById("update-history-more-wrap");
    const picker = document.getElementById("update-history-month-picker");
    const entriesContainer = document.getElementById("update-history-month-entries");

    if (recentContainer) {
      recentContainer.innerHTML = '<p class="empty">更新履歴の取得に失敗しました。</p>';
    }
    if (moreWrap) {
      moreWrap.hidden = true;
    }
    if (picker) {
      picker.innerHTML = '<p class="empty">更新履歴の取得に失敗しました。</p>';
    }
    if (entriesContainer) {
      entriesContainer.innerHTML = '<p class="empty">更新履歴の取得に失敗しました。</p>';
    }
    closeUpdateHistoryModal();
  }

  async function refreshUpdateHistory() {
    try {
      const entries = await fetchUpdateHistory();
      const sortedEntries = sortUpdateEntries(entries);
      groupedUpdateHistory = groupUpdateHistory(sortedEntries);

      if (!selectedUpdateMonthKey) {
        selectedUpdateMonthKey = groupedUpdateHistory.latestKey;
      }

      const monthExists = groupedUpdateHistory.ordered.some((group) => group.key === selectedUpdateMonthKey);
      if (!monthExists) {
        selectedUpdateMonthKey = groupedUpdateHistory.latestKey;
      }

      renderRecentUpdates(sortedEntries);

      if (isModalOpen()) {
        renderMonthPicker(groupedUpdateHistory.ordered);
        renderSelectedMonthEntries(getSelectedMonthGroup());
      }
    } catch (error) {
      console.error(error);
      groupedUpdateHistory = { latestKey: "", ordered: [] };
      selectedUpdateMonthKey = "";
      renderUpdateHistoryError();
    }
  }

  function bindFeatureRequestForm() {
    const form = document.getElementById("feature-request-form");
    const messageInput = document.getElementById("feature-request-message");
    const submitButton = document.getElementById("feature-request-submit");
    const moreButton = document.getElementById("feature-request-more");
    if (!form || !messageInput || !submitButton || !moreButton) return;

    moreButton.addEventListener("click", async () => {
      moreButton.disabled = true;
      featureLimit += FEATURE_PAGE_SIZE;
      try {
        await refreshFeatureRequests();
      } catch (error) {
        console.error(error);
        setStatus("要望一覧の追加読み込みに失敗しました。", true);
      } finally {
        moreButton.disabled = false;
      }
    });

    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const rawMessage = String(messageInput.value || "").trim();
      if (rawMessage.length < 8 || rawMessage.length > 500) {
        setStatus("8文字以上500文字以下で入力してください。", true);
        return;
      }

      const lastSubmittedAt = Number(window.localStorage.getItem(REQUEST_LAST_KEY) || 0);
      if (Date.now() - lastSubmittedAt < RATE_LIMIT_MS) {
        setStatus("投稿は5分に1回までです。時間を空けて再度お試しください。", true);
        return;
      }

      submitButton.disabled = true;
      setStatus("送信中...", false);
      try {
        await createFeatureRequest(buildFeatureRequestPayload(rawMessage));
        window.localStorage.setItem(REQUEST_LAST_KEY, String(Date.now()));
        messageInput.value = "";
        await refreshFeatureRequests();
        setStatus("要望を受け付けました。ありがとうございます。", false);
      } catch (error) {
        console.error(error);
        setStatus("送信に失敗しました。時間をおいて再試行してください。", true);
      } finally {
        submitButton.disabled = false;
      }
    });
  }

  async function initPage() {
    bindFeatureRequestForm();
    bindUpdateHistoryModalControls();
    try {
      await refreshFeatureRequests();
    } catch (error) {
      console.error(error);
      setStatus("要望一覧の取得に失敗しました。", true);
      const container = document.getElementById("feature-request-list");
      if (container) container.innerHTML = '<p class="empty">要望一覧を取得できませんでした。</p>';
    }
    await refreshUpdateHistory();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => {
      initPage().catch((error) => console.error(error));
    });
  } else {
    initPage().catch((error) => console.error(error));
  }
})();
