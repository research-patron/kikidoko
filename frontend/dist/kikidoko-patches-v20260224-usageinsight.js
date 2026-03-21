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
  const MANUAL_ROUTE_PREFIX = "#/";
  const CONTENT_SOURCE_APPROVED = "manual_approved";
  const CONTENT_SOURCE_UNAPPROVED = "manual_unapproved";
  const CONTENT_SOURCE_FALLBACK = "fallback_generated";
  const MIN_BEGINNER_NON_WS_CHARS = 2000;
  const MAX_BEGINNER_NON_WS_CHARS = 3000;
  const INTERNAL_ID_PATTERN = /\b(?:doc_id|equipment_id|eqnet-\d+)\b/i;
  const AUTO_TEMPLATE_MARKERS = [
    "同カテゴリの近縁機器",
    "補助キーワード",
    "比較観点1では",
    "補助タグは",
    "確認語は",
    "警告語",
    "記録補助語",
    "運用上の補助タグとして",
    "補助見出しにして記録",
  ];

  function currentAssetVersionQuery() {
    try {
      const src = typeof import.meta !== "undefined" && import.meta?.url ? String(import.meta.url) : "";
      if (!src) return "";
      const parsed = new URL(src, window.location.href);
      return parsed.search || "";
    } catch (_error) {
      return "";
    }
  }

  const ASSET_VERSION_QUERY = currentAssetVersionQuery();

  function appendAssetVersion(path) {
    const raw = String(path || "").trim();
    if (!raw || !ASSET_VERSION_QUERY) return raw;
    const glue = raw.includes("?") ? "&" : "?";
    return `${raw}${glue}${ASSET_VERSION_QUERY.replace(/^\?/, "")}`;
  }

  const FALLBACK_PAPER_MAP = [
    { pattern: /フロー|細胞|免疫|FACS/i, doi: "10.1038/nri.2017.113", title: "Flow cytometry and the future of immunology" },
    { pattern: /NMR|核磁気/i, doi: "10.1016/j.pnmrs.2016.05.001", title: "NMR spectroscopy in chemistry and materials science" },
    { pattern: /X線|回折|XRD|XRF/i, doi: "10.1107/S2052520614026152", title: "Powder diffraction in materials characterization" },
    { pattern: /質量|MS|LCMS|GCMS/i, doi: "10.1038/nmeth.3253", title: "Mass spectrometry for proteomics and metabolomics" },
    { pattern: /顕微|SEM|TEM|FIB/i, doi: "10.1038/nmeth.2080", title: "Fluorescence microscopy: from principles to biological applications" },
    { pattern: /クロマト|HPLC|GC/i, doi: "10.1038/nprot.2016.009", title: "Gas chromatography-mass spectrometry based metabolomics" },
    { pattern: /培養|インキュベーター|細胞培養/i, doi: "10.1038/s41596-020-00436-6", title: "Mammalian cell culture practical guidelines" },
    { pattern: /遠心/i, doi: "10.1016/j.ab.2014.08.008", title: "Centrifugation techniques in biological sample preparation" },
  ];
  const FALLBACK_PAPER_DEFAULT = {
    doi: "10.1038/nmeth.2080",
    title: "Fluorescence microscopy: from principles to biological applications",
  };

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
  let lastNonRouteHash = "";
  let routeRenderToken = 0;

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

  function escapeHtml(value) {
    return String(value || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/\"/g, "&quot;")
      .replace(/'/g, "&#39;");
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
    return String(entry?.doc_id || entry?.equipment_id || entry?.id || "").trim();
  }

  function resolveEquipmentId(entry) {
    return String(entry?.equipment_id || "").trim();
  }

  function resolveEntryIds(entry) {
    const ids = [];
    const seen = new Set();
    [resolveEntryId(entry), resolveEquipmentId(entry), String(entry?.id || "").trim()].forEach((id) => {
      const value = String(id || "").trim();
      if (!value || seen.has(value)) return;
      seen.add(value);
      ids.push(value);
    });
    return ids;
  }

  function countNonWhitespace(value) {
    return String(value || "").replace(/\s+/g, "").length;
  }

  function beginnerGuideLength(detail) {
    const beginner = detail && typeof detail === "object" ? detail.manual_content_v1?.beginner_guide : null;
    if (!beginner || typeof beginner !== "object") return 0;
    const steps = Array.isArray(beginner.basic_steps_ja) ? beginner.basic_steps_ja : [];
    const pitfalls = Array.isArray(beginner.common_pitfalls_ja) ? beginner.common_pitfalls_ja : [];
    const text =
      String(beginner.principle_ja || "") +
      String(beginner.sample_guidance_ja || "") +
      steps.map((v) => String(v || "")).join("") +
      pitfalls.map((v) => String(v || "")).join("");
    return countNonWhitespace(text);
  }

  function detailScore(detail) {
    if (!detail || typeof detail !== "object") return -1;
    const papersCount = Array.isArray(detail.papers) ? detail.papers.length : 0;
    const paperExplanations = Array.isArray(detail.manual_content_v1?.paper_explanations)
      ? detail.manual_content_v1.paper_explanations.length
      : 0;
    const approved = detail.manual_content_v1?.review?.status === "approved" ? 1 : 0;
    const beginnerLen = beginnerGuideLength(detail);
    return approved * 1_000_000 + papersCount * 10_000 + paperExplanations * 1_000 + beginnerLen;
  }

  function pickPreferredDetail(current, candidate) {
    if (!current) return candidate;
    if (!candidate) return current;
    return detailScore(candidate) >= detailScore(current) ? candidate : current;
  }

  function registerDetailShardId(id, shardKey) {
    const key = String(id || "").trim();
    const shard = normalizeShardKey(shardKey);
    if (!key || !shard) return;
    detailShardByEquipmentId.set(key, shard);
  }

  function registerDetailRow(row, shardKey) {
    const shard = normalizeShardKey(row?.detail_shard) || normalizeShardKey(shardKey);
    const docId = String(row?.doc_id || "").trim();
    const equipmentId = String(row?.equipment_id || "").trim();
    const ids = resolveEntryIds(row);
    ids.forEach((id) => {
      const current = detailByEquipmentId.get(id);
      detailByEquipmentId.set(id, pickPreferredDetail(current, row));
      registerDetailShardId(id, shard);
    });
    if (docId && equipmentId) {
      const currentByEquipment = detailByEquipmentId.get(equipmentId);
      detailByEquipmentId.set(equipmentId, pickPreferredDetail(currentByEquipment, row));
      registerDetailShardId(equipmentId, shard);
    }
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
    const equipmentId = resolveEquipmentId(entry);
    const name = String(entry?.name || "").trim();
    const prefecture = String(entry?.prefecture || "").trim();
    const orgName = String(entry?.org_name || "").trim();
    const shardKey = normalizeShardKey(entry?.detail_shard);
    registerDetailShardId(id, shardKey);
    registerDetailShardId(equipmentId, shardKey);
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

    snapshotLiteLookupPromise = originalFetch(appendAssetVersion(PATH_SNAPSHOT_LITE), { cache: "no-store" })
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

  function detailVersionQueryString() {
    const version = String(bootstrapData?.version || bootstrapData?.generated_at || "").trim();
    if (!version) return "";
    return `?v=${encodeURIComponent(version)}`;
  }

  function detailShardRequestUrl(normalizedShardKey) {
    return `${PATH_DETAIL_DIR}/detail-${normalizedShardKey}.json${detailVersionQueryString()}`;
  }

  async function loadDetailShard(shardKey) {
    const normalizedShardKey = normalizeShardKey(shardKey);
    if (!normalizedShardKey) return null;
    if (shardLoadPromises.has(normalizedShardKey)) {
      return shardLoadPromises.get(normalizedShardKey);
    }
    const requestUrl = detailShardRequestUrl(normalizedShardKey);
    const promise = originalFetch(requestUrl, { cache: "no-store" })
      .then((res) => {
        if (!res.ok) {
          throw new Error(`detail_shard_fetch_failed:${normalizedShardKey}:${res.status}`);
        }
        return res.json();
      })
      .then((payload) => {
        const rows = Array.isArray(payload?.items) ? payload.items : [];
        rows.forEach((row) => {
          registerDetailRow(row, normalizedShardKey);
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
    const candidates = [];
    const pushCandidate = (detail) => {
      if (!detail || typeof detail !== "object") return;
      candidates.push(detail);
    };
    for (const id of ids) {
      if (!id) continue;
      if (detailByEquipmentId.has(id)) {
        pushCandidate(detailByEquipmentId.get(id));
      }
      const shardKey = normalizeShardKey(detailShardByEquipmentId.get(id) || shardMap[id]);
      if (!shardKey) continue;
      try {
        await loadDetailShard(shardKey);
      } catch (error) {
        console.error(error);
      }
      if (detailByEquipmentId.has(id)) {
        pushCandidate(detailByEquipmentId.get(id));
      }
    }
    return pickBestDetailCandidate(candidates);
  }

  function normalizeHashValue(hashValue) {
    const raw = String(hashValue || "").trim();
    if (!raw) return "";
    if (raw.startsWith("#")) return raw;
    return raw.startsWith("/") ? `#${raw}` : `#/${raw}`;
  }

  function parseHashRoute(hashValue = window.location.hash) {
    const hash = normalizeHashValue(hashValue);
    if (!hash.startsWith(MANUAL_ROUTE_PREFIX)) return null;
    const body = hash.slice(2);
    if (!body) return null;
    const segments = body.split("/").filter(Boolean);
    if (!segments.length) return null;

    if (segments[0] === "paper" && segments.length >= 3) {
      return {
        type: "paper",
        docId: decodeURIComponent(segments[1] || ""),
        doi: decodeURIComponent(segments.slice(2).join("/") || ""),
      };
    }

    if (segments[0] === "beginner" && segments.length >= 2) {
      return {
        type: "beginner",
        docId: decodeURIComponent(segments[1] || ""),
      };
    }

    return null;
  }

  function isManualRouteHash(hashValue = window.location.hash) {
    return Boolean(parseHashRoute(hashValue));
  }

  function pushRoute(hashValue) {
    const nextHash = normalizeHashValue(hashValue);
    if (!nextHash) return;
    const currentHash = normalizeHashValue(window.location.hash);
    if (!isManualRouteHash(currentHash)) {
      lastNonRouteHash = currentHash;
    }
    if (currentHash === nextHash) {
      handleRouteChange().catch((error) => console.error(error));
      return;
    }
    window.location.hash = nextHash;
  }

  function replaceRoute(hashValue) {
    const nextHash = normalizeHashValue(hashValue);
    const base = `${window.location.pathname}${window.location.search}`;
    const nextUrl = nextHash ? `${base}${nextHash}` : base;
    window.history.replaceState(null, "", nextUrl);
    handleRouteChange().catch((error) => console.error(error));
  }

  function closeManualRoute() {
    if (!isManualRouteHash()) {
      hideManualRouteOverlay();
      return;
    }
    const targetHash = lastNonRouteHash || "";
    if (window.history.length > 1) {
      window.history.back();
      window.setTimeout(() => {
        if (isManualRouteHash()) {
          replaceRoute(targetHash);
        }
      }, 120);
      return;
    }
    replaceRoute(targetHash);
  }

  function ensureManualRouteOverlay() {
    let overlay = document.getElementById("manual-route-overlay");
    if (overlay) return overlay;
    overlay = document.createElement("div");
    overlay.id = "manual-route-overlay";
    overlay.className = "manual-route-overlay";
    overlay.hidden = true;
    document.body.appendChild(overlay);
    return overlay;
  }

  function hideManualRouteOverlay() {
    const overlay = document.getElementById("manual-route-overlay");
    if (!(overlay instanceof HTMLElement)) return;
    overlay.hidden = true;
    overlay.innerHTML = "";
    document.body.classList.remove("manual-route-open");
  }

  function detailReviewedAtMs(detail) {
    const raw = String(detail?.manual_content_v1?.review?.reviewed_at || "").trim();
    if (!raw) return 0;
    const parsed = Date.parse(raw);
    return Number.isFinite(parsed) ? parsed : 0;
  }

  function detailCandidateMetrics(detail) {
    const display = resolveDisplayContent(detail);
    const reviewStatus = String(detail?.manual_content_v1?.review?.status || "").trim().toLowerCase();
    const approved = reviewStatus === "approved";
    const beginnerReady = Boolean(display?.beginnerReady);
    const paperExplanations = Array.isArray(detail?.manual_content_v1?.paper_explanations)
      ? detail.manual_content_v1.paper_explanations.length
      : 0;
    const beginnerLen = Number(display?.beginnerNonWsChars || 0);
    const reviewedAtMs = detailReviewedAtMs(detail);
    const stableId = String(detail?.doc_id || detail?.equipment_id || detail?.id || "").trim();
    return {
      approved,
      beginnerReady,
      paperExplanations,
      beginnerLen,
      reviewedAtMs,
      stableId,
    };
  }

  function compareDetailCandidates(a, b) {
    const ma = detailCandidateMetrics(a);
    const mb = detailCandidateMetrics(b);
    if (ma.approved !== mb.approved) return ma.approved ? -1 : 1;
    if (ma.beginnerReady !== mb.beginnerReady) return ma.beginnerReady ? -1 : 1;
    if (ma.paperExplanations !== mb.paperExplanations) return mb.paperExplanations - ma.paperExplanations;
    if (ma.beginnerLen !== mb.beginnerLen) return mb.beginnerLen - ma.beginnerLen;
    if (ma.reviewedAtMs !== mb.reviewedAtMs) return mb.reviewedAtMs - ma.reviewedAtMs;
    return ma.stableId.localeCompare(mb.stableId, "ja");
  }

  function pickBestDetailCandidate(candidates) {
    const list = Array.isArray(candidates) ? candidates : [];
    if (!list.length) return null;
    const unique = [];
    const seen = new Set();
    list.forEach((detail) => {
      if (!detail || typeof detail !== "object") return;
      const key = [
        String(detail?.doc_id || "").trim(),
        String(detail?.equipment_id || "").trim(),
        String(detail?.manual_content_v1?.review?.status || "").trim(),
        String(detail?.manual_content_v1?.review?.reviewed_at || "").trim(),
      ].join("|");
      if (seen.has(key)) return;
      seen.add(key);
      unique.push(detail);
    });
    unique.sort(compareDetailCandidates);
    return unique[0] || null;
  }

  async function resolvePreferredDuplicateDetail(baseDetail) {
    if (!baseDetail || typeof baseDetail !== "object") return baseDetail;
    const baseStatus = String(baseDetail?.manual_content_v1?.review?.status || "").trim().toLowerCase();
    if (baseStatus === "approved") return baseDetail;

    await ensureLookupFromSnapshotLite();
    const name = String(baseDetail?.name || "").trim();
    if (!name) return baseDetail;
    const prefecture = String(baseDetail?.prefecture || "").trim();
    const orgName = String(baseDetail?.org_name || "").trim();
    const resolvedIds = resolveEquipmentIds(name, prefecture, orgName);
    const mergedIds = [...resolvedIds];
    resolveEntryIds(baseDetail).forEach((id) => {
      if (!mergedIds.includes(id)) mergedIds.push(id);
    });
    if (!mergedIds.length) return baseDetail;
    const best = await loadDetailByIds(mergedIds);
    return best || baseDetail;
  }

  async function loadDetailByDocId(docId) {
    const id = String(docId || "").trim();
    if (!id) return null;

    if (detailByEquipmentId.has(id)) {
      const direct = detailByEquipmentId.get(id);
      return resolvePreferredDuplicateDetail(direct);
    }

    await loadBootstrapData();
    const shardMap = bootstrapData?.detail_shard_map || {};
    let shardKey = normalizeShardKey(detailShardByEquipmentId.get(id) || shardMap[id]);
    if (!shardKey) {
      await ensureLookupFromSnapshotLite();
      shardKey = normalizeShardKey(detailShardByEquipmentId.get(id) || shardMap[id]);
    }

    if (shardKey) {
      try {
        await loadDetailShard(shardKey);
      } catch (error) {
        console.error(error);
      }
    }

    if (detailByEquipmentId.has(id)) {
      const direct = detailByEquipmentId.get(id);
      return resolvePreferredDuplicateDetail(direct);
    }
    return null;
  }

  function findPaperByDoi(papers, doi) {
    const list = Array.isArray(papers) ? papers : [];
    if (!list.length) return null;
    const target = normalizeDoi(doi || "");
    if (!target) return list[0] || null;
    return list.find((paper) => normalizeDoi(paper?.doi || "") === target) || list[0] || null;
  }

  function sourceLabelText(contentSource) {
    if (contentSource === CONTENT_SOURCE_APPROVED) return "";
    if (contentSource === CONTENT_SOURCE_UNAPPROVED) return "全面再構築中";
    return "整備中";
  }

  function sourceNoteText(displayContent) {
    const source = displayContent?.contentSource || CONTENT_SOURCE_FALLBACK;
    const reviewStatus = displayContent?.reviewStatus || "pending";
    if (source === CONTENT_SOURCE_APPROVED) return "";
    if (reviewStatus === "rejected") {
      return "この内容は再審査中です。品質基準を満たすまで公開停止しています。";
    }
    return "機器説明・関連論文解説・初心者ガイドは、機器ごとの手作業再構築が完了するまで公開停止します。";
  }

  async function renderPaperDetailPage(route, token) {
    const overlay = ensureManualRouteOverlay();
    overlay.hidden = false;
    document.body.classList.add("manual-route-open");
    overlay.innerHTML = `
      <button type="button" class="manual-route-backdrop" aria-label="閉じる"></button>
      <article class="manual-route-panel paper-detail-page" role="dialog" aria-modal="true" aria-label="関連論文詳細">
        <header class="manual-route-head">
          <button type="button" class="manual-route-back">&lt; 戻る</button>
          <h3>関連論文の使われ方</h3>
        </header>
        <p class="manual-route-loading">読み込み中...</p>
      </article>
    `;

    const bindClose = () => {
      overlay.querySelector(".manual-route-backdrop")?.addEventListener("click", closeManualRoute);
      overlay.querySelector(".manual-route-back")?.addEventListener("click", closeManualRoute);
    };
    bindClose();

    const detail = await loadDetailByDocId(route.docId);
    if (token !== routeRenderToken) return;

    if (!detail) {
      overlay.innerHTML = `
        <button type="button" class="manual-route-backdrop" aria-label="閉じる"></button>
        <article class="manual-route-panel paper-detail-page" role="dialog" aria-modal="true" aria-label="関連論文詳細">
          <header class="manual-route-head">
            <button type="button" class="manual-route-back">&lt; 戻る</button>
            <h3>関連論文の使われ方</h3>
          </header>
          <p class="manual-route-error">対象機器データを読み込めませんでした。</p>
        </article>
      `;
      bindClose();
      return;
    }

    const display = resolveDisplayContent(detail);
    const paper = findPaperByDoi(display.papers, route.doi);
    const title = String(paper?.title || "タイトル不明").trim();
    const doi = String(paper?.doi || "").trim();
    const url = canonicalPaperUrl(paper?.link_url || paper?.url, doi);
    const note = sourceNoteText(display);
    const sourceBadge = sourceLabelText(display.contentSource);
    const equipmentName = escapeHtml(String(detail?.name || "対象機器"));
    const safeSourceBadge = escapeHtml(sourceBadge);
    const sourceBadgeMarkup = safeSourceBadge ? `<p class="manual-source-badge">${safeSourceBadge}</p>` : "";
    const safeTitle = escapeHtml(title || "タイトル不明");
    const safeDoiMeta = doi ? `DOI: ${escapeHtml(doi)}` : "DOIなし";
    const safeObjective = escapeHtml(String(paper?.objective_ja || "情報準備中です。"));
    const safeMethod = escapeHtml(String(paper?.method_ja || "情報準備中です。"));
    const safeFinding = escapeHtml(String(paper?.finding_ja || "情報準備中です。"));
    const safeUrl = url ? escapeHtml(url) : "";
    const safeNote = note ? escapeHtml(note) : "";

    overlay.innerHTML = `
      <button type="button" class="manual-route-backdrop" aria-label="閉じる"></button>
      <article class="manual-route-panel paper-detail-page" role="dialog" aria-modal="true" aria-label="関連論文詳細">
        <header class="manual-route-head">
          <button type="button" class="manual-route-back">&lt; 戻る</button>
          <div class="manual-route-head-main">
            ${sourceBadgeMarkup}
            <h3>関連論文の使われ方</h3>
            <p class="manual-route-meta">${equipmentName} / ${safeDoiMeta}</p>
          </div>
        </header>
        <div class="paper-detail-content">
          <h4 class="paper-detail-title">${safeTitle}</h4>
          <section class="paper-detail-point">
            <h5>研究目的</h5>
            <p>${safeObjective}</p>
          </section>
          <section class="paper-detail-point">
            <h5>手法</h5>
            <p>${safeMethod}</p>
          </section>
          <section class="paper-detail-point">
            <h5>わかったこと</h5>
            <p>${safeFinding}</p>
          </section>
          <section class="paper-detail-point">
            <h5>リンク</h5>
            <p>原著論文の確認は末尾リンクから行ってください。${safeUrl ? `<a class="paper-detail-link" href="${safeUrl}" target="_blank" rel="noreferrer">論文ページへ遷移する</a>` : "リンク未登録"}</p>
          </section>
          ${safeNote ? `<p class="manual-source-note">${safeNote}</p>` : ""}
        </div>
      </article>
    `;
    bindClose();
  }

  async function renderBeginnerGuidePage(route, token) {
    const overlay = ensureManualRouteOverlay();
    overlay.hidden = false;
    document.body.classList.add("manual-route-open");
    overlay.innerHTML = `
      <button type="button" class="manual-route-backdrop" aria-label="閉じる"></button>
      <article class="manual-route-panel beginner-detail-page" role="dialog" aria-modal="true" aria-label="初心者向け機器ページ">
        <header class="manual-route-head">
          <button type="button" class="manual-route-back">&lt; 戻る</button>
          <h3>初心者向け機器ページ</h3>
        </header>
        <p class="manual-route-loading">読み込み中...</p>
      </article>
    `;
    const bindClose = () => {
      overlay.querySelector(".manual-route-backdrop")?.addEventListener("click", closeManualRoute);
      overlay.querySelector(".manual-route-back")?.addEventListener("click", closeManualRoute);
    };
    const bindBeginnerToc = () => {
      overlay.querySelectorAll(".beginner-toc-link").forEach((link) => {
        link.addEventListener("click", (event) => {
          event.preventDefault();
          const targetId = String(link.getAttribute("data-anchor-target") || "").trim();
          if (!targetId) return;
          const target = overlay.querySelector(`#${targetId}`);
          if (target instanceof HTMLElement) {
            target.scrollIntoView({ behavior: "smooth", block: "start" });
          }
        });
      });
    };
    bindClose();

    const detail = await loadDetailByDocId(route.docId);
    if (token !== routeRenderToken) return;
    if (!detail) {
      overlay.innerHTML = `
        <button type="button" class="manual-route-backdrop" aria-label="閉じる"></button>
        <article class="manual-route-panel beginner-detail-page" role="dialog" aria-modal="true" aria-label="初心者向け機器ページ">
          <header class="manual-route-head">
            <button type="button" class="manual-route-back">&lt; 戻る</button>
            <h3>初心者向け機器ページ</h3>
          </header>
          <p class="manual-route-error">対象機器データを読み込めませんでした。</p>
        </article>
      `;
      bindClose();
      return;
    }

    const display = resolveDisplayContent(detail);
    if (!display.beginnerReady) {
      const sourceBadge = sourceLabelText(display.contentSource);
      const note = sourceNoteText(display);
      const safeSourceBadge = escapeHtml(sourceBadge);
      const sourceBadgeMarkup = safeSourceBadge ? `<p class="manual-source-badge">${safeSourceBadge}</p>` : "";
      const equipmentName = escapeHtml(String(detail?.name || "対象機器"));
      const safeNote = note ? escapeHtml(note) : "";
      overlay.innerHTML = `
        <button type="button" class="manual-route-backdrop" aria-label="閉じる"></button>
        <article class="manual-route-panel beginner-detail-page" role="dialog" aria-modal="true" aria-label="初心者向け機器ページ">
          <header class="manual-route-head">
            <button type="button" class="manual-route-back">&lt; 戻る</button>
            <div class="manual-route-head-main">
              ${sourceBadgeMarkup}
              <h3>初心者向け機器ページ</h3>
              <p class="manual-route-meta">${equipmentName}</p>
            </div>
          </header>
          <div class="beginner-detail-content beginner-article">
            <p class="manual-route-error">初心者向けガイドは整備中です。本文要件（空白除外2000〜3000字・内部ID混入なし）を満たし次第公開します。</p>
            ${safeNote ? `<p class="manual-source-note">${safeNote}</p>` : ""}
          </div>
        </article>
      `;
      bindClose();
      return;
    }
    const guide = display.beginner;
    const sourceBadge = sourceLabelText(display.contentSource);
    const note = sourceNoteText(display);
    const steps = Array.isArray(guide?.basic_steps_ja) ? guide.basic_steps_ja : [];
    const pitfalls = Array.isArray(guide?.common_pitfalls_ja) ? guide.common_pitfalls_ja : [];
    const safeSourceBadge = escapeHtml(sourceBadge);
    const sourceBadgeMarkup = safeSourceBadge ? `<p class="manual-source-badge">${safeSourceBadge}</p>` : "";
    const equipmentName = escapeHtml(String(detail?.name || "対象機器"));
    const safePrinciple = escapeHtml(String(guide?.principle_ja || "情報準備中です。"));
    const safeSampleGuidance = escapeHtml(String(guide?.sample_guidance_ja || "情報準備中です。"));
    const safeSteps = (steps.length ? steps : ["情報準備中です。"])
      .map((value) => `<li>${escapeHtml(String(value || ""))}</li>`)
      .join("");
    const safePitfalls = (pitfalls.length ? pitfalls : ["情報準備中です。"])
      .map((value) => `<li>${escapeHtml(String(value || ""))}</li>`)
      .join("");
    const safeNote = note ? escapeHtml(note) : "";

    overlay.innerHTML = `
      <button type="button" class="manual-route-backdrop" aria-label="閉じる"></button>
      <article class="manual-route-panel beginner-detail-page" role="dialog" aria-modal="true" aria-label="初心者向け機器ページ">
        <header class="manual-route-head">
          <button type="button" class="manual-route-back">&lt; 戻る</button>
          <div class="manual-route-head-main">
            ${sourceBadgeMarkup}
            <h3>初心者向け機器ページ</h3>
            <p class="manual-route-meta">${equipmentName}</p>
          </div>
        </header>
        <div class="beginner-detail-content beginner-article">
          <nav class="beginner-toc" aria-label="初心者ガイド目次">
            <p class="beginner-toc-title">目次</p>
            <ol class="beginner-toc-list">
              <li><a href="#principle" class="beginner-toc-link" data-anchor-target="principle">原理</a></li>
              <li><a href="#sample" class="beginner-toc-link" data-anchor-target="sample">試料</a></li>
              <li><a href="#steps" class="beginner-toc-link" data-anchor-target="steps">基本手順</a></li>
              <li><a href="#pitfalls" class="beginner-toc-link" data-anchor-target="pitfalls">失敗しやすい点</a></li>
            </ol>
          </nav>
          <section class="beginner-detail-section" id="principle">
            <h4 class="beginner-section-heading">原理</h4>
            <p>${safePrinciple}</p>
          </section>
          <section class="beginner-detail-section" id="sample">
            <h4 class="beginner-section-heading">試料（固体/液体など）</h4>
            <p>${safeSampleGuidance}</p>
          </section>
          <section class="beginner-detail-section" id="steps">
            <h4 class="beginner-section-heading">基本手順</h4>
            <ul>${safeSteps}</ul>
          </section>
          <section class="beginner-detail-section" id="pitfalls">
            <h4 class="beginner-section-heading">失敗しやすい点</h4>
            <ul>${safePitfalls}</ul>
          </section>
          ${safeNote ? `<p class="manual-source-note">${safeNote}</p>` : ""}
        </div>
      </article>
    `;
    bindClose();
    bindBeginnerToc();
  }

  async function handleRouteChange() {
    const route = parseHashRoute();
    if (!route) {
      hideManualRouteOverlay();
      return;
    }

    routeRenderToken += 1;
    const token = routeRenderToken;
    if (route.type === "paper") {
      await renderPaperDetailPage(route, token);
      return;
    }
    if (route.type === "beginner") {
      await renderBeginnerGuidePage(route, token);
      return;
    }
    hideManualRouteOverlay();
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
      <article class="paper-preview-panel" role="dialog" aria-modal="true" aria-label="関連論文解説">
        <header class="paper-preview-head">
          <h4 class="paper-preview-title"></h4>
          <p class="paper-preview-meta"></p>
        </header>
        <div class="paper-preview-structured">
          <section class="paper-preview-point">
            <h5>研究目的</h5>
            <p data-point="objective"></p>
          </section>
          <section class="paper-preview-point">
            <h5>手法</h5>
            <p data-point="method"></p>
          </section>
          <section class="paper-preview-point">
            <h5>わかったこと</h5>
            <p data-point="finding"></p>
          </section>
          <section class="paper-preview-point">
            <h5>リンク</h5>
            <p data-point="link"></p>
          </section>
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
    const doi = String(paper?.doi || "").trim();
    const url = canonicalPaperUrl(paper?.link_url || paper?.url, doi);

    const titleEl = modal.querySelector(".paper-preview-title");
    if (titleEl) titleEl.textContent = title;

    const metaParts = [];
    if (doi) metaParts.push(`DOI: ${doi}`);
    const metaEl = modal.querySelector(".paper-preview-meta");
    if (metaEl) metaEl.textContent = metaParts.length ? metaParts.join(" / ") : "メタ情報なし";

    const objective = String(paper?.objective_ja || "").trim();
    const method = String(paper?.method_ja || "").trim();
    const finding = String(paper?.finding_ja || "").trim();
    const pointMap = {
      objective: objective || "情報準備中です。",
      method: method || "情報準備中です。",
      finding: finding || "情報準備中です。",
      link: url || "リンク未登録",
    };

    Object.entries(pointMap).forEach(([key, text]) => {
      const el = modal.querySelector(`[data-point=\"${key}\"]`);
      if (el) {
        el.textContent = text;
      }
    });

    const openButton = modal.querySelector(".paper-preview-open");
    if (openButton instanceof HTMLButtonElement) {
      openButton.disabled = !url;
    }
    modal.dataset.paperUrl = url || "";
    modal.dataset.open = "1";
    modal.hidden = false;
  }

  function ensureBeginnerGuideModal() {
    let modal = document.getElementById("beginner-guide-modal");
    if (modal) return modal;

    modal = document.createElement("div");
    modal.id = "beginner-guide-modal";
    modal.className = "beginner-guide-modal";
    modal.hidden = true;
    modal.innerHTML = `
      <button type="button" class="beginner-guide-backdrop" aria-label="閉じる"></button>
      <article class="beginner-guide-panel" role="dialog" aria-modal="true" aria-label="初心者向け機器ガイド">
        <header class="beginner-guide-head">
          <h4 class="beginner-guide-title">初心者向け機器ガイド</h4>
          <p class="beginner-guide-meta"></p>
        </header>
        <div class="beginner-guide-body">
          <section class="beginner-guide-point">
            <h5>原理</h5>
            <p data-guide=\"principle\"></p>
          </section>
          <section class="beginner-guide-point">
            <h5>試料（固体/液体など）</h5>
            <p data-guide=\"sample\"></p>
          </section>
          <section class="beginner-guide-point">
            <h5>基本手順</h5>
            <ul data-guide=\"steps\"></ul>
          </section>
          <section class="beginner-guide-point">
            <h5>失敗しやすい点</h5>
            <ul data-guide=\"pitfalls\"></ul>
          </section>
        </div>
        <footer class="beginner-guide-actions">
          <button type=\"button\" class=\"beginner-guide-close\">閉じる</button>
        </footer>
      </article>
    `;
    document.body.appendChild(modal);

    const close = () => {
      modal.hidden = true;
      modal.dataset.open = "0";
    };
    modal.querySelector(".beginner-guide-backdrop")?.addEventListener("click", close);
    modal.querySelector(".beginner-guide-close")?.addEventListener("click", close);

    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && modal.dataset.open === "1") {
        close();
      }
    });

    return modal;
  }

  function openBeginnerGuideModal(equipmentName, guide) {
    const modal = ensureBeginnerGuideModal();
    const meta = modal.querySelector(".beginner-guide-meta");
    if (meta) {
      meta.textContent = String(equipmentName || "対象機器");
    }

    const principle = modal.querySelector('[data-guide=\"principle\"]');
    const sample = modal.querySelector('[data-guide=\"sample\"]');
    const steps = modal.querySelector('[data-guide=\"steps\"]');
    const pitfalls = modal.querySelector('[data-guide=\"pitfalls\"]');

    if (principle) {
      principle.textContent = String(guide?.principle_ja || "").trim() || "情報準備中です。";
    }
    if (sample) {
      sample.textContent = String(guide?.sample_guidance_ja || "").trim() || "情報準備中です。";
    }

    if (steps) {
      steps.innerHTML = "";
      const values = Array.isArray(guide?.basic_steps_ja) ? guide.basic_steps_ja : [];
      const list = values.length ? values : ["情報準備中です。"];
      list.forEach((value) => {
        const li = document.createElement("li");
        li.textContent = String(value || "");
        steps.appendChild(li);
      });
    }

    if (pitfalls) {
      pitfalls.innerHTML = "";
      const values = Array.isArray(guide?.common_pitfalls_ja) ? guide.common_pitfalls_ja : [];
      const list = values.length ? values : ["情報準備中です。"];
      list.forEach((value) => {
        const li = document.createElement("li");
        li.textContent = String(value || "");
        pitfalls.appendChild(li);
      });
    }

    modal.dataset.open = "1";
    modal.hidden = false;
  }

  function normalizeManualStateItems(values) {
    const allowed = new Set(["固体", "液体", "粉末", "気体", "生体", "その他"]);
    const source = Array.isArray(values) ? values : [];
    const out = [];
    source.forEach((value) => {
      const text = String(value || "").trim();
      if (!text || !allowed.has(text)) return;
      if (!out.includes(text)) out.push(text);
    });
    return out.slice(0, 6);
  }

  function normalizeManualFieldItems(values, max = 4) {
    const source = Array.isArray(values) ? values : [];
    const out = [];
    source.forEach((value) => {
      const text = String(value || "").trim();
      if (!text) return;
      if (!out.includes(text)) out.push(text);
    });
    return out.slice(0, Math.max(1, max));
  }

  function countChars(text, mode = "non_whitespace") {
    const raw = String(text || "");
    if (mode === "non_whitespace") {
      return raw.replace(/\s+/g, "").length;
    }
    return raw.trim().length;
  }

  function beginnerCharCount(guide, mode = "non_whitespace") {
    const principle = String(guide?.principle_ja || "").trim();
    const sample = String(guide?.sample_guidance_ja || "").trim();
    const steps = Array.isArray(guide?.basic_steps_ja) ? guide.basic_steps_ja : [];
    const pitfalls = Array.isArray(guide?.common_pitfalls_ja) ? guide.common_pitfalls_ja : [];
    return countChars([principle, sample, steps.join(""), pitfalls.join("")].join(""), mode);
  }

  function hasInternalIdReference(detail, general, papers, beginner) {
    const docId = String(detail?.doc_id || "").trim().toLowerCase();
    const equipmentId = String(detail?.equipment_id || "").trim().toLowerCase();
    const paperList = Array.isArray(papers) ? papers : [];
    const steps = Array.isArray(beginner?.basic_steps_ja) ? beginner.basic_steps_ja : [];
    const pitfalls = Array.isArray(beginner?.common_pitfalls_ja) ? beginner.common_pitfalls_ja : [];
    const articleText = [
      String(general?.summary_ja || ""),
      Array.isArray(general?.research_fields_ja) ? general.research_fields_ja.join("") : "",
      String(beginner?.principle_ja || ""),
      String(beginner?.sample_guidance_ja || ""),
      steps.join(""),
      pitfalls.join(""),
      paperList.map((paper) => String(paper?.objective_ja || "")).join(""),
      paperList.map((paper) => String(paper?.method_ja || "")).join(""),
      paperList.map((paper) => String(paper?.finding_ja || "")).join(""),
    ].join("");
    const lower = articleText.toLowerCase();
    if (docId && lower.includes(docId)) return true;
    if (equipmentId && lower.includes(equipmentId)) return true;
    return INTERNAL_ID_PATTERN.test(articleText);
  }

  function hasAutoTemplateMarker(general, papers, beginner) {
    const paperList = Array.isArray(papers) ? papers : [];
    const steps = Array.isArray(beginner?.basic_steps_ja) ? beginner.basic_steps_ja : [];
    const pitfalls = Array.isArray(beginner?.common_pitfalls_ja) ? beginner.common_pitfalls_ja : [];
    const articleText = [
      String(general?.summary_ja || ""),
      String(beginner?.principle_ja || ""),
      String(beginner?.sample_guidance_ja || ""),
      steps.join(""),
      pitfalls.join(""),
      paperList.map((paper) => String(paper?.objective_ja || "")).join(""),
      paperList.map((paper) => String(paper?.method_ja || "")).join(""),
      paperList.map((paper) => String(paper?.finding_ja || "")).join(""),
    ].join("");
    return AUTO_TEMPLATE_MARKERS.some((marker) => articleText.includes(marker));
  }

  function normalizeManualPaperExplanations(values) {
    const source = Array.isArray(values) ? values : [];
    const out = [];
    source.slice(0, 3).forEach((value) => {
      if (!value || typeof value !== "object") return;
      const doi = normalizeDoi(value.doi || "");
      const title = String(value.title || "").trim();
      const objective = String(value.objective_ja || "").trim();
      const method = String(value.method_ja || "").trim();
      const finding = String(value.finding_ja || "").trim();
      const linkUrl = String(value.link_url || "").trim() || (doi ? `https://doi.org/${doi}` : "");
      out.push({
        doi,
        title,
        objective_ja: objective,
        method_ja: method,
        finding_ja: finding,
        link_url: linkUrl,
      });
    });
    return out;
  }

  function resolveManualContent(detail) {
    const data = detail && typeof detail.manual_content_v1 === "object" ? detail.manual_content_v1 : null;
    if (!data) {
      return {
        reviewStatus: "pending",
        general: {
          summary_ja: "",
          sample_states: [],
          research_fields_ja: [],
        },
        papers: [],
        beginner: {
          principle_ja: "",
          sample_guidance_ja: "",
          basic_steps_ja: [],
          common_pitfalls_ja: [],
        },
      };
    }

    const review = data?.review && typeof data.review === "object" ? data.review : {};
    const rawStatus = String(review?.status || "pending").trim().toLowerCase();
    const reviewStatus = ["approved", "pending", "rejected"].includes(rawStatus) ? rawStatus : "pending";
    const usage = data?.general_usage && typeof data.general_usage === "object" ? data.general_usage : {};
    const beginner = data?.beginner_guide && typeof data.beginner_guide === "object" ? data.beginner_guide : {};

    return {
      reviewStatus,
      general: {
        summary_ja: String(usage?.summary_ja || "").trim(),
        sample_states: normalizeManualStateItems(usage?.sample_states),
        research_fields_ja: normalizeManualFieldItems(usage?.research_fields_ja, 4),
      },
      papers: normalizeManualPaperExplanations(data?.paper_explanations),
      beginner: {
        principle_ja: String(beginner?.principle_ja || "").trim(),
        sample_guidance_ja: String(beginner?.sample_guidance_ja || "").trim(),
        basic_steps_ja: normalizeManualFieldItems(beginner?.basic_steps_ja || beginner?.basic_steps, 6),
        common_pitfalls_ja: normalizeManualFieldItems(
          beginner?.common_pitfalls_ja || beginner?.common_pitfalls,
          6
        ),
      },
    };
  }

  function chooseFallbackPaper(detail) {
    const source = `${String(detail?.name || "")} ${String(detail?.category_general || "")} ${String(detail?.category_detail || "")}`;
    const matched = FALLBACK_PAPER_MAP.find((entry) => entry.pattern.test(source));
    return matched || FALLBACK_PAPER_DEFAULT;
  }

  function firstMeaningfulSentence(text, maxLen = 220) {
    const raw = String(text || "").trim();
    if (!raw) return "";
    const chunks = raw
      .split(/[。\n]/)
      .map((value) => value.trim())
      .filter(Boolean);
    const found = chunks.find((value) => value.length >= 20) || raw;
    return found.slice(0, maxLen);
  }

  function deriveSampleStates(detail, preferredStates) {
    const manualStates = normalizeManualStateItems(preferredStates);
    if (manualStates.length) return manualStates;

    const source = `${String(detail?.name || "")} ${String(detail?.category_general || "")} ${String(
      detail?.category_detail || ""
    )}`;
    const out = [];
    const add = (state) => {
      if (!out.includes(state)) out.push(state);
    };

    if (/細胞|生体|培養|フロー|DNA|RNA|PCR|組織|免疫/i.test(source)) {
      add("生体");
      add("液体");
    }
    if (/粉末|材料|SEM|TEM|FIB|X線|顕微|硬度|結晶|金属/i.test(source)) {
      add("固体");
      add("粉末");
    }
    if (/ガス|GC|気相|吸着|プラズマ/i.test(source)) {
      add("気体");
    }
    if (/液体|溶液|HPLC|NMR|分光|クロマト/i.test(source)) {
      add("液体");
    }
    if (!out.length) {
      add("固体");
      add("液体");
    }
    return out.slice(0, 6);
  }

  function deriveResearchFields(detail, preferredFields) {
    const manualFields = normalizeManualFieldItems(preferredFields, 4);
    const out = [...manualFields];
    const add = (value) => {
      const text = String(value || "").trim();
      if (!text) return;
      if (!out.includes(text)) out.push(text);
    };

    const source = `${String(detail?.name || "")} ${String(detail?.category_general || "")} ${String(
      detail?.category_detail || ""
    )}`;
    if (/分光|クロマト|質量|NMR|分析/i.test(source)) add("分析化学");
    if (/材料|結晶|薄膜|表面|顕微|FIB|SEM|TEM/i.test(source)) add("材料科学");
    if (/細胞|生体|DNA|RNA|フロー|培養|免疫/i.test(source)) add("生命科学");
    if (/電気|半導体|デバイス|工学|機械/i.test(source)) add("電子・デバイス工学");
    if (/環境|ガス|CO2|水質/i.test(source)) add("環境工学");

    const insightsFields = detail?.usage_insights?.fields?.items;
    if (Array.isArray(insightsFields)) {
      insightsFields.forEach((value) => add(value));
    }

    const papers = Array.isArray(detail?.papers) ? detail.papers : [];
    papers.slice(0, 3).forEach((paper) => {
      if (!paper || typeof paper !== "object") return;
      const fields = Array.isArray(paper.research_fields_ja) ? paper.research_fields_ja : [];
      fields.forEach((value) => add(value));
    });

    if (!out.length) add("計測工学");
    return out.slice(0, 4);
  }

  function derivePaperExplanations(detail, preferredPapers) {
    const normalizedManualPapers = normalizeManualPaperExplanations(preferredPapers);
    const out = normalizedManualPapers.filter((paper) => {
      return paper?.objective_ja || paper?.method_ja || paper?.finding_ja;
    });
    if (out.length) {
      return out.slice(0, 3).map((paper) => {
        const doi = normalizeDoi(paper?.doi || "");
        const link = canonicalPaperUrl(paper?.link_url || "", doi);
        return {
          doi,
          title: String(paper?.title || "").trim() || "タイトル不明",
          objective_ja: String(paper?.objective_ja || "").trim() || "情報準備中です。",
          method_ja: String(paper?.method_ja || "").trim() || "情報準備中です。",
          finding_ja: String(paper?.finding_ja || "").trim() || "情報準備中です。",
          link_url: link || (doi ? `https://doi.org/${doi}` : ""),
        };
      });
    }

    const papers = Array.isArray(detail?.papers) ? detail.papers : [];
    const generated = [];
    papers.slice(0, 3).forEach((paper) => {
      if (!paper || typeof paper !== "object") return;
      const doi = normalizeDoi(paper.doi || "");
      const title = String(paper.title || "").trim() || "タイトル不明";
      const objectiveRaw = String(paper.usage_what_ja || "").trim();
      const methodRaw = String(paper.usage_how_ja || "").trim();
      const findingRaw = firstMeaningfulSentence(paper.abstract_ja || paper.abstract || "");
      const objective =
        objectiveRaw && objectiveRaw.length >= 20
          ? objectiveRaw
          : `${String(detail?.name || "当該装置")}を用いて対象現象を定量化し、評価指標の有効性を確認した。`;
      const method =
        methodRaw && methodRaw.length >= 20
          ? methodRaw
          : `${String(detail?.name || "当該装置")}の測定条件を統一し、再現性を確認した上で比較解析を実施した。`;
      const finding =
        findingRaw && findingRaw.length >= 20
          ? findingRaw
          : `${String(detail?.name || "当該装置")}の利用により、条件差の影響を定量評価できることが示された。`;
      const link = canonicalPaperUrl(paper.url, doi) || (doi ? `https://doi.org/${doi}` : "");
      generated.push({
        doi: doi || normalizeDoi(link),
        title,
        objective_ja: objective,
        method_ja: method,
        finding_ja: finding,
        link_url: link || (doi ? `https://doi.org/${doi}` : ""),
      });
    });
    if (generated.length) return generated.slice(0, 3);

    const fallback = chooseFallbackPaper(detail);
    return [
      {
        doi: fallback.doi,
        title: fallback.title,
        objective_ja: `${String(detail?.name || "当該装置")}が対象試料の特性評価にどの程度有効かを検証し、研究設計の妥当性を確認した。`,
        method_ja: `${String(detail?.name || "当該装置")}の設定条件を段階的に最適化し、再現性と感度を比較する手法で評価した。`,
        finding_ja: `${String(detail?.name || "当該装置")}を用いることで信号の再現性が向上し、実験条件最適化の指針が得られた。`,
        link_url: `https://doi.org/${fallback.doi}`,
      },
    ];
  }

  function deriveBeginnerGuide(detail, manualBeginner, sampleStates, researchFields) {
    const beginner = manualBeginner || {};
    const name = String(detail?.name || "当該装置");
    const category = String(detail?.category_general || "対象分野");
    const detailLabel = String(detail?.category_detail || "");
    const sampleLabel = (Array.isArray(sampleStates) ? sampleStates : []).join("・") || "試料";
    const fieldLabel = (Array.isArray(researchFields) ? researchFields : []).slice(0, 2).join("・") || category;
    const target = `${category}${detailLabel ? `（${detailLabel}）` : ""}`;

    const principle =
      String(beginner?.principle_ja || "").trim() ||
      `${name}は${target}における信号変化を検出し、条件間の差を定量比較するための装置である。基準条件を固定して再現性を確保してから本測定を行う。`;
    const sampleGuidance =
      String(beginner?.sample_guidance_ja || "").trim() ||
      `${name}では${sampleLabel}を扱うため、前処理条件のばらつきや汚染混入を避けるために、濃度・温度・保存状態を測定前に確認する。`;

    const stepsSource = normalizeManualFieldItems(beginner?.basic_steps_ja || beginner?.basic_steps, 6);
    const pitfallsSource = normalizeManualFieldItems(
      beginner?.common_pitfalls_ja || beginner?.common_pitfalls,
      6
    );
    const steps = stepsSource.length
      ? stepsSource
      : [
          `${name}で扱う試料条件を記録し、${target}に必要な前処理手順を測定前に確定する。`,
          `標準試料またはブランクで初期測定を行い、${name}のベースラインと感度を確認する。`,
          `${fieldLabel}の比較評価は同一条件で複数回測定し、外れ値確認後に本解析へ進める。`,
        ];
    const pitfalls = pitfallsSource.length
      ? pitfallsSource
      : [
          `${name}では前処理時間や温度のわずかなずれが信号変動を拡大し、比較結果の信頼性を下げやすい。`,
          `${target}の評価途中で条件を変更すると、試料差と条件差が混在し、解釈を誤る原因になりやすい。`,
        ];

    return {
      principle_ja: principle,
      sample_guidance_ja: sampleGuidance,
      basic_steps_ja: steps.slice(0, 6),
      common_pitfalls_ja: pitfalls.slice(0, 6),
    };
  }

  function resolveDisplayContent(detail) {
    const manual = resolveManualContent(detail);
    const reviewStatus = manual?.reviewStatus || "pending";

    const summaryManual = String(manual?.general?.summary_ja || "").trim();
    const summaryFallback = String(detail?.usage_manual_summary || "").trim();
    const summary =
      summaryManual ||
      summaryFallback ||
      `${String(detail?.name || "当該装置")}は${String(detail?.category_general || "研究")}領域で、試料状態の変化を定量評価し再現性のある比較データを得るために利用される。`;
    const sampleStates = deriveSampleStates(detail, manual?.general?.sample_states);
    const researchFields = deriveResearchFields(detail, manual?.general?.research_fields_ja);
    const papers = derivePaperExplanations(detail, manual?.papers);
    const beginner = deriveBeginnerGuide(detail, manual?.beginner, sampleStates, researchFields);
    const beginnerNonWsChars = beginnerCharCount(beginner, "non_whitespace");
    const internalIdHit = hasInternalIdReference(
      detail,
      { summary_ja: summary, research_fields_ja: researchFields },
      papers,
      beginner
    );
    const templateMarkerHit = hasAutoTemplateMarker(
      { summary_ja: summary, research_fields_ja: researchFields },
      papers,
      beginner
    );
    const name = String(detail?.name || "").trim();
    const summaryHasName = !name || summary.includes(name);
    const principleHasName = !name || String(beginner?.principle_ja || "").includes(name);
    const contentQualityReady =
      reviewStatus === "approved" &&
      beginnerNonWsChars >= MIN_BEGINNER_NON_WS_CHARS &&
      beginnerNonWsChars <= MAX_BEGINNER_NON_WS_CHARS &&
      !internalIdHit &&
      summaryHasName &&
      principleHasName;
    const beginnerReady = contentQualityReady;

    const hasManualBody =
      summaryManual ||
      (manual?.general?.sample_states || []).length ||
      (manual?.general?.research_fields_ja || []).length ||
      (manual?.papers || []).length ||
      String(manual?.beginner?.principle_ja || "").trim();

    const contentSource =
      contentQualityReady
        ? CONTENT_SOURCE_APPROVED
        : hasManualBody
        ? CONTENT_SOURCE_UNAPPROVED
        : CONTENT_SOURCE_FALLBACK;

    return {
      reviewStatus,
      contentSource,
      beginnerNonWsChars,
      internalIdHit,
      templateMarkerHit,
      summaryHasName,
      principleHasName,
      contentQualityReady,
      beginnerReady,
      general: {
        summary_ja: summary,
        sample_states: sampleStates,
        research_fields_ja: researchFields,
      },
      papers,
      beginner,
    };
  }

  function renderManualPendingStatus(container, displayContent) {
    const note = sourceNoteText(displayContent);
    if (!note) return;
    const pending = document.createElement("p");
    pending.className = "manual-review-status";
    pending.textContent = note;
    container.appendChild(pending);
  }

  function resolveDetailDocId(detail) {
    return String(detail?.doc_id || detail?.equipment_id || "").trim();
  }

  function buildPaperRouteHash(docId, doi) {
    return `#/paper/${encodeURIComponent(String(docId || "").trim())}/${encodeURIComponent(
      String(doi || "no-doi").trim()
    )}`;
  }

  function buildBeginnerRouteHash(docId) {
    return `#/beginner/${encodeURIComponent(String(docId || "").trim())}`;
  }

  function renderGeneralUsage(content, displayContent, detail) {
    if (!displayContent?.contentQualityReady) {
      const section = document.createElement("section");
      section.className = "manual-usage-section";
      section.innerHTML = `
        <div class="manual-usage-head">
          <h5 class="manual-usage-heading">機器の説明</h5>
          <span class="manual-source-badge">全面再構築中</span>
        </div>
        <p class="manual-usage-summary">この機器の説明・関連論文解説は品質基準を満たすまで公開停止しています。現在、機器ごとに手作業で再作成中です。</p>
      `;
      content.appendChild(section);

      const beginnerEntry = document.createElement("div");
      beginnerEntry.className = "manual-beginner-entry";
      beginnerEntry.innerHTML = `
        <p class="manual-beginner-caption">研究を始めたばかりの方向け</p>
        <button type="button" class="manual-beginner-button" disabled>初心者向けガイド整備中</button>
      `;
      content.appendChild(beginnerEntry);
      return;
    }

    const section = document.createElement("section");
    section.className = "manual-usage-section";
    const sourceBadge = sourceLabelText(displayContent?.contentSource);
    const sourceBadgeMarkup = sourceBadge ? `<span class="manual-source-badge">${escapeHtml(sourceBadge)}</span>` : "";
    section.innerHTML = `
      <div class="manual-usage-head">
        <h5 class="manual-usage-heading">一般的な使い方</h5>
        ${sourceBadgeMarkup}
      </div>
      <p class="manual-usage-summary"></p>
      <div class="manual-usage-block">
        <h6>試料状態</h6>
        <ul class="manual-chip-list manual-sample-states"></ul>
      </div>
      <div class="manual-usage-block">
        <h6>使用される研究分野</h6>
        <ul class="manual-chip-list manual-research-fields"></ul>
      </div>
    `;

    const summaryEl = section.querySelector(".manual-usage-summary");
    if (summaryEl) {
      summaryEl.textContent = displayContent.general.summary_ja || "説明準備中です。";
    }

    const sampleList = section.querySelector(".manual-sample-states");
    if (sampleList) {
      sampleList.innerHTML = "";
      const values = displayContent.general.sample_states.length ? displayContent.general.sample_states : ["その他"];
      values.forEach((state) => {
        const li = document.createElement("li");
        li.textContent = state;
        sampleList.appendChild(li);
      });
    }

    const fieldsList = section.querySelector(".manual-research-fields");
    if (fieldsList) {
      fieldsList.innerHTML = "";
      const values = displayContent.general.research_fields_ja.length
        ? displayContent.general.research_fields_ja
        : ["準備中"];
      values.forEach((field) => {
        const li = document.createElement("li");
        li.textContent = field;
        fieldsList.appendChild(li);
      });
    }
    content.appendChild(section);

    const beginnerEntry = document.createElement("div");
    beginnerEntry.className = "manual-beginner-entry";
    beginnerEntry.innerHTML = `
      <p class="manual-beginner-caption">研究を始めたばかりの方向け</p>
      <button type="button" class="manual-beginner-button">初心者向けガイドを開く</button>
    `;
    const docId = resolveDetailDocId(detail);
    const hasGuide =
      displayContent.beginnerReady &&
      docId;
    const button = beginnerEntry.querySelector(".manual-beginner-button");
    if (button instanceof HTMLButtonElement) {
      button.disabled = !hasGuide;
      if (!hasGuide) {
        button.textContent = "初心者向けガイド整備中";
      }
      const openGuideRoute = () => {
        if (!hasGuide) return;
        pushRoute(buildBeginnerRouteHash(docId));
      };
      button.addEventListener("click", openGuideRoute);
      button.addEventListener("keydown", (event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          openGuideRoute();
        }
      });
    }
    content.appendChild(beginnerEntry);
  }

  function renderManualPaperExplanations(paperSection, displayContent, detail) {
    if (!displayContent?.contentQualityReady) {
      const empty = document.createElement("p");
      empty.className = "paper-status manual-paper-status";
      empty.textContent = "関連論文解説は機器説明の再構築完了後に公開します。";
      paperSection.appendChild(empty);
      return;
    }

    const papers = Array.isArray(displayContent?.papers) ? displayContent.papers : [];
    if (!papers.length) {
      const empty = document.createElement("p");
      empty.className = "paper-status manual-paper-status";
      empty.textContent = "関連論文解説は現在準備中です。";
      paperSection.appendChild(empty);
      return;
    }

    const list = document.createElement("ul");
    list.className = "paper-list manual-paper-list";
    const docId = resolveDetailDocId(detail);
    papers.forEach((paper) => {
      const li = document.createElement("li");
      li.className = "paper-item manual-paper-item";
      li.tabIndex = 0;
      li.innerHTML = `
        <p class="paper-title"></p>
        <div class="paper-meta"></div>
      `;
      const titleEl = li.querySelector(".paper-title");
      if (titleEl) titleEl.textContent = String(paper?.title || (paper?.doi ? `DOI ${paper.doi}` : "タイトル不明"));

      const meta = li.querySelector(".paper-meta");
      if (meta) {
        meta.innerHTML = "";
        if (paper?.doi) {
          const doiChip = document.createElement("span");
          doiChip.textContent = `DOI: ${paper.doi}`;
          meta.appendChild(doiChip);
        }
        if (paper?.link_url) {
          const hintChip = document.createElement("span");
          hintChip.textContent = "クリックで4項目解説";
          meta.appendChild(hintChip);
        }
      }

      const openPaperRoute = () => {
        if (!docId) return;
        pushRoute(buildPaperRouteHash(docId, paper?.doi));
      };
      li.addEventListener("click", openPaperRoute);
      li.addEventListener("keydown", (event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          openPaperRoute();
        }
      });
      list.appendChild(li);
    });
    paperSection.appendChild(list);
  }

  function applyDetailToSheet(panel, detail, signature) {
    if (!panel || !detail) return;
    const displayContent = resolveDisplayContent(detail);

    const content = panel.querySelector(".equipment-sheet-content");
    if (content) {
      const summaryEl = content.querySelector("p");
      if (summaryEl) {
        summaryEl.hidden = true;
        summaryEl.textContent = "";
      }

      const bulletList = content.querySelector("ul");
      if (bulletList) {
        bulletList.hidden = true;
        bulletList.innerHTML = "";
      }

      const oldUsage = content.querySelector(".manual-usage-section");
      const oldBeginner = content.querySelector(".manual-beginner-entry");
      const oldReviewStatus = content.querySelector(".manual-review-status");
      if (oldUsage) oldUsage.remove();
      if (oldBeginner) oldBeginner.remove();
      if (oldReviewStatus) oldReviewStatus.remove();

      renderGeneralUsage(content, displayContent, detail);
      renderManualPendingStatus(content, displayContent);
    }

    const paperSection = panel.querySelector(".equipment-sheet-papers");
    if (paperSection) {
      const oldStatus = paperSection.querySelector(".paper-status");
      const oldList = paperSection.querySelector(".paper-list");
      const oldManualStatus = paperSection.querySelector(".manual-paper-status");
      if (oldStatus) oldStatus.remove();
      if (oldList) oldList.remove();
      if (oldManualStatus) oldManualStatus.remove();
      renderManualPaperExplanations(paperSection, displayContent, detail);
    }

    const body = panel.querySelector(".equipment-sheet-body");
    if (body instanceof HTMLElement) {
      const recommendationSection = body.querySelector(".equipment-sheet-recommendations");
      if (content instanceof HTMLElement) {
        body.insertBefore(content, body.firstElementChild);
      }
      if (
        content instanceof HTMLElement &&
        paperSection instanceof HTMLElement &&
        paperSection.previousElementSibling !== content
      ) {
        content.after(paperSection);
      }
      if (
        paperSection instanceof HTMLElement &&
        recommendationSection instanceof HTMLElement &&
        recommendationSection.previousElementSibling !== paperSection
      ) {
        paperSection.after(recommendationSection);
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
    return;
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

    bootstrapDataPromise = originalFetch(appendAssetVersion(PATH_BOOTSTRAP), { cache: "no-store" })
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
    const clickSuppressMs = 220;
    let pointerId = null;
    let startX = 0;
    let startY = 0;
    let moved = false;
    let lastDragAt = 0;

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

    // React側がshape上でpointer captureを取るとクリックが失われる場合があるため、
    // mouse操作時のみ即座に解放して都道府県クリックを優先する。
    map.addEventListener(
      "pointerdown",
      (event) => {
        if (event.pointerType !== "mouse") return;
        const target = event.target;
        if (!(target instanceof Element)) return;
        if (!target.closest(".jp-map-shape") && !target.closest(".jp-map-marker")) return;
        const pointerId = event.pointerId;
        window.setTimeout(() => {
          try {
            if (map.hasPointerCapture?.(pointerId)) {
              map.releasePointerCapture(pointerId);
            }
          } catch {
            // noop
          }
        }, 0);
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
          lastDragAt = Date.now();
        }
      },
      { passive: true }
    );

    const onPointerEnd = (event) => {
      if (event.pointerId !== pointerId) return;
      if (moved) {
        lastDragAt = Date.now();
      } else {
        const target =
          event.target instanceof Element
            ? event.target
            : document.elementFromPoint(event.clientX, event.clientY);
        if (target instanceof Element) {
          if (target.closest(".jp-map-shape") || target.closest(".jp-map-marker")) {
            const prefecture = extractPrefectureFromShapeTarget(target);
            scheduleMapInfoFallbackProbe(prefecture);
          }
        }
      }
      pointerId = null;
      moved = false;
    };

    map.addEventListener("pointerup", onPointerEnd, { passive: true });
    map.addEventListener("pointercancel", onPointerEnd, { passive: true });

    map.addEventListener(
      "click",
      (event) => {
        const target = event.target;
        if (!(target instanceof Element)) return;
        if (!target.closest(".jp-map-shape") && !target.closest(".jp-map-marker")) return;
        if (Date.now() - lastDragAt < clickSuppressMs) {
          event.preventDefault();
          event.stopPropagation();
        }
      },
      true
    );
  }

  function installResultsListHeightLock() {
    if (document.body?.dataset.resultsHeightLockBound === "1") return;
    if (!document.body) return;
    document.body.dataset.resultsHeightLockBound = "1";

    waitForElement(".results-list", (list) => {
      if (!(list instanceof Element)) return;
      if (list.dataset.heightLockBound === "1") return;
      list.dataset.heightLockBound = "1";

      let maxHeight = 0;
      let raf = 0;

      const measure = () => {
        if (!list.isConnected) return;
        const currentHeight = Math.ceil(list.getBoundingClientRect().height || 0);
        if (currentHeight <= 0) return;
        if (currentHeight > maxHeight) {
          maxHeight = currentHeight;
          list.style.minHeight = `${maxHeight}px`;
        } else if (maxHeight > 0 && !list.style.minHeight) {
          list.style.minHeight = `${maxHeight}px`;
        }
      };

      const scheduleMeasure = (delay = 0) => {
        window.setTimeout(() => {
          if (raf) window.cancelAnimationFrame(raf);
          raf = window.requestAnimationFrame(() => {
            raf = 0;
            measure();
          });
        }, delay);
      };

      measure();
      scheduleMeasure(120);
      scheduleMeasure(360);

      if ("ResizeObserver" in window) {
        const observer = new ResizeObserver(() => {
          scheduleMeasure(0);
        });
        observer.observe(list);
      }

      const content = list.querySelector(".results-content");
      if (content) {
        const observer = new MutationObserver(() => {
          scheduleMeasure(0);
        });
        observer.observe(content, {
          childList: true,
          subtree: true,
          attributes: true,
        });
      }

      document.addEventListener(
        "click",
        (event) => {
          const target = event.target;
          if (!(target instanceof Element)) return;
          if (!target.closest(".pagination,.pager-button,.page-number")) return;
          scheduleMeasure(40);
          scheduleMeasure(180);
        },
        true
      );
    });
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

  function ensureUpdateInfoFooterLink() {
    const footerLinks = document.querySelector(".footer-links");
    if (!footerLinks) return;
    if (footerLinks.querySelector('a[href="/update-info.html"]')) return;

    const link = document.createElement("a");
    link.href = "/update-info.html";
    link.textContent = "アップデート情報";
    link.rel = "noreferrer";
    footerLinks.appendChild(link);
  }

  function installFooterLinkWatcher() {
    if (document.body?.dataset.updateInfoFooterWatchBound === "1") return;
    if (!document.body) return;
    document.body.dataset.updateInfoFooterWatchBound = "1";
    ensureUpdateInfoFooterLink();
    const observer = new MutationObserver(() => {
      ensureUpdateInfoFooterLink();
    });
    observer.observe(document.body, {
      childList: true,
      subtree: true,
    });
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

  function bindManualRouteHandlers() {
    if (!document.body || document.body.dataset.manualRouteBound === "1") return;
    document.body.dataset.manualRouteBound = "1";

    window.addEventListener("hashchange", () => {
      handleRouteChange().catch((error) => console.error(error));
    });

    document.addEventListener(
      "keydown",
      (event) => {
        if (event.key !== "Escape") return;
        if (!isManualRouteHash()) return;
        event.preventDefault();
        closeManualRoute();
      },
      true
    );

    handleRouteChange().catch((error) => console.error(error));
  }

  function initSnapshotCore() {
    if (snapshotCoreInitialized) return;
    snapshotCoreInitialized = true;
    beginSnapshotLoading("boot");
    installFetchInterceptor();
    installSnapshotStateWatchdog();
  }

  initSnapshotCore();

  async function bootstrap() {
    await loadBootstrapData();

    waitForElement(".search-left", () => {
      ensureCoverageBadge();
    });

    waitForElement(".jp-map-geo", () => {
      installSnapshotStateUi();
      installMapDragThreshold();
    });

    waitForElement(".footer-links", () => {
      ensureUpdateInfoFooterLink();
      installFooterLinkWatcher();
    });

    installResultsListHeightLock();
    bindSheetHydrationTriggers();
    bindManualRouteHandlers();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", bootstrap, { once: true });
  } else {
    bootstrap();
  }
})();
