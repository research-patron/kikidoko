(() => {
  const FIRESTORE_PROJECT_ID = "kikidoko";
  const FIRESTORE_API_KEY = "AIzaSyBrVNGOTueD6p5RNvsXiggisbETuTrNKbQ";
  const FEATURE_COLLECTION = "feature_requests";
  const FEATURE_PAGE_SIZE = 50;
  const RATE_LIMIT_MS = 5 * 60 * 1000;

  const PATH_BOOTSTRAP = "/data/bootstrap-v1.json";
  const PATH_SNAPSHOT_LITE = "/data/equipment_snapshot_lite-v1.json";
  const PATH_SNAPSHOT_FULL_GZIP = "/equipment_snapshot.json.gz";
  const PATH_SNAPSHOT_FULL_JSON = "/equipment_snapshot.json";
  const PATH_SIMPLIFIED_GEO = "/data/japan-prefectures-simplified.geojson";
  const PATH_DETAIL_DIR = "/data/equipment_detail_shards";
  const SNAPSHOT_STATE_KEY = "__kikidokoSnapshotState";
  const MAP_DEBUG_KEY = "__kikidokoMapDebug";
  const SNAPSHOT_TIMEOUT_MS = 10000;
  const MAP_FALLBACK_DELAY_MS = 320;
  const MAP_FALLBACK_MONITOR_MS = 2400;

  const REQUEST_LAST_KEY = "kikidoko:feature_request:last";
  const REQUEST_FP_KEY = "kikidoko:feature_request:fingerprint";

  const originalFetch = window.fetch.bind(window);

  let bootstrapDataPromise = null;
  let bootstrapData = null;
  let lookupByNamePrefOrg = null;
  let lookupByNamePref = null;
  let lookupByName = null;
  let snapshotLiteLookupReady = false;
  let snapshotLiteLookupPromise = null;

  const detailByEquipmentId = new Map();
  const detailShardByEquipmentId = new Map();
  const detailBySignature = new Map();
  const shardLoadPromises = new Map();
  let pendingHydrationTimer = null;
  let featureEntries = [];
  let featureLimit = FEATURE_PAGE_SIZE;
  let featureSectionInitialized = false;
  let featureLoadedOnce = false;
  let snapshotWatchdogTimer = null;
  let snapshotCoreInitialized = false;
  let mapFallbackIndexByPrefecture = new Map();
  let mapFallbackIndexReady = false;
  let mapFallbackProbeTimer = null;

  function getMapDebugState() {
    const current = window[MAP_DEBUG_KEY];
    if (current && typeof current === "object") return current;
    const snapshot = window[SNAPSHOT_STATE_KEY];
    const initial = {
      lastShapeClickAt: 0,
      lastPrefecture: "",
      snapshotState: String(snapshot?.status || "loading"),
      fallbackPanelOpen: false,
      lastBlockReason: "",
      fallbackPrefectures: 0,
      updatedAt: new Date().toISOString(),
    };
    window[MAP_DEBUG_KEY] = initial;
    return initial;
  }

  function updateMapDebug(patch) {
    const next = {
      ...getMapDebugState(),
      ...patch,
      updatedAt: new Date().toISOString(),
    };
    window[MAP_DEBUG_KEY] = next;
    return next;
  }

  function getSnapshotState() {
    const current = window[SNAPSHOT_STATE_KEY];
    if (current && typeof current === "object") return current;
    const initial = {
      status: "loading",
      source: "lite",
      startedAt: Date.now(),
      updatedAt: new Date().toISOString(),
      timeoutExceeded: false,
      lastError: "",
    };
    window[SNAPSHOT_STATE_KEY] = initial;
    return initial;
  }

  function updateSnapshotState(patch) {
    const next = {
      ...getSnapshotState(),
      ...patch,
      updatedAt: new Date().toISOString(),
    };
    window[SNAPSHOT_STATE_KEY] = next;
    updateMapDebug({ snapshotState: String(next.status || "loading") });
    window.dispatchEvent(new CustomEvent("kikidoko:snapshot-state", { detail: next }));
    return next;
  }

  function beginSnapshotLoading(source = "lite") {
    return updateSnapshotState({
      status: "loading",
      source,
      startedAt: Date.now(),
      timeoutExceeded: false,
      lastError: "",
    });
  }

  function toNumber(value) {
    const n = Number(value);
    return Number.isFinite(n) ? n : 0;
  }

  function formatCount(value) {
    return toNumber(value).toLocaleString("ja-JP");
  }

  function normalizeDoi(input) {
    return String(input || "")
      .trim()
      .replace(/^https?:\/\/(dx\.)?doi\.org\//i, "")
      .trim();
  }

  function sameOriginPath(url) {
    try {
      const parsed = new URL(url, window.location.origin);
      if (parsed.origin !== window.location.origin) return null;
      return parsed.pathname;
    } catch {
      return null;
    }
  }

  function cloneSearch(url) {
    try {
      return new URL(url, window.location.origin).search || "";
    } catch {
      return "";
    }
  }

  function normalizeLookupPart(value) {
    return String(value || "")
      .normalize("NFKC")
      .replace(/\s+/g, " ")
      .trim()
      .toLowerCase();
  }

  function prefOrgKey(name, prefecture, orgName) {
    return `${normalizeLookupPart(name)}|${normalizeLookupPart(prefecture)}|${normalizeLookupPart(orgName)}`;
  }

  function prefKey(name, prefecture) {
    return `${normalizeLookupPart(name)}|${normalizeLookupPart(prefecture)}`;
  }

  function nameKey(name) {
    return normalizeLookupPart(name);
  }

  function extractPrefectureAndOrg(metaText) {
    const raw = String(metaText || "").trim();
    if (!raw) return { prefecture: "", orgName: "" };
    const parts = raw
      .split("・")
      .map((p) => p.trim())
      .filter(Boolean);
    if (parts.length === 0) return { prefecture: "", orgName: "" };
    if (parts.length === 1) return { prefecture: parts[0], orgName: "" };
    return { prefecture: parts[0], orgName: parts.slice(1).join("・") };
  }

  function resolveEntryId(entry) {
    return String(entry?.equipment_id || entry?.doc_id || entry?.id || "").trim();
  }

  function normalizeShardKey(value) {
    const raw = String(value || "").trim().toLowerCase();
    if (!raw) return "";
    if (/^[a-f0-9]{2}$/.test(raw)) return raw;
    if (raw.startsWith("detail-")) {
      const tail = raw.slice(7);
      if (/^[a-f0-9]{2}$/.test(tail)) return tail;
    }
    const match = raw.match(/detail-([a-f0-9]{2})/);
    return match?.[1] || "";
  }

  function appendLookup(map, key, value) {
    if (!key || !value) return;
    const list = map.get(key);
    if (list) {
      if (!list.includes(value)) list.push(value);
      return;
    }
    map.set(key, [value]);
  }

  function appendLookupFromEntry(entry) {
    const id = resolveEntryId(entry);
    const name = String(entry?.name || "").trim();
    const prefecture = String(entry?.prefecture || "").trim();
    const orgName = String(entry?.org_name || "").trim();
    const shardKey = normalizeShardKey(entry?.detail_shard);
    if (id && shardKey) {
      detailShardByEquipmentId.set(id, shardKey);
    }
    if (!id || !name) return;
    appendLookup(lookupByNamePrefOrg, prefOrgKey(name, prefecture, orgName), id);
    appendLookup(lookupByNamePref, prefKey(name, prefecture), id);
    appendLookup(lookupByName, nameKey(name), id);
  }

  function buildMapFallbackIndex(rows) {
    const staging = new Map();
    rows.forEach((entry) => {
      const prefecture = String(entry?.prefecture || "").trim();
      const orgName = String(entry?.org_name || "").trim();
      if (!prefecture || !orgName) return;
      let pref = staging.get(prefecture);
      if (!pref) {
        pref = { totalEquipment: 0, orgCounts: new Map() };
        staging.set(prefecture, pref);
      }
      pref.totalEquipment += 1;
      pref.orgCounts.set(orgName, Number(pref.orgCounts.get(orgName) || 0) + 1);
    });

    const normalized = new Map();
    staging.forEach((value, prefecture) => {
      const orgList = Array.from(value.orgCounts.entries())
        .map(([orgName, count]) => ({ orgName, count }))
        .sort((a, b) => b.count - a.count || a.orgName.localeCompare(b.orgName, "ja"));
      normalized.set(prefecture, {
        prefecture,
        totalEquipment: Number(value.totalEquipment || 0),
        totalFacilities: orgList.length,
        orgList,
      });
    });
    mapFallbackIndexByPrefecture = normalized;
    mapFallbackIndexReady = normalized.size > 0;
    updateMapDebug({ fallbackPrefectures: normalized.size });
  }

  function seedDetailShardMapFromBootstrap() {
    const shardMap =
      bootstrapData && typeof bootstrapData === "object" && bootstrapData.detail_shard_map
        ? bootstrapData.detail_shard_map
        : {};
    if (!shardMap || typeof shardMap !== "object") return;
    Object.entries(shardMap).forEach(([id, value]) => {
      const key = normalizeShardKey(value);
      if (id && key) {
        detailShardByEquipmentId.set(id, key);
      }
    });
  }

  function ensureEquipmentLookup() {
    if (lookupByNamePrefOrg && lookupByNamePref && lookupByName) {
      seedDetailShardMapFromBootstrap();
      return;
    }
    lookupByNamePrefOrg = new Map();
    lookupByNamePref = new Map();
    lookupByName = new Map();

    const entries = Array.isArray(bootstrapData?.search_head) ? bootstrapData.search_head : [];
    entries.forEach((entry) => {
      appendLookupFromEntry(entry);
    });
    seedDetailShardMapFromBootstrap();
  }

  async function ensureLookupFromSnapshotLite() {
    if (snapshotLiteLookupReady) return;
    if (snapshotLiteLookupPromise) {
      await snapshotLiteLookupPromise;
      return;
    }

    snapshotLiteLookupPromise = originalFetch(PATH_SNAPSHOT_LITE, { cache: "force-cache" })
      .then((res) => {
        if (!res.ok) {
          throw new Error(`snapshot_lite_lookup_fetch_failed:${res.status}`);
        }
        return res.json();
      })
      .then((payload) => {
        ensureEquipmentLookup();
        const rows = Array.isArray(payload?.items) ? payload.items : [];
        rows.forEach((entry) => {
          appendLookupFromEntry(entry);
        });
        buildMapFallbackIndex(rows);
        snapshotLiteLookupReady = true;
      })
      .catch((error) => {
        console.error(error);
      })
      .finally(() => {
        snapshotLiteLookupPromise = null;
      });

    await snapshotLiteLookupPromise;
  }

  function resolveEquipmentIds(name, prefecture, orgName) {
    ensureEquipmentLookup();
    if (!name) return [];

    const keyA = prefOrgKey(name, prefecture, orgName);
    const keyB = prefKey(name, prefecture);
    const keyC = nameKey(name);

    const merged = [];
    const seen = new Set();
    [lookupByNamePrefOrg.get(keyA), lookupByNamePref.get(keyB), lookupByName.get(keyC)].forEach((list) => {
      if (!Array.isArray(list)) return;
      list.forEach((id) => {
        if (!seen.has(id)) {
          seen.add(id);
          merged.push(id);
        }
      });
    });
    return merged;
  }

  function canonicalPaperUrl(rawUrl, doi) {
    const doiNorm = normalizeDoi(doi || "").toLowerCase();
    const url = String(rawUrl || "").trim();
    const lower = url.toLowerCase();

    if (lower.includes("api.elsevier.com/content/article/")) {
      const piiMatch = url.match(/\/pii\/([^/?]+)/i) || url.match(/1-s2\.0-([A-Za-z0-9]+)/i);
      if (piiMatch?.[1]) {
        return `https://www.sciencedirect.com/science/article/pii/${piiMatch[1]}`;
      }
    }

    if (lower.includes("www.scopus.com") && doiNorm) {
      return `https://doi.org/${doiNorm}`;
    }

    if (doiNorm && (lower.includes("doi.org") || !url)) {
      return `https://doi.org/${doiNorm}`;
    }

    if (doiNorm && !url) {
      return `https://doi.org/${doiNorm}`;
    }

    return url;
  }

  function detailSignature(name, prefecture, orgName) {
    return prefOrgKey(name, prefecture, orgName);
  }

  async function loadDetailShard(shardKey) {
    const normalizedShardKey = normalizeShardKey(shardKey);
    if (!normalizedShardKey) return null;
    if (shardLoadPromises.has(normalizedShardKey)) {
      return shardLoadPromises.get(normalizedShardKey);
    }
    const promise = originalFetch(`${PATH_DETAIL_DIR}/detail-${normalizedShardKey}.json`, { cache: "force-cache" })
      .then((res) => {
        if (!res.ok) {
          throw new Error(`detail_shard_fetch_failed:${normalizedShardKey}:${res.status}`);
        }
        return res.json();
      })
      .then((payload) => {
        const rows = Array.isArray(payload?.items) ? payload.items : [];
        rows.forEach((row) => {
          const id = resolveEntryId(row);
          if (id) {
            detailByEquipmentId.set(id, row);
            const shard = normalizeShardKey(row?.detail_shard) || normalizedShardKey;
            if (shard) {
              detailShardByEquipmentId.set(id, shard);
            }
          }
        });
        return rows;
      })
      .catch((error) => {
        shardLoadPromises.delete(normalizedShardKey);
        throw error;
      });
    shardLoadPromises.set(normalizedShardKey, promise);
    return promise;
  }

  async function loadDetailByIds(ids) {
    const shardMap = bootstrapData?.detail_shard_map || {};
    for (const id of ids) {
      if (!id) continue;
      if (detailByEquipmentId.has(id)) {
        return detailByEquipmentId.get(id);
      }
      const shardKey = normalizeShardKey(detailShardByEquipmentId.get(id) || shardMap[id]);
      if (!shardKey) continue;
      try {
        await loadDetailShard(shardKey);
      } catch (error) {
        console.error(error);
      }
      if (detailByEquipmentId.has(id)) {
        return detailByEquipmentId.get(id);
      }
    }
    return null;
  }

  function findActiveSheetContext() {
    const panel = document.querySelector(".equipment-sheet-panel");
    if (!panel) return null;

    const nameEl = panel.querySelector(".equipment-sheet-name");
    const metaEl = panel.querySelector(".equipment-sheet-meta");
    const name = String(nameEl?.textContent || "").trim();
    const meta = String(metaEl?.textContent || "").trim();
    if (!name) return null;
    const parsed = extractPrefectureAndOrg(meta);
    const signature = detailSignature(name, parsed.prefecture, parsed.orgName);
    const ids = resolveEquipmentIds(name, parsed.prefecture, parsed.orgName);

    return {
      panel,
      name,
      prefecture: parsed.prefecture,
      orgName: parsed.orgName,
      signature,
      ids,
    };
  }

  function renderDetailRetry(panel, message) {
    const paperSection = panel.querySelector(".equipment-sheet-papers");
    if (!paperSection) return;

    let box = paperSection.querySelector(".detail-retry-box");
    if (!box) {
      box = document.createElement("div");
      box.className = "detail-retry-box";
      box.innerHTML = `
        <p class="detail-retry-text"></p>
        <button type="button" class="detail-retry-button">詳細を再取得</button>
      `;
      paperSection.appendChild(box);
    }
    const text = box.querySelector(".detail-retry-text");
    if (text) text.textContent = message || "詳細データの取得に失敗しました。";
    const button = box.querySelector(".detail-retry-button");
    if (button && !button.dataset.bound) {
      button.dataset.bound = "1";
      button.addEventListener("click", () => {
        hydrateActiveEquipmentSheet(true).catch((error) => console.error(error));
      });
    }
  }

  function removeDetailRetry(panel) {
    const retry = panel.querySelector(".detail-retry-box");
    if (retry?.parentElement) {
      retry.parentElement.removeChild(retry);
    }
  }

  function ensurePaperPreviewModal() {
    let modal = document.getElementById("paper-preview-modal");
    if (modal) return modal;

    modal = document.createElement("div");
    modal.id = "paper-preview-modal";
    modal.className = "paper-preview-modal";
    modal.hidden = true;
    modal.innerHTML = `
      <button type="button" class="paper-preview-backdrop" aria-label="閉じる"></button>
      <article class="paper-preview-panel" role="dialog" aria-modal="true" aria-label="関連論文要旨">
        <header class="paper-preview-head">
          <h4 class="paper-preview-title"></h4>
          <p class="paper-preview-meta"></p>
        </header>
        <div class="paper-preview-tabs" role="tablist" aria-label="要旨表示">
          <button type="button" class="paper-preview-tab is-active" data-tab="ja" role="tab" aria-selected="true">日本語直訳</button>
          <button type="button" class="paper-preview-tab" data-tab="original" role="tab" aria-selected="false">原文要旨</button>
        </div>
        <div class="paper-preview-body">
          <p class="paper-preview-text" data-panel="ja"></p>
          <p class="paper-preview-text" data-panel="original" hidden></p>
        </div>
        <footer class="paper-preview-actions">
          <button type="button" class="paper-preview-open">論文ページを開く</button>
          <button type="button" class="paper-preview-close">閉じる</button>
        </footer>
      </article>
    `;
    document.body.appendChild(modal);

    const close = () => {
      modal.hidden = true;
      modal.dataset.open = "0";
      modal.dataset.paperUrl = "";
    };
    modal.querySelector(".paper-preview-backdrop")?.addEventListener("click", close);
    modal.querySelector(".paper-preview-close")?.addEventListener("click", close);

    const openButton = modal.querySelector(".paper-preview-open");
    if (openButton) {
      openButton.addEventListener("click", () => {
        const url = String(modal.dataset.paperUrl || "");
        if (!url) return;
        window.open(url, "_blank", "noopener,noreferrer");
      });
    }

    modal.querySelectorAll(".paper-preview-tab").forEach((button) => {
      button.addEventListener("click", () => {
        const targetTab = String(button.getAttribute("data-tab") || "ja");
        modal.querySelectorAll(".paper-preview-tab").forEach((tab) => {
          const active = tab.getAttribute("data-tab") === targetTab;
          tab.classList.toggle("is-active", active);
          tab.setAttribute("aria-selected", active ? "true" : "false");
        });
        modal.querySelectorAll(".paper-preview-text").forEach((panel) => {
          panel.hidden = panel.getAttribute("data-panel") !== targetTab;
        });
      });
    });

    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && modal.dataset.open === "1") {
        close();
      }
    });

    return modal;
  }

  function openPaperPreviewModal(paper) {
    const modal = ensurePaperPreviewModal();
    const title = String(paper?.title || "タイトル不明");
    const doi = String(paper?.doi || "");
    const source = String(paper?.source || "");
    const year = String(paper?.year || "");
    const url = canonicalPaperUrl(paper?.url, doi);

    const titleEl = modal.querySelector(".paper-preview-title");
    if (titleEl) titleEl.textContent = title;

    const metaParts = [];
    if (source) metaParts.push(source);
    if (year) metaParts.push(year);
    if (doi) metaParts.push(`DOI: ${doi}`);
    const metaEl = modal.querySelector(".paper-preview-meta");
    if (metaEl) metaEl.textContent = metaParts.length ? metaParts.join(" / ") : "メタ情報なし";

    const jaText = String(paper?.abstract_ja || "").trim();
    const originalText = String(paper?.abstract || "").trim();
    const jaPanel = modal.querySelector('.paper-preview-text[data-panel="ja"]');
    const originalPanel = modal.querySelector('.paper-preview-text[data-panel="original"]');
    if (jaPanel) {
      jaPanel.textContent = jaText || "日本語直訳要旨が未登録です。";
    }
    if (originalPanel) {
      originalPanel.textContent = originalText || "原文要旨が未登録です。";
    }

    modal.querySelectorAll(".paper-preview-tab").forEach((tab) => {
      const active = tab.getAttribute("data-tab") === "ja";
      tab.classList.toggle("is-active", active);
      tab.setAttribute("aria-selected", active ? "true" : "false");
    });
    modal.querySelectorAll(".paper-preview-text").forEach((panel) => {
      panel.hidden = panel.getAttribute("data-panel") !== "ja";
    });

    const openButton = modal.querySelector(".paper-preview-open");
    if (openButton instanceof HTMLButtonElement) {
      openButton.disabled = !url;
    }
    modal.dataset.paperUrl = url || "";
    modal.dataset.open = "1";
    modal.hidden = false;
  }

  function applyDetailToSheet(panel, detail, signature) {
    if (!panel || !detail) return;

    const content = panel.querySelector(".equipment-sheet-content");
    if (content) {
      const summary = String(detail?.usage_manual_summary || "").trim();
      const bullets = Array.isArray(detail?.usage_manual_bullets) ? detail.usage_manual_bullets : [];

      const summaryEl = content.querySelector("p");
      if (summaryEl && summary) {
        summaryEl.textContent = summary;
      }

      const bulletList = content.querySelector("ul");
      if (bulletList && bullets.length > 0) {
        bulletList.innerHTML = "";
        bullets.slice(0, 5).forEach((bullet) => {
          const li = document.createElement("li");
          li.textContent = String(bullet || "");
          bulletList.appendChild(li);
        });
      }
    }

    const paperSection = panel.querySelector(".equipment-sheet-papers");
    if (paperSection) {
      const oldStatus = paperSection.querySelector(".paper-status");
      const oldList = paperSection.querySelector(".paper-list");
      if (oldStatus) oldStatus.remove();
      if (oldList) oldList.remove();

      const papers = Array.isArray(detail?.papers) ? detail.papers : [];
      if (!papers.length) {
        const empty = document.createElement("p");
        empty.className = "paper-status";
        empty.textContent = "この機器の関連論文詳細は未取得です。";
        paperSection.appendChild(empty);
      } else {
        const list = document.createElement("ul");
        list.className = "paper-list";
        papers.slice(0, 3).forEach((paper) => {
          const title = String(paper?.title || "タイトル不明");
          const doi = String(paper?.doi || "");
          const genre = String(paper?.genre_ja || paper?.genre || "");
          const source = String(paper?.source || "");
          const year = String(paper?.year || "");

          const li = document.createElement("li");
          li.className = "paper-item";
          li.tabIndex = 0;
          li.innerHTML = `
            <p class="paper-title"></p>
            <div class="paper-meta"></div>
          `;
          const titleEl = li.querySelector(".paper-title");
          if (titleEl) titleEl.textContent = title;

          const meta = li.querySelector(".paper-meta");
          if (meta) {
            const chips = [];
            if (genre) chips.push(`<span>${genre}</span>`);
            if (source) chips.push(`<span>${source}</span>`);
            if (year) chips.push(`<span>${year}</span>`);
            if (doi) chips.push(`<span>DOI: ${doi}</span>`);
            meta.innerHTML = chips.join("");
          }

          const openPaperPreview = () => {
            openPaperPreviewModal(paper);
          };
          li.addEventListener("click", openPaperPreview);
          li.addEventListener("keydown", (event) => {
            if (event.key === "Enter" || event.key === " ") {
              event.preventDefault();
              openPaperPreview();
            }
          });

          list.appendChild(li);
        });
        paperSection.appendChild(list);
      }
    }

    detailBySignature.set(signature, detail);
    panel.dataset.detailSignature = signature;
    panel.dataset.detailHydrated = "1";
    removeDetailRetry(panel);
  }

  async function hydrateActiveEquipmentSheet(forceRetry = false) {
    const ctx = findActiveSheetContext();
    if (!ctx) return;

    const { panel, signature } = ctx;
    let ids = ctx.ids;
    if (!forceRetry && panel.dataset.detailSignature === signature && panel.dataset.detailHydrated === "1") {
      return;
    }

    if (detailBySignature.has(signature)) {
      applyDetailToSheet(panel, detailBySignature.get(signature), signature);
      return;
    }

    if (!ids.length) {
      await ensureLookupFromSnapshotLite();
      ids = resolveEquipmentIds(ctx.name, ctx.prefecture, ctx.orgName);
    }

    if (!ids.length) {
      renderDetailRetry(panel, "詳細データIDを解決できませんでした。");
      return;
    }

    const detail = await loadDetailByIds(ids);
    if (!detail) {
      renderDetailRetry(panel, "詳細データの取得に失敗しました。");
      return;
    }

    applyDetailToSheet(panel, detail, signature);
  }

  function scheduleSheetHydration(delayMs = 120) {
    if (pendingHydrationTimer != null) {
      window.clearTimeout(pendingHydrationTimer);
    }
    pendingHydrationTimer = window.setTimeout(() => {
      pendingHydrationTimer = null;
      hydrateActiveEquipmentSheet(false).catch((error) => console.error(error));
    }, Math.max(0, delayMs));
  }

  async function fetchSnapshotWithFailover(requestUrl, init) {
    const search = cloneSearch(requestUrl);
    const pathname = sameOriginPath(requestUrl);
    const fullTargets = [];
    if (pathname === PATH_SNAPSHOT_FULL_GZIP) {
      fullTargets.push(requestUrl, `${PATH_SNAPSHOT_FULL_JSON}${search}`);
    } else if (pathname === PATH_SNAPSHOT_FULL_JSON) {
      fullTargets.push(requestUrl, `${PATH_SNAPSHOT_FULL_GZIP}${search}`);
    } else {
      fullTargets.push(`${PATH_SNAPSHOT_FULL_GZIP}${search}`, `${PATH_SNAPSHOT_FULL_JSON}${search}`);
    }
    beginSnapshotLoading("lite");
    try {
      const liteResponse = await originalFetch(pathname === PATH_SNAPSHOT_LITE ? requestUrl : `${PATH_SNAPSHOT_LITE}${search}`, init);
      if (!liteResponse.ok) {
        throw new Error(`snapshot_lite_fetch_failed:${liteResponse.status}`);
      }
      updateSnapshotState({ status: "ready", source: "lite", timeoutExceeded: false, lastError: "" });
      return liteResponse;
    } catch (liteError) {
      console.warn("snapshot lite fetch failed, fallback to full snapshot", liteError);
      updateSnapshotState({
        status: "fallback",
        source: "full",
        lastError: String(liteError?.message || liteError || "snapshot_lite_failed"),
      });
      let lastFullError = null;
      for (const fullTarget of fullTargets) {
        try {
          const fullResponse = await originalFetch(fullTarget, init);
          if (!fullResponse.ok) {
            throw new Error(`snapshot_full_fetch_failed:${fullResponse.status}`);
          }
          updateSnapshotState({ status: "ready", source: "full", timeoutExceeded: false, lastError: "" });
          return fullResponse;
        } catch (fullError) {
          lastFullError = fullError;
        }
      }
      if (lastFullError) {
        updateSnapshotState({
          status: "error",
          source: "full",
          timeoutExceeded: true,
          lastError: String(lastFullError?.message || lastFullError || "snapshot_full_failed"),
        });
        throw lastFullError;
      }
      const unknownError = new Error("snapshot_full_failed:unknown");
      updateSnapshotState({
        status: "error",
        source: "full",
        timeoutExceeded: true,
        lastError: String(unknownError.message),
      });
      throw unknownError;
    }
  }

  function installFetchInterceptor() {
    if (window.__kikidokoFetchPatched) return;
    window.__kikidokoFetchPatched = true;

    window.fetch = (input, init) => {
      const requestUrl = typeof input === "string" ? input : input?.url || "";
      const pathname = sameOriginPath(requestUrl);

      if (
        pathname === PATH_SNAPSHOT_FULL_GZIP ||
        pathname === PATH_SNAPSHOT_FULL_JSON ||
        pathname === PATH_SNAPSHOT_LITE
      ) {
        return fetchSnapshotWithFailover(requestUrl, init);
      }

      if (pathname === "/japan-prefectures.geojson") {
        const search = cloneSearch(requestUrl);
        return originalFetch(`${PATH_SIMPLIFIED_GEO}${search}`, init);
      }

      return originalFetch(input, init);
    };
  }

  function renderSnapshotStateBanner(container) {
    if (!(container instanceof Element)) return;
    const text = container.querySelector(".snapshot-state-text");
    const retry = container.querySelector(".snapshot-state-retry");
    if (!text || !retry) return;

    const state = getSnapshotState();
    const status = String(state.status || "loading");
    const timeoutExceeded = Boolean(state.timeoutExceeded);

    if (status === "ready") {
      container.hidden = true;
      return;
    }

    container.hidden = false;
    retry.hidden = true;
    retry.disabled = false;
    retry.textContent = "再取得";

    if (status === "fallback") {
      text.textContent = "軽量データの取得に失敗したため、通常データで再取得中です。";
      return;
    }

    if (status === "error") {
      text.textContent = "地図データの取得に失敗しました。再取得してください。";
      retry.hidden = false;
      return;
    }

    if (timeoutExceeded) {
      text.textContent = "データ読込中（都道府県詳細は準備中）: 時間がかかっています。";
      retry.hidden = false;
      return;
    }

    text.textContent = "データ読込中（都道府県詳細は準備中）";
  }

  async function runSnapshotRetry(button) {
    const trigger = button instanceof HTMLElement ? button : null;
    if (trigger) {
      trigger.disabled = true;
      trigger.textContent = "再取得中...";
    }

    beginSnapshotLoading("retry");

    try {
      const probeUrl = `${PATH_SNAPSHOT_FULL_GZIP}?v=${Date.now()}`;
      const response = await originalFetch(probeUrl, { cache: "no-store" });
      if (!response.ok) {
        throw new Error(`snapshot_retry_failed:${response.status}`);
      }
      window.location.reload();
      return;
    } catch (error) {
      console.error(error);
      updateSnapshotState({
        status: "error",
        source: "retry",
        timeoutExceeded: true,
        lastError: String(error?.message || error || "snapshot_retry_failed"),
      });
    } finally {
      if (trigger) {
        trigger.disabled = false;
        trigger.textContent = "再取得";
      }
    }
  }

  function installSnapshotStateUi() {
    const map = document.querySelector(".jp-map-geo");
    if (!map || map.dataset.snapshotStateUiInstalled === "1") return;

    map.dataset.snapshotStateUiInstalled = "1";
    let banner = map.querySelector(".snapshot-state-banner");
    if (!banner) {
      banner = document.createElement("div");
      banner.className = "snapshot-state-banner";
      banner.hidden = true;
      banner.innerHTML = `
        <p class="snapshot-state-text"></p>
        <button type="button" class="snapshot-state-retry">再取得</button>
      `;
      map.appendChild(banner);
    }

    const retry = banner.querySelector(".snapshot-state-retry");
    if (retry && !retry.dataset.bound) {
      retry.dataset.bound = "1";
      retry.addEventListener("click", (event) => {
        event.preventDefault();
        event.stopPropagation();
        runSnapshotRetry(retry).catch((error) => console.error(error));
      });
    }

    const rerender = () => renderSnapshotStateBanner(banner);
    window.addEventListener("kikidoko:snapshot-state", rerender);
    rerender();
  }

  function installSnapshotStateWatchdog() {
    if (snapshotWatchdogTimer != null) return;
    snapshotWatchdogTimer = window.setInterval(() => {
      const state = getSnapshotState();
      if (state.status === "ready" || state.status === "error") return;
      const startedAt = Number(state.startedAt || 0);
      if (!startedAt || state.timeoutExceeded) return;
      if (Date.now() - startedAt >= SNAPSHOT_TIMEOUT_MS) {
        updateSnapshotState({ timeoutExceeded: true });
      }
    }, 500);
  }

  function extractPrefectureFromShapeTarget(target) {
    if (!(target instanceof Element)) return "";
    const shape = target.closest(".jp-map-shape");
    if (!shape) return "";
    const titleText = String(shape.querySelector("title")?.textContent || "").trim();
    if (!titleText) return "";
    const matched = titleText.match(/^(.+?)\s+\d+件/);
    if (matched?.[1]) {
      return matched[1].trim();
    }
    return titleText.split(/\s+/)[0] || "";
  }

  function getNativeMapInfoPanel(map) {
    if (!(map instanceof Element)) return null;
    const panels = map.querySelectorAll(".map-info");
    for (const panel of panels) {
      if (!(panel instanceof HTMLElement)) continue;
      if (panel.classList.contains("map-info-fallback")) continue;
      if (panel.hidden) continue;
      return panel;
    }
    return null;
  }

  function ensureMapFallbackPanel(map) {
    let panel = map.querySelector(".map-info-fallback");
    if (panel instanceof HTMLElement) return panel;

    panel = document.createElement("div");
    panel.className = "map-info map-info-fallback";
    panel.hidden = true;
    panel.innerHTML = `
      <div class="map-info-head">
        <div>
          <h4 class="map-fallback-title"></h4>
          <p class="map-fallback-sub"></p>
        </div>
        <div class="map-info-actions">
          <button type="button" class="ghost map-fallback-close">閉じる</button>
        </div>
      </div>
      <div class="map-info-body">
        <div class="map-info-section">
          <h5>機器保有機関（フォールバック）</h5>
          <p class="map-info-empty map-fallback-empty">読み込み中...</p>
          <ul class="map-info-list map-fallback-list"></ul>
        </div>
      </div>
      <p class="map-info-note">集計対象: snapshot_lite全件（フォールバック）</p>
    `;
    map.appendChild(panel);

    const closeButton = panel.querySelector(".map-fallback-close");
    if (closeButton && !closeButton.dataset.bound) {
      closeButton.dataset.bound = "1";
      closeButton.addEventListener("click", () => {
        panel.hidden = true;
        updateMapDebug({ fallbackPanelOpen: false });
      });
    }

    return panel;
  }

  function hideMapFallbackPanel(map) {
    if (!(map instanceof Element)) return;
    const panel = map.querySelector(".map-info-fallback");
    if (panel instanceof HTMLElement) {
      panel.hidden = true;
    }
    updateMapDebug({ fallbackPanelOpen: false });
  }

  function renderMapFallbackPanel(map, prefecture) {
    const panel = ensureMapFallbackPanel(map);
    const titleEl = panel.querySelector(".map-fallback-title");
    const subEl = panel.querySelector(".map-fallback-sub");
    const emptyEl = panel.querySelector(".map-fallback-empty");
    const listEl = panel.querySelector(".map-fallback-list");
    if (!(titleEl instanceof HTMLElement) || !(subEl instanceof HTMLElement)) return;
    if (!(emptyEl instanceof HTMLElement) || !(listEl instanceof HTMLElement)) return;

    titleEl.textContent = prefecture || "都道府県";
    listEl.innerHTML = "";

    const prefData = mapFallbackIndexByPrefecture.get(prefecture);
    if (!prefecture) {
      subEl.textContent = "都道府県名を特定できませんでした。";
      emptyEl.hidden = false;
      emptyEl.textContent = "地図を再読み込み後に再試行してください。";
      panel.hidden = false;
      updateMapDebug({ fallbackPanelOpen: true, lastBlockReason: "prefecture_parse_failed" });
      return;
    }

    if (!mapFallbackIndexReady) {
      subEl.textContent = "読み込み中";
      emptyEl.hidden = false;
      emptyEl.textContent = "機関一覧を準備中です。";
      panel.hidden = false;
      updateMapDebug({ fallbackPanelOpen: true, lastBlockReason: "snapshot_not_ready" });
      return;
    }

    if (!prefData || !Array.isArray(prefData.orgList) || prefData.orgList.length === 0) {
      subEl.textContent = "0件 / 0拠点";
      emptyEl.hidden = false;
      emptyEl.textContent = "該当なし";
      panel.hidden = false;
      updateMapDebug({ fallbackPanelOpen: true, lastBlockReason: "prefecture_no_data" });
      return;
    }

    subEl.textContent = `${formatCount(prefData.totalEquipment)}件 / ${formatCount(prefData.totalFacilities)}拠点`;
    prefData.orgList.forEach((row) => {
      const li = document.createElement("li");
      li.innerHTML = `
        <button type="button" class="map-org-button" disabled>
          <span class="map-org-name"></span>
          <span class="map-org-count"></span>
        </button>
      `;
      const nameEl = li.querySelector(".map-org-name");
      const countEl = li.querySelector(".map-org-count");
      if (nameEl) nameEl.textContent = String(row.orgName || "");
      if (countEl) countEl.textContent = `${formatCount(row.count)}件`;
      listEl.appendChild(li);
    });
    emptyEl.hidden = true;
    panel.hidden = false;
    updateMapDebug({ fallbackPanelOpen: true, lastBlockReason: "" });
  }

  function scheduleMapInfoFallbackProbe(prefecture) {
    const clickAt = Date.now();
    updateMapDebug({
      lastShapeClickAt: clickAt,
      lastPrefecture: prefecture,
      snapshotState: String(getSnapshotState().status || "loading"),
      lastBlockReason: "",
    });

    if (mapFallbackProbeTimer != null) {
      window.clearInterval(mapFallbackProbeTimer);
      mapFallbackProbeTimer = null;
    }

    window.setTimeout(() => {
      const debug = getMapDebugState();
      if (Number(debug.lastShapeClickAt || 0) !== clickAt) return;
      const map = document.querySelector(".jp-map-geo");
      if (!(map instanceof Element)) return;
      if (getNativeMapInfoPanel(map)) {
        hideMapFallbackPanel(map);
        return;
      }
      ensureLookupFromSnapshotLite()
        .catch((error) => console.error(error))
        .finally(() => {
          const latestMap = document.querySelector(".jp-map-geo");
          if (!(latestMap instanceof Element)) return;
          if (getNativeMapInfoPanel(latestMap)) {
            hideMapFallbackPanel(latestMap);
            return;
          }
          renderMapFallbackPanel(latestMap, prefecture);
        });
    }, MAP_FALLBACK_DELAY_MS);

    const monitorStartedAt = Date.now();
    mapFallbackProbeTimer = window.setInterval(() => {
      const map = document.querySelector(".jp-map-geo");
      if (!(map instanceof Element)) {
        window.clearInterval(mapFallbackProbeTimer);
        mapFallbackProbeTimer = null;
        return;
      }
      if (getNativeMapInfoPanel(map)) {
        hideMapFallbackPanel(map);
        window.clearInterval(mapFallbackProbeTimer);
        mapFallbackProbeTimer = null;
        return;
      }
      if (Date.now() - monitorStartedAt >= MAP_FALLBACK_MONITOR_MS) {
        window.clearInterval(mapFallbackProbeTimer);
        mapFallbackProbeTimer = null;
      }
    }, 120);
  }

  function installSnapshotClickGuard() {
    if (!document.body) {
      document.addEventListener("DOMContentLoaded", installSnapshotClickGuard, { once: true });
      return;
    }
    if (document.body.dataset.snapshotClickGuardBound === "1") return;
    document.body.dataset.snapshotClickGuardBound = "1";

    document.addEventListener(
      "click",
      (event) => {
        const target = event.target;
        if (!(target instanceof Element)) return;
        if (!target.closest(".jp-map-shape") && !target.closest(".jp-map-marker")) return;
        const prefecture = extractPrefectureFromShapeTarget(target);
        scheduleMapInfoFallbackProbe(prefecture);
      },
      true
    );

    document.addEventListener(
      "keydown",
      (event) => {
        if (event.key !== "Enter" && event.key !== " ") return;
        const target = event.target;
        if (!(target instanceof Element)) return;
        if (!target.closest(".jp-map-shape")) return;
        const prefecture = extractPrefectureFromShapeTarget(target);
        scheduleMapInfoFallbackProbe(prefecture);
      },
      true
    );
  }

  function waitForElement(selector, callback, options = {}) {
    const intervalMs = options.intervalMs || 120;
    const maxTries = options.maxTries || 200;
    let tries = 0;

    const timer = setInterval(() => {
      const el = document.querySelector(selector);
      if (el) {
        clearInterval(timer);
        callback(el);
        return;
      }
      tries += 1;
      if (tries >= maxTries) {
        clearInterval(timer);
      }
    }, intervalMs);
  }

  async function loadBootstrapData() {
    if (bootstrapDataPromise) return bootstrapDataPromise;

    bootstrapDataPromise = originalFetch(PATH_BOOTSTRAP, { cache: "force-cache" })
      .then((res) => {
        if (!res.ok) throw new Error(`bootstrap_fetch_failed:${res.status}`);
        return res.json();
      })
      .then((json) => {
        bootstrapData = json;
        return json;
      })
      .catch((error) => {
        console.error(error);
        bootstrapData = null;
        return null;
      });

    return bootstrapDataPromise;
  }

  function ensureCoverageBadge() {
    const searchLeft = document.querySelector(".search-left");
    if (!searchLeft) return;

    let badge = searchLeft.querySelector(".coverage-count-badge");
    if (!badge) {
      badge = document.createElement("span");
      badge.className = "coverage-count-badge";
      searchLeft.appendChild(badge);
    }

    const count = toNumber(bootstrapData?.coverage_count || 0);
    if (count > 0) {
      badge.textContent = `網羅機器数: ${formatCount(count)}件`;
      badge.dataset.ready = "1";
    } else {
      badge.textContent = "網羅機器数: 読み込み中...";
      badge.dataset.ready = "0";
    }
  }

  function installMapDragThreshold() {
    const map = document.querySelector(".jp-map-geo");
    if (!map || map.dataset.dragThresholdInstalled === "1") return;

    map.dataset.dragThresholdInstalled = "1";
    map.style.touchAction = "pan-x pan-y pinch-zoom";

    const threshold = 8;
    let pointerId = null;
    let startX = 0;
    let startY = 0;
    let moved = false;

    map.addEventListener(
      "pointerdown",
      (event) => {
        if (event.pointerType === "mouse" && event.button !== 0) return;
        const target = event.target;
        if (
          target instanceof Element &&
          (target.closest(".map-info") || target.closest(".map-zoom-controls"))
        ) {
          return;
        }
        pointerId = event.pointerId;
        startX = event.clientX;
        startY = event.clientY;
        moved = false;
      },
      { passive: true }
    );

    map.addEventListener(
      "pointermove",
      (event) => {
        if (event.pointerId !== pointerId) return;
        const distance = Math.hypot(event.clientX - startX, event.clientY - startY);
        if (!moved && distance > threshold) {
          moved = true;
        }
      },
      { passive: true }
    );

    const onPointerEnd = (event) => {
      if (event.pointerId !== pointerId) return;
      pointerId = null;
      moved = false;
    };

    map.addEventListener("pointerup", onPointerEnd, { passive: true });
    map.addEventListener("pointercancel", onPointerEnd, { passive: true });
  }

  function getFingerprint() {
    const existing = window.localStorage.getItem(REQUEST_FP_KEY);
    if (existing) return existing;
    const fp = `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 12)}`;
    window.localStorage.setItem(REQUEST_FP_KEY, fp);
    return fp;
  }

  function firestoreBase() {
    return `https://firestore.googleapis.com/v1/projects/${FIRESTORE_PROJECT_ID}/databases/(default)/documents`;
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

  async function fetchFeatureRequests(limit) {
    const endpoint = `${firestoreBase()}:runQuery?key=${encodeURIComponent(FIRESTORE_API_KEY)}`;
    const payload = {
      structuredQuery: {
        from: [{ collectionId: FEATURE_COLLECTION }],
        orderBy: [{ field: { fieldPath: "created_at" }, direction: "DESCENDING" }],
        limit,
      },
    };

    const response = await originalFetch(endpoint, {
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
    const response = await originalFetch(endpoint, {
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

  function renderFeatureComments(entries) {
    const container = document.getElementById("feature-request-comments");
    if (!container) return;

    container.innerHTML = "";
    if (entries.length === 0) {
      container.innerHTML = '<p class="feature-empty">投稿はまだありません。</p>';
      return;
    }

    entries.slice(0, featureLimit).forEach((entry) => {
      const item = document.createElement("article");
      item.className = "feature-comment-item";

      const date = entry.createdAt ? new Date(entry.createdAt) : null;
      const dateText = date && !Number.isNaN(date.getTime()) ? date.toLocaleString("ja-JP") : "日時不明";

      item.innerHTML = `
        <p class="feature-comment-meta">${dateText}</p>
        <p class="feature-comment-text"></p>
      `;
      item.querySelector(".feature-comment-text").textContent = entry.messageRaw;
      container.appendChild(item);
    });
  }

  async function fetchUpdateHistory() {
    const response = await originalFetch(`/update-history.json?v=${Date.now()}`, { cache: "no-store" });
    if (!response.ok) {
      throw new Error(`update_history_fetch_failed:${response.status}`);
    }
    const json = await response.json();
    return Array.isArray(json?.entries) ? json.entries : [];
  }

  function renderUpdateHistory(entries) {
    const container = document.getElementById("feature-update-history");
    if (!container) return;

    container.innerHTML = "";

    if (!entries.length) {
      container.innerHTML = '<p class="feature-empty">更新履歴はまだありません。</p>';
      return;
    }

    entries.slice(0, 12).forEach((entry) => {
      const item = document.createElement("article");
      item.className = "feature-history-item";

      const date = entry?.timestamp ? new Date(entry.timestamp) : null;
      const dateText = date && !Number.isNaN(date.getTime()) ? date.toLocaleString("ja-JP") : "日時不明";
      const summary = String(entry?.summary || entry?.event || "更新");

      item.innerHTML = `
        <p class="feature-history-meta">${dateText}</p>
        <p class="feature-history-text"></p>
      `;
      item.querySelector(".feature-history-text").textContent = summary;
      container.appendChild(item);
    });
  }

  function setFeatureStatus(message, isError) {
    const el = document.getElementById("feature-request-status");
    if (!el) return;
    el.textContent = message || "";
    el.classList.toggle("error", Boolean(isError));
  }

  function updateLoadMoreButton() {
    const wrapper = document.getElementById("feature-request-more-wrap");
    const button = document.getElementById("feature-request-more");
    if (!wrapper || !button) return;

    const canLoadMore = featureEntries.length >= featureLimit;
    wrapper.hidden = !canLoadMore;
    button.disabled = false;
  }

  async function refreshFeatureRequests() {
    const entries = await fetchFeatureRequests(featureLimit);
    featureEntries = entries;
    renderFeatureComments(featureEntries);
    updateLoadMoreButton();
  }

  async function refreshUpdateHistory() {
    try {
      const history = await fetchUpdateHistory();
      renderUpdateHistory(history);
    } catch (_) {
      renderUpdateHistory([]);
    }
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

  function bindFeatureRequestForm() {
    const form = document.getElementById("feature-request-form");
    const messageInput = document.getElementById("feature-request-message");
    const submitButton = document.getElementById("feature-request-submit");
    const moreButton = document.getElementById("feature-request-more");

    if (moreButton && !moreButton.dataset.bound) {
      moreButton.dataset.bound = "1";
      moreButton.addEventListener("click", async () => {
        moreButton.disabled = true;
        featureLimit += FEATURE_PAGE_SIZE;
        try {
          await refreshFeatureRequests();
        } catch (error) {
          console.error(error);
          setFeatureStatus("追加読み込みに失敗しました。", true);
        } finally {
          moreButton.disabled = false;
        }
      });
    }

    if (!form || !messageInput || !submitButton || form.dataset.bound === "1") return;
    form.dataset.bound = "1";

    form.addEventListener("submit", async (event) => {
      event.preventDefault();

      const rawMessage = String(messageInput.value || "").trim();

      if (rawMessage.length < 8 || rawMessage.length > 500) {
        setFeatureStatus("8文字以上500文字以下で入力してください。", true);
        return;
      }

      const lastSubmittedAt = Number(window.localStorage.getItem(REQUEST_LAST_KEY) || 0);
      if (Date.now() - lastSubmittedAt < RATE_LIMIT_MS) {
        setFeatureStatus("投稿は5分に1回までです。時間を空けて再度お試しください。", true);
        return;
      }

      submitButton.disabled = true;
      setFeatureStatus("送信中...", false);

      try {
        const payload = buildFeatureRequestPayload(rawMessage);
        await createFeatureRequest(payload);
        window.localStorage.setItem(REQUEST_LAST_KEY, String(Date.now()));
        messageInput.value = "";
        await refreshFeatureRequests();
        await refreshUpdateHistory();
        setFeatureStatus("要望を受け付けました。ありがとうございます。", false);
      } catch (error) {
        console.error(error);
        setFeatureStatus("送信に失敗しました。時間をおいて再試行してください。", true);
      } finally {
        submitButton.disabled = false;
      }
    });
  }

  function renderFeatureSectionShell() {
    const section = document.getElementById("feature-feedback-section");
    if (!section) return;

    section.innerHTML = `
      <div class="feature-feedback-grid">
        <article class="feature-card">
          <h3>開発要望を投稿</h3>
          <p class="feature-caption">匿名で投稿できます。投稿内容は時系列リストで表示されます。</p>
          <form id="feature-request-form" class="feature-form">
            <textarea id="feature-request-message" maxlength="500" placeholder="要望内容を入力してください（8〜500文字）" required></textarea>
            <div class="feature-form-actions">
              <button id="feature-request-submit" type="submit" class="primary">要望を送信</button>
              <p id="feature-request-status" class="feature-form-status" aria-live="polite"></p>
            </div>
          </form>
        </article>

        <article class="feature-card">
          <h3>要望リスト</h3>
          <p class="feature-caption">新しい投稿順で表示します。</p>
          <div id="feature-request-comments" class="feature-comments" aria-live="polite">
            <p class="feature-empty">表示準備中です...</p>
          </div>
          <div id="feature-request-more-wrap" class="feature-more-wrap" hidden>
            <button id="feature-request-more" type="button" class="ghost">さらに読み込む</button>
          </div>
        </article>

        <article class="feature-card">
          <h3>アップデート情報</h3>
          <p class="feature-caption">データ更新ジョブ完了時に履歴が追加されます。</p>
          <div id="feature-update-history" class="feature-history" aria-live="polite">
            <p class="feature-empty">表示準備中です...</p>
          </div>
        </article>
      </div>
    `;
  }

  async function initFeatureSectionData() {
    if (featureLoadedOnce) return;
    featureLoadedOnce = true;

    bindFeatureRequestForm();
    try {
      await refreshFeatureRequests();
    } catch (error) {
      console.error(error);
      setFeatureStatus("要望一覧の取得に失敗しました。", true);
      const comments = document.getElementById("feature-request-comments");
      if (comments) comments.innerHTML = '<p class="feature-empty">要望一覧を取得できませんでした。</p>';
    }

    await refreshUpdateHistory();
  }

  function scheduleLazyFeatureLoad(section) {
    const startLoad = () => {
      initFeatureSectionData().catch((error) => console.error(error));
    };

    if ("IntersectionObserver" in window) {
      const observer = new IntersectionObserver(
        (entries) => {
          if (entries.some((entry) => entry.isIntersecting)) {
            observer.disconnect();
            startLoad();
          }
        },
        { rootMargin: "240px" }
      );
      observer.observe(section);
    }

    if ("requestIdleCallback" in window) {
      window.requestIdleCallback(startLoad, { timeout: 5000 });
    } else {
      window.setTimeout(startLoad, 3200);
    }
  }

  function ensureFeatureSection() {
    if (featureSectionInitialized) return;

    const page = document.querySelector(".page");
    if (!page) return;

    const footer = page.querySelector(".footer");
    if (!footer) return;

    const section = document.createElement("section");
    section.id = "feature-feedback-section";
    section.className = "feature-feedback";
    page.insertBefore(section, footer);

    renderFeatureSectionShell();
    scheduleLazyFeatureLoad(section);
    featureSectionInitialized = true;
  }

  function bindSheetHydrationTriggers() {
    if (document.body.dataset.sheetHydrationBound === "1") return;
    document.body.dataset.sheetHydrationBound = "1";

    const triggerSelectors = [
      ".result-row",
      ".recommendation-item",
      ".map-org-button",
      ".equipment-sheet-nav-button",
      ".prefecture-row",
      ".paper-item",
      ".equipment-sheet-handle",
    ];

    document.addEventListener(
      "click",
      (event) => {
        const target = event.target;
        if (!(target instanceof Element)) return;
        if (triggerSelectors.some((selector) => target.closest(selector))) {
          scheduleSheetHydration(130);
        }
      },
      true
    );

    document.addEventListener(
      "keydown",
      (event) => {
        const target = event.target;
        if (!(target instanceof Element)) return;
        if (event.key !== "Enter" && event.key !== " ") return;
        if (triggerSelectors.some((selector) => target.closest(selector))) {
          scheduleSheetHydration(130);
        }
      },
      true
    );

    window.setInterval(() => {
      if (!document.querySelector(".equipment-sheet-panel")) return;
      scheduleSheetHydration(0);
    }, 1400);
  }

  function initSnapshotCore() {
    if (snapshotCoreInitialized) return;
    snapshotCoreInitialized = true;
    beginSnapshotLoading("boot");
    installFetchInterceptor();
    installSnapshotStateWatchdog();
    installSnapshotClickGuard();
  }

  initSnapshotCore();

  async function bootstrap() {
    await loadBootstrapData();

    waitForElement(".search-left", () => {
      ensureCoverageBadge();
    });

    waitForElement(".jp-map-geo", () => {
      installMapDragThreshold();
      installSnapshotStateUi();
    });

    waitForElement(".page", () => {
      ensureFeatureSection();
    });

    bindSheetHydrationTriggers();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", bootstrap, { once: true });
  } else {
    bootstrap();
  }
})();
