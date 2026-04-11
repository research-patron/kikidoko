(() => {
  const FIRESTORE_PROJECT_ID = "kikidoko";
  const FIRESTORE_API_KEY = "AIzaSyBrVNGOTueD6p5RNvsXiggisbETuTrNKbQ";

  const PATH_BOOTSTRAP = "/data/bootstrap-v1.json";
  const PATH_SNAPSHOT_LITE = "/data/equipment_snapshot_lite-v1.json";
  const PATH_BLOG_ARTICLES = "/blog/articles.json";
  const PATH_POPULAR_EQUIPMENT = "/data/home_modules/popular-equipment-v1.json";
  const PATH_SNAPSHOT_FULL_GZIP = "/equipment_snapshot.json.gz";
  const PATH_SNAPSHOT_FULL_JSON = "/equipment_snapshot.json";
  const PATH_SIMPLIFIED_GEO = "/data/japan-prefectures-simplified.geojson";
  const PATH_DETAIL_DIR = "/data/equipment_detail_shards";
  const POPULARITY_COLLECTION = "equipment_view_events";
  const POPULARITY_RATE_LIMIT_MS = 6 * 60 * 60 * 1000;
  const SNAPSHOT_STATE_KEY = "__kikidokoSnapshotState";
  const MAP_DEBUG_KEY = "__kikidokoMapDebug";
  const SNAPSHOT_TIMEOUT_MS = 10000;
  const MAP_FALLBACK_DELAY_MS = 320;
  const MAP_FALLBACK_MONITOR_MS = 2400;

  const REQUEST_FP_KEY = "kikidoko:feature_request:fingerprint";
  const HOME_DISCLOSURE_KEY = "kikidoko:home:advanced-open";
  const HOME_DISCLOSURE_EXPANDED_KEY = "kikidoko:home:advanced-expanded";
  const HOME_DISCLOSURE_PANEL_ANIM_MS = 280;
  const HOME_DISCLOSURE_SHOW_SCROLL_THRESHOLD = 12;
  const HOME_DISCLOSURE_HIDE_SCROLL_THRESHOLD = 56;
  const HOME_LOCATION_PREFERENCE_KEY = "kikidoko:home:location-preference";
  const HOME_LOCATION_READY_KEY = "kikidoko:home:location-ready";
  const HOME_KEYWORD_PLACEHOLDER_DEFAULT = "設備名・略称・機関名で検索";
  const HOME_KEYWORD_PLACEHOLDER_INSTITUTION = "機関名で検索（例: 東北大学、産総研）";
  const HOME_SEARCH_HELPER_DEFAULT = "設備名・測定手法・略称で検索できます";
  const HOME_POPULAR_CUE_KEY = "kikidoko:home:popular-cue-dismissed";
  const POPULARITY_EVENT_KEY_PREFIX = "kikidoko:popularity-event";
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
  let snapshotLiteDataPromise = null;
  let snapshotLiteById = null;
  let blogArticlesPromise = null;
  let popularFeedPromise = null;
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
  let snapshotWatchdogTimer = null;
  let snapshotCoreInitialized = false;
  let mapFallbackIndexByPrefecture = new Map();
  let mapFallbackIndexReady = false;
  let mapFallbackProbeTimer = null;
  let lastNonRouteHash = "";
  let routeRenderToken = 0;
  let resultRowAnnotationTimer = null;
  let homeStructureSyncTimer = null;
  let homeDisclosureScrollRaf = null;
  let homeDisclosurePanelTimer = null;
  let homeDisclosurePanelOpenRaf = null;
  let homeDisclosureLastScrollTop = 0;
  let homeDisclosureScrollIntent = "";
  let homeDisclosureRevealRequiresUp = false;
  let homeDisclosureForceVisible = false;
  let homeDisclosureIntentLockUntil = 0;
  let homeSheetVisibilityRaf = null;
  let homeSearchFabVisibilityRaf = null;
  let homeSearchSheetScrollY = 0;
  let allowNextHomeSearchClick = false;
  let pendingHomeLocationRequest = null;
  let homeLocationPromptResolver = null;
  let popularEquipmentSheetToken = 0;

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

    snapshotLiteLookupPromise = originalFetch(appendAssetVersion(PATH_SNAPSHOT_LITE))
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

  async function loadSnapshotLiteData() {
    if (snapshotLiteDataPromise) return snapshotLiteDataPromise;

    snapshotLiteDataPromise = originalFetch(appendAssetVersion(PATH_SNAPSHOT_LITE))
      .then((res) => {
        if (!res.ok) {
          throw new Error(`snapshot_lite_fetch_failed:${res.status}`);
        }
        return res.json();
      })
      .then((payload) => {
        const rows = Array.isArray(payload?.items) ? payload.items : [];
        const byId = new Map();
        rows.forEach((entry) => {
          resolveEntryIds(entry).forEach((id) => {
            if (!id || byId.has(id)) return;
            byId.set(id, entry);
          });
        });
        snapshotLiteById = byId;
        return {
          items: rows,
          byId,
        };
      })
      .catch((error) => {
        snapshotLiteDataPromise = null;
        throw error;
      });

    return snapshotLiteDataPromise;
  }

  async function loadBlogArticles() {
    if (blogArticlesPromise) return blogArticlesPromise;
    blogArticlesPromise = originalFetch(appendAssetVersion(PATH_BLOG_ARTICLES))
      .then((res) => {
        if (!res.ok) {
          throw new Error(`blog_articles_fetch_failed:${res.status}`);
        }
        return res.json();
      })
      .catch((error) => {
        blogArticlesPromise = null;
        throw error;
      });
    return blogArticlesPromise;
  }

  function normalizeArticleExcerptText(text) {
    return String(text || "").replace(/\s+/g, " ").trim();
  }

  function clampArticleExcerpt(text, maxChars = 96) {
    const normalized = String(text || "").replace(/\s+/g, " ").trim();
    if (!normalized) return "";
    if (normalized.length <= maxChars) return normalized;
    return `${normalized.slice(0, Math.max(0, maxChars - 1)).trimEnd()}…`;
  }

  async function loadArticleExcerpt(article) {
    return clampArticleExcerpt(
      article?.meta_description || article?.metaDescription || article?.excerpt || article?.description || ""
    );
  }

  async function loadPopularFeed() {
    if (popularFeedPromise) return popularFeedPromise;
    popularFeedPromise = originalFetch(appendAssetVersion(PATH_POPULAR_EQUIPMENT))
      .then((res) => {
        if (!res.ok) {
          throw new Error(`popular_feed_fetch_failed:${res.status}`);
        }
        return res.json();
      })
      .catch((error) => {
        popularFeedPromise = null;
        throw error;
      });
    return popularFeedPromise;
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
    const promise = originalFetch(requestUrl)
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
    const panel =
      document.querySelector(".home-popular-sheet.is-open .equipment-sheet-panel") ||
      document.querySelector(".equipment-sheet.is-open .equipment-sheet-panel");
    if (!panel) return null;

    const nameEl = panel.querySelector(".equipment-sheet-name");
    const metaEl = panel.querySelector(".equipment-sheet-meta");
    const name = String(nameEl?.textContent || "").trim();
    const meta = String(metaEl?.textContent || "").trim();
    if (!name) return null;
    const parsed = extractPrefectureAndOrg(meta);
    const signature = detailSignature(name, parsed.prefecture, parsed.orgName);
    const ids = [];
    const directEquipmentId = String(panel.dataset.equipmentId || "").trim();
    const directDocId = String(panel.dataset.detailDocId || "").trim();
    if (directEquipmentId) ids.push(directEquipmentId);
    if (directDocId && !ids.includes(directDocId)) ids.push(directDocId);
    if (!ids.length) {
      resolveEquipmentIds(name, parsed.prefecture, parsed.orgName).forEach((id) => {
        if (!ids.includes(id)) ids.push(id);
      });
    }

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

    bootstrapDataPromise = originalFetch(appendAssetVersion(PATH_BOOTSTRAP))
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
    if (isHomeRefreshEligible()) {
      syncHomeFooterCoverageStat();
      return;
    }

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

  function getHomeCoverageText() {
    const count = toNumber(bootstrapData?.coverage_count || 0);
    return count > 0 ? `網羅機器数: ${formatCount(count)}件` : "網羅機器数: 読み込み中...";
  }

  function syncHomeFooterCoverageStat() {
    const stat = document.querySelector(".home-footer-coverage");
    if (!(stat instanceof HTMLElement)) return;
    const count = toNumber(bootstrapData?.coverage_count || 0);
    stat.textContent = getHomeCoverageText();
    stat.dataset.ready = count > 0 ? "1" : "0";
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

  function removeLegacyFeatureSection() {
    document.getElementById("feature-feedback-section")?.remove();
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

  function isHomeRefreshEligible() {
    return Boolean(
      document.querySelector(".hero") &&
        document.querySelector(".search-panel") &&
        document.querySelector(".results-body") &&
        document.querySelector(".footer")
    );
  }

  function cleanEquipmentName(value) {
    const raw = String(value || "").trim();
    if (!raw) return "";
    if (raw.startsWith('"') && raw.endsWith('"') && raw.length >= 2) {
      return raw.slice(1, -1).trim();
    }
    return raw;
  }

  function normalizeHomeUrl(url) {
    const raw = String(url || "").trim();
    if (!raw) return "";
    try {
      return new URL(raw, window.location.origin).toString();
    } catch {
      return raw;
    }
  }

  function getStickyHeaderHeight() {
    return 0;
  }

  function scrollToHomeSection(target) {
    const el = typeof target === "string" ? document.getElementById(target) : target;
    if (!(el instanceof Element)) return;
    const top = window.scrollY + el.getBoundingClientRect().top - getStickyHeaderHeight() - 16;
    window.scrollTo({ top: Math.max(top, 0), behavior: "smooth" });
  }

  function focusElementSoon(el) {
    if (!(el instanceof HTMLElement)) return;
    window.setTimeout(() => {
      try {
        el.focus({ preventScroll: true });
      } catch {
        el.focus();
      }
    }, 140);
  }

  function isHomeSearchOptionsElement(node) {
    return node instanceof HTMLElement && node.matches(".search-options");
  }

  function isHomeSearchOptionsCandidate(node) {
    if (!isHomeSearchOptionsElement(node)) return false;
    return (
      node.querySelector("#region") instanceof HTMLSelectElement ||
      node.querySelector("#category") instanceof HTMLSelectElement ||
      node.querySelector(".filter select") instanceof HTMLSelectElement ||
      node.querySelector(".filter input") instanceof HTMLInputElement
    );
  }

  function getHomeSearchElements() {
    const hero = document.querySelector(".hero.home-sticky-bar") || document.querySelector(".hero");
    const heroShell = hero?.querySelector(".hero-shell");
    const mainRow = heroShell?.querySelector(".home-header-main-row");
    const searchPanel = hero?.querySelector(".search-panel");
    if (!(searchPanel instanceof HTMLElement)) {
      return {
        hero: null,
        heroShell: null,
        mainRow: null,
        searchPanel: null,
        searchMain: null,
        searchActions: null,
        searchButtons: null,
        searchLeft: null,
        searchRight: null,
        searchOptions: null,
        searchButton: null,
        resetButton: null,
        locationButton: null,
        locationNote: null,
        searchInput: null,
      };
    }

    const searchMain = searchPanel.querySelector(".search-main");
    const searchActions = searchPanel.querySelector(".search-actions");
    const searchButtons = searchPanel.querySelector(".search-buttons");
    const searchLeft = searchPanel.querySelector(".search-left");
    const searchRight = searchPanel.querySelector(".search-right");
    const directSearchOptions = searchPanel.querySelector(":scope > .search-options");
    const searchOptions = isHomeSearchOptionsCandidate(directSearchOptions)
      ? directSearchOptions
      : Array.from(searchPanel.children).find((child) => isHomeSearchOptionsCandidate(child)) || null;
    const searchButton =
      searchPanel.querySelector('[data-home-search-submit="1"]') ||
      searchPanel.querySelector(".search-main .primary") ||
      searchPanel.querySelector(".search-right .primary") ||
      searchPanel.querySelector(".primary");
    const locationButton =
      searchPanel.querySelector(".location-button") || searchOptions?.querySelector(".location-button");
    const locationNote =
      searchPanel.querySelector(".location-note") || searchOptions?.querySelector(".location-note");
    const searchInput = searchPanel.querySelector(".search-main input");
    const resetButton =
      searchPanel.querySelector('[data-home-advanced-reset]') ||
      Array.from(searchPanel.querySelectorAll("button.ghost")).find(
        (button) =>
          !button.classList.contains("location-button") &&
          !button.classList.contains("home-search-shortcut") &&
          !button.classList.contains("home-advanced-close")
      ) ||
      null;

    return {
      hero: hero instanceof HTMLElement ? hero : null,
      heroShell: heroShell instanceof HTMLElement ? heroShell : null,
      mainRow: mainRow instanceof HTMLElement ? mainRow : null,
      searchPanel,
      searchMain: searchMain instanceof HTMLElement ? searchMain : null,
      searchActions: searchActions instanceof HTMLElement ? searchActions : null,
      searchButtons: searchButtons instanceof HTMLElement ? searchButtons : null,
      searchLeft: searchLeft instanceof HTMLElement ? searchLeft : null,
      searchRight: searchRight instanceof HTMLElement ? searchRight : null,
      searchOptions: searchOptions instanceof HTMLElement ? searchOptions : null,
      searchButton: searchButton instanceof HTMLButtonElement ? searchButton : null,
      resetButton: resetButton instanceof HTMLButtonElement ? resetButton : null,
      locationButton: locationButton instanceof HTMLButtonElement ? locationButton : null,
      locationNote: locationNote instanceof HTMLElement ? locationNote : null,
      searchInput: searchInput instanceof HTMLInputElement ? searchInput : null,
    };
  }

  function getHomeSearchFilterBlocks(searchOptions) {
    if (!(searchOptions instanceof HTMLElement)) {
      return {
        regionFilter: null,
        categoryFilter: null,
        filterInline: null,
      };
    }
    const filters = Array.from(searchOptions.querySelectorAll(":scope > .filter")).filter(
      (node) => node instanceof HTMLElement
    );
    const regionFilter =
      filters.find((filter) => filter.querySelector("#region") instanceof HTMLSelectElement) || null;
    const categoryFilter =
      filters.find((filter) => filter.querySelector("#category") instanceof HTMLSelectElement) || null;
    const filterInline = searchOptions.querySelector(".filter-inline");
    return {
      regionFilter: regionFilter instanceof HTMLElement ? regionFilter : null,
      categoryFilter: categoryFilter instanceof HTMLElement ? categoryFilter : null,
      filterInline: filterInline instanceof HTMLElement ? filterInline : null,
    };
  }

  function isHomeCompactSearchMode() {
    return window.matchMedia("(max-width: 639px)").matches;
  }

  function ensureHomeSearchHelper(searchMain) {
    if (!(searchMain instanceof HTMLElement)) return null;
    searchMain.querySelectorAll(".home-search-helper").forEach((node) => node.remove());
    return null;
  }

  function ensureHomeSearchShortcutButtons(searchLeft) {
    if (!(searchLeft instanceof HTMLElement)) return null;
    searchLeft.querySelectorAll(".home-search-shortcuts").forEach((node) => node.remove());
    return null;
  }

  function ensureHomeRegionActionMount(regionFilter) {
    if (!(regionFilter instanceof HTMLElement)) return null;
    let mount = regionFilter.querySelector(".home-region-actions");
    if (!(mount instanceof HTMLElement)) {
      mount = document.createElement("div");
      mount.className = "home-region-actions";
      regionFilter.appendChild(mount);
    }
    return mount;
  }

  function ensureHomeLocationToggle(filterInline) {
    if (!(filterInline instanceof HTMLElement)) return null;
    let toggle = filterInline.querySelector(".toggle.home-location-toggle");
    if (!(toggle instanceof HTMLLabelElement)) {
      toggle = document.createElement("label");
      toggle.className = "toggle home-location-toggle";
      toggle.innerHTML = `
        <input type="checkbox" data-home-location-toggle="1" />
        <span>現在地を使う</span>
      `;
      filterInline.insertBefore(toggle, filterInline.firstElementChild);
    }
    const input = toggle.querySelector('input[data-home-location-toggle="1"]');
    return input instanceof HTMLInputElement ? input : null;
  }

  function applyHomeConditionRowPresentation(filterInline, resetButton) {
    if (!(filterInline instanceof HTMLElement)) return;
    const compactGrid = window.matchMedia("(max-width: 639px)").matches;
    filterInline.style.setProperty("grid-column", "1 / -1");
    filterInline.style.setProperty("display", compactGrid ? "grid" : "flex", "important");
    filterInline.style.setProperty(
      "grid-template-columns",
      compactGrid ? "repeat(2, minmax(0, 1fr))" : "none"
    );
    filterInline.style.setProperty("flex-direction", "row");
    filterInline.style.setProperty("flex-wrap", compactGrid ? "wrap" : "nowrap");
    filterInline.style.setProperty("align-items", compactGrid ? "start" : "center");
    filterInline.style.setProperty("justify-content", "flex-start");
    filterInline.style.setProperty("gap", compactGrid ? "12px 16px" : "12px 22px");
    filterInline.style.setProperty("width", "100%");
    filterInline.style.setProperty("margin-top", "0");
    filterInline.style.setProperty("padding-top", "2px");

    Array.from(filterInline.querySelectorAll(".toggle")).forEach((node) => {
      if (!(node instanceof HTMLLabelElement)) return;
      node.style.setProperty("display", "inline-flex", "important");
      node.style.setProperty("align-items", "center");
      node.style.setProperty("gap", "10px");
      node.style.setProperty("cursor", "pointer");
      node.style.setProperty("width", "auto", "important");
      node.style.setProperty("min-height", "0");
      node.style.setProperty("padding", "0", "important");
      node.style.setProperty("border", "0", "important");
      node.style.setProperty("border-radius", "0", "important");
      node.style.setProperty("background", "transparent", "important");
      node.style.setProperty("box-shadow", "none", "important");
      node.style.setProperty("justify-self", compactGrid ? "start" : "auto");
      const input = node.querySelector("input");
      if (input instanceof HTMLInputElement) {
        input.style.setProperty("width", "20px");
        input.style.setProperty("height", "20px");
        input.style.setProperty("margin", "0");
      }
      const copy = node.querySelector("span");
      if (copy instanceof HTMLElement) {
        copy.style.setProperty("font-weight", "400", "important");
        copy.style.setProperty("letter-spacing", "0");
      }
    });

    if (resetButton instanceof HTMLButtonElement) {
      resetButton.style.setProperty("display", "inline-flex", "important");
      resetButton.style.setProperty("align-items", "center");
      resetButton.style.setProperty("justify-content", "center");
      resetButton.style.setProperty("margin-left", compactGrid ? "0" : "auto", "important");
      resetButton.style.setProperty("justify-self", compactGrid ? "start" : "auto");
      resetButton.style.setProperty("width", "auto", "important");
      resetButton.style.setProperty("white-space", "nowrap");
    }
  }

  async function handleHomeLocationToggleIntent(toggle) {
    if (!(toggle instanceof HTMLInputElement)) return;
    if (!toggle.checked) {
      setHomeLocationPreference("0");
      updateSearchDisclosureState();
      return;
    }
    toggle.disabled = true;
    const resolved = await requestHomeLocationFromQuickButton({ alreadyTriggered: false }).catch(() => false);
    toggle.disabled = false;
    if (!resolved) {
      toggle.checked = false;
      setHomeLocationPreference("0");
    } else {
      toggle.checked = true;
      setHomeLocationPreference("1");
    }
    updateSearchDisclosureState();
  }

  function ensureHomeMobilePrimaryRegionSlot(searchPanel, searchMain) {
    if (!(searchPanel instanceof HTMLElement) || !(searchMain instanceof HTMLElement)) return null;
    let slot = searchPanel.querySelector(".home-mobile-primary-region");
    if (!(slot instanceof HTMLElement)) {
      slot = document.createElement("div");
      slot.className = "home-mobile-primary-region";
      searchMain.insertAdjacentElement("afterend", slot);
    } else if (slot.previousElementSibling !== searchMain) {
      searchMain.insertAdjacentElement("afterend", slot);
    }
    return slot;
  }

  function syncHomeSearchActionPlacement() {
    const {
      searchPanel,
      searchMain,
      searchActions,
      searchButtons,
      searchLeft,
      searchRight,
      searchButton,
      resetButton,
      searchOptions,
      searchInput,
    } = getHomeSearchElements();
    if (
      !(searchPanel instanceof HTMLElement) ||
      !(searchMain instanceof HTMLElement) ||
      !(searchActions instanceof HTMLElement) ||
      !(searchButtons instanceof HTMLElement) ||
      !(searchLeft instanceof HTMLElement) ||
      !(searchRight instanceof HTMLElement) ||
      !(searchOptions instanceof HTMLElement)
    ) {
      return;
    }

    const { regionFilter, categoryFilter, filterInline } = getHomeSearchFilterBlocks(searchOptions);
    const helper = ensureHomeSearchHelper(searchMain);
    ensureHomeSearchShortcutButtons(searchLeft);
    const mobileRegionSlot = ensureHomeMobilePrimaryRegionSlot(searchPanel, searchMain);
    let activeRegionFilter = regionFilter;
    if (!(activeRegionFilter instanceof HTMLElement) && mobileRegionSlot instanceof HTMLElement) {
      const slottedRegionFilter = Array.from(mobileRegionSlot.children).find((node) => {
        return node instanceof HTMLElement && node.querySelector("#region") instanceof HTMLSelectElement;
      });
      if (slottedRegionFilter instanceof HTMLElement) {
        activeRegionFilter = slottedRegionFilter;
      }
    }
    const utility = searchOptions.querySelector(".home-advanced-utility");
    const actionRow =
      utility instanceof HTMLElement ? utility.querySelector(".home-advanced-actions") : null;
    const closeButton =
      actionRow instanceof HTMLElement ? actionRow.querySelector(".home-advanced-close") : null;
    const disclosure = searchPanel.querySelector(".search-disclosure");
    const disclosureLabel =
      disclosure instanceof HTMLElement ? disclosure.querySelector(".search-disclosure-label") : null;
    const mobileCloseRow =
      searchActions instanceof HTMLElement ? searchActions.querySelector(".home-search-mobile-close-row") : null;
    const sheetOpen = isHomeSearchSheetOpen();
    const compactMode = !sheetOpen && isHomeCompactSearchMode();

    if (searchInput instanceof HTMLInputElement) {
      searchInput.dataset.defaultPlaceholder = HOME_KEYWORD_PLACEHOLDER_DEFAULT;
      if (searchInput.dataset.searchInstitutionHint !== "1") {
        searchInput.placeholder = HOME_KEYWORD_PLACEHOLDER_DEFAULT;
      }
    }

    if (searchButton instanceof HTMLButtonElement) {
      searchButton.dataset.homeSearchSubmit = "1";
    }

    if (disclosureLabel instanceof HTMLElement) {
      disclosureLabel.textContent = compactMode ? "絞り込み" : "詳細設定";
    }

    if (filterInline instanceof HTMLElement) {
      const locationToggle = ensureHomeLocationToggle(filterInline);
      if (locationToggle instanceof HTMLInputElement) {
        locationToggle.checked = getHomeLocationPreference() === "1";
        if (locationToggle.dataset.bound !== "1") {
          locationToggle.dataset.bound = "1";
          locationToggle.addEventListener("change", () => {
            handleHomeLocationToggleIntent(locationToggle).catch((error) => console.error(error));
          });
        }
      }
      const toggleLabels = Array.from(filterInline.querySelectorAll(".toggle")).filter(
        (node) => node instanceof HTMLElement
      );
      const locationLabel =
        toggleLabels.find((label) => label.classList.contains("home-location-toggle")) || null;
      const externalLabel =
        toggleLabels.find((label) => String(label.textContent || "").includes("学外利用可")) || null;
      const freeLabel =
        toggleLabels.find((label) => String(label.textContent || "").includes("無料設備")) || null;
      if (
        locationLabel instanceof HTMLElement &&
        filterInline.firstElementChild !== locationLabel
      ) {
        filterInline.insertBefore(locationLabel, filterInline.firstElementChild);
      }
      if (
        externalLabel instanceof HTMLElement &&
        freeLabel instanceof HTMLElement &&
        externalLabel.compareDocumentPosition(freeLabel) & Node.DOCUMENT_POSITION_PRECEDING
      ) {
        filterInline.insertBefore(externalLabel, freeLabel);
      }
      if (resetButton instanceof HTMLButtonElement) {
        resetButton.dataset.homeAdvancedReset = "1";
        resetButton.classList.add("home-inline-reset");
        if (resetButton.parentElement !== filterInline) {
          filterInline.appendChild(resetButton);
        } else {
          filterInline.appendChild(resetButton);
        }
      }
      applyHomeConditionRowPresentation(filterInline, resetButton);
    }

    if (compactMode) {
      if (
        activeRegionFilter instanceof HTMLElement &&
        mobileRegionSlot instanceof HTMLElement &&
        activeRegionFilter.parentElement !== mobileRegionSlot
      ) {
        mobileRegionSlot.appendChild(activeRegionFilter);
      }
      if (disclosure instanceof HTMLElement) {
        disclosure.hidden = true;
        disclosure.style.setProperty("display", "none", "important");
      }
      if (closeButton instanceof HTMLButtonElement) {
        closeButton.hidden = true;
      }
      if (mobileCloseRow instanceof HTMLElement) {
        if (
          closeButton instanceof HTMLButtonElement &&
          actionRow instanceof HTMLElement &&
          closeButton.parentElement === mobileCloseRow
        ) {
          actionRow.appendChild(closeButton);
        }
        mobileCloseRow.remove();
      }
      if (resetButton instanceof HTMLButtonElement && resetButton.parentElement !== searchLeft) {
        searchLeft.replaceChildren(resetButton);
      }
      if (searchButton instanceof HTMLButtonElement && searchButton.parentElement !== searchRight) {
        searchRight.replaceChildren(searchButton);
        searchRight.appendChild(searchButton);
      }
      searchButtons.replaceChildren(searchLeft, searchRight);
      searchActions.replaceChildren(searchButtons);
      if (resetButton instanceof HTMLButtonElement) {
        resetButton.style.setProperty("display", "inline-flex", "important");
        resetButton.style.setProperty("align-items", "center");
        resetButton.style.setProperty("justify-content", "center");
        resetButton.style.setProperty("margin", "0", "important");
      }
      if (searchButton instanceof HTMLButtonElement) {
        searchButton.style.setProperty("display", "inline-flex", "important");
        searchButton.style.setProperty("align-items", "center");
        searchButton.style.setProperty("justify-content", "center");
        searchButton.style.setProperty("margin", "0", "important");
      }
      searchActions.hidden = false;
      return;
    }

    if (mobileCloseRow instanceof HTMLElement) {
      mobileCloseRow.remove();
    }

    if (disclosure instanceof HTMLElement) {
      disclosure.hidden = false;
      disclosure.style.removeProperty("display");
    }
    if (closeButton instanceof HTMLButtonElement) {
      closeButton.hidden = false;
    }
    if (
      closeButton instanceof HTMLButtonElement &&
      actionRow instanceof HTMLElement &&
      closeButton.parentElement !== actionRow
    ) {
      actionRow.appendChild(closeButton);
    }

    if (activeRegionFilter instanceof HTMLElement && activeRegionFilter.parentElement !== searchOptions) {
      searchOptions.insertBefore(
        activeRegionFilter,
        categoryFilter instanceof HTMLElement ? categoryFilter : searchOptions.firstElementChild
      );
    }

    if (
      activeRegionFilter instanceof HTMLElement &&
      categoryFilter instanceof HTMLElement &&
      activeRegionFilter.parentElement === searchOptions &&
      activeRegionFilter.nextElementSibling !== categoryFilter
    ) {
      searchOptions.insertBefore(activeRegionFilter, categoryFilter);
    }

    if (mobileRegionSlot instanceof HTMLElement && !compactMode) {
      mobileRegionSlot.replaceChildren();
    }

    if (disclosure instanceof HTMLElement && disclosure.parentElement !== searchRight) {
      searchRight.appendChild(disclosure);
    }

    if (searchButton instanceof HTMLButtonElement) {
      const anchor = helper instanceof HTMLElement ? helper : null;
      if (searchButton.parentElement !== searchMain || (anchor && searchButton.nextElementSibling !== anchor)) {
        searchMain.insertBefore(searchButton, anchor);
      }
    }

    searchActions.hidden = !sheetOpen && !compactMode;
  }

  function syncHomeLocationPreferenceToggle() {
    const { searchOptions } = getHomeSearchElements();
    if (!(searchOptions instanceof HTMLElement)) return;
    searchOptions.querySelectorAll(".home-location-preference-toggle").forEach((node) => node.remove());
    const toggle = searchOptions.querySelector('input[data-home-location-toggle="1"]');
    if (toggle instanceof HTMLInputElement) {
      toggle.checked = getHomeLocationPreference() === "1";
    }
  }

  function isHomeSearchSheetOpen() {
    return document.body?.dataset.homeSearchSheetOpen === "1";
  }

  function getHomeSearchSheetParts() {
    const { hero, heroShell, searchPanel, searchButton } = getHomeSearchElements();
    const placeholder = document.querySelector(".home-search-sheet-placeholder");
    const backdrop = document.querySelector(".home-search-sheet-backdrop");
    const closeButton = heroShell?.querySelector(".home-search-sheet-close");
    const input = hero?.querySelector(".search-main input");
    return {
      hero: hero instanceof HTMLElement ? hero : null,
      heroShell: heroShell instanceof HTMLElement ? heroShell : null,
      searchPanel: searchPanel instanceof HTMLElement ? searchPanel : null,
      searchButton: searchButton instanceof HTMLButtonElement ? searchButton : null,
      placeholder: placeholder instanceof HTMLElement ? placeholder : null,
      backdrop: backdrop instanceof HTMLElement ? backdrop : null,
      closeButton: closeButton instanceof HTMLButtonElement ? closeButton : null,
      input: input instanceof HTMLInputElement ? input : null,
    };
  }

  function ensureHomeSearchSheetChrome() {
    const { hero, heroShell } = getHomeSearchElements();
    if (!(hero instanceof HTMLElement) || !(heroShell instanceof HTMLElement) || !(document.body instanceof HTMLElement)) {
      return getHomeSearchSheetParts();
    }

    let placeholder = hero.nextElementSibling;
    if (!(placeholder instanceof HTMLElement) || !placeholder.classList.contains("home-search-sheet-placeholder")) {
      placeholder = document.createElement("div");
      placeholder.className = "home-search-sheet-placeholder";
      placeholder.hidden = true;
      hero.insertAdjacentElement("afterend", placeholder);
    }

    let backdrop = document.querySelector(".home-search-sheet-backdrop");
    if (!(backdrop instanceof HTMLElement)) {
      backdrop = document.createElement("button");
      backdrop.type = "button";
      backdrop.className = "home-search-sheet-backdrop";
      backdrop.hidden = true;
      backdrop.setAttribute("aria-label", "検索シートを閉じる");
      document.body.appendChild(backdrop);
    }

    let fab = document.querySelector(".home-search-fab");
    if (!(fab instanceof HTMLButtonElement)) {
      fab = document.createElement("button");
      fab.type = "button";
      fab.className = "home-search-fab";
      fab.hidden = true;
      fab.setAttribute("aria-label", "検索を開く");
      fab.innerHTML = `
        <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
          <path d="M10.5 4a6.5 6.5 0 1 1 0 13a6.5 6.5 0 0 1 0-13Zm0 2a4.5 4.5 0 1 0 0 9a4.5 4.5 0 0 0 0-9Zm7.4 10.98 2.62 2.61-1.42 1.42-2.61-2.62 1.41-1.41Z"></path>
        </svg>
      `;
      document.body.appendChild(fab);
    }

    let closeButton = heroShell.querySelector(".home-search-sheet-close");
    if (!(closeButton instanceof HTMLButtonElement)) {
      closeButton = document.createElement("button");
      closeButton.type = "button";
      closeButton.className = "home-search-sheet-close";
      closeButton.textContent = "閉じる";
    }

    const titleRow = heroShell.querySelector(".hero-copy .title-row");
    if (titleRow instanceof HTMLElement) {
      if (closeButton.parentElement !== titleRow) {
        titleRow.appendChild(closeButton);
      }
    } else if (closeButton.parentElement !== heroShell) {
      heroShell.appendChild(closeButton);
    }

    return getHomeSearchSheetParts();
  }

  function applyHomeSearchSheetState(nextOpen) {
    if (document.body instanceof HTMLElement) {
      if (nextOpen) {
        document.body.dataset.homeSearchSheetOpen = "1";
      } else {
        delete document.body.dataset.homeSearchSheetOpen;
      }
    }
    const { hero, heroShell, mainRow, searchPanel } = getHomeSearchElements();
    const value = nextOpen ? "1" : "0";
    [hero, heroShell, mainRow, searchPanel].forEach((node) => {
      if (node instanceof HTMLElement) {
        node.dataset.searchSheetOpen = value;
      }
    });
  }

  function syncHomeSearchSheetPlaceholder() {
    const { hero, placeholder, backdrop } = ensureHomeSearchSheetChrome();
    if (!(placeholder instanceof HTMLElement) || !(backdrop instanceof HTMLElement)) return;
    if (!isHomeSearchSheetOpen() || !(hero instanceof HTMLElement)) {
      placeholder.hidden = true;
      placeholder.style.height = "0px";
      delete placeholder.dataset.sheetHeight;
      backdrop.hidden = true;
      return;
    }
    const cachedHeight = Number.parseFloat(placeholder.dataset.sheetHeight || "0");
    const nextHeight = cachedHeight > 0 ? cachedHeight : Math.ceil(hero.getBoundingClientRect().height || 0);
    placeholder.hidden = false;
    placeholder.style.height = `${Math.max(nextHeight, 1)}px`;
    backdrop.hidden = false;
  }

  function syncHomeSearchFabVisibility() {
    const { hero } = ensureHomeSearchSheetChrome();
    const fab = document.querySelector(".home-search-fab");
    if (!(fab instanceof HTMLButtonElement)) return;
    const equipmentSheetOpen = document.querySelector(".equipment-sheet.is-open:not(.home-popular-sheet)") instanceof HTMLElement;
    const popularSheetOpen = document.querySelector(".home-popular-sheet.is-open") instanceof HTMLElement;
    const eqnetAssistOpen = document.querySelector(".eqnet-assist-panel") instanceof HTMLElement;
    const sheetOpen = equipmentSheetOpen || popularSheetOpen || eqnetAssistOpen || isHomeSearchSheetOpen();
    const heroOutOfView =
      hero instanceof HTMLElement ? hero.getBoundingClientRect().bottom <= 48 : false;
    const shouldShow = isHomeRefreshEligible() && !sheetOpen && heroOutOfView;
    fab.hidden = !shouldShow;
    fab.dataset.visible = shouldShow ? "1" : "0";
    fab.setAttribute("aria-hidden", shouldShow ? "false" : "true");
  }

  function scheduleHomeSearchFabVisibilitySync() {
    if (homeSearchFabVisibilityRaf != null) return;
    homeSearchFabVisibilityRaf = window.requestAnimationFrame(() => {
      homeSearchFabVisibilityRaf = null;
      syncHomeSearchFabVisibility();
      syncHomeSearchSheetPlaceholder();
    });
  }

  function openHomeSearchSheet() {
    const { hero, input, placeholder, backdrop } = ensureHomeSearchSheetChrome();
    if (!(hero instanceof HTMLElement) || !(document.body instanceof HTMLElement)) return;
    if (isHomeSearchSheetOpen()) return;
    if (document.querySelector(".equipment-sheet.is-open") instanceof HTMLElement) return;
    homeSearchSheetScrollY = window.scrollY;
    const nextHeight = Math.ceil(hero.getBoundingClientRect().height || 0);
    if (placeholder instanceof HTMLElement) {
      placeholder.dataset.sheetHeight = `${Math.max(nextHeight, 1)}`;
      placeholder.hidden = false;
      placeholder.style.height = `${Math.max(nextHeight, 1)}px`;
    }
    if (backdrop instanceof HTMLElement) {
      backdrop.hidden = false;
    }
    applyHomeSearchSheetState(true);
    syncHomeSearchActionPlacement();
    updateSearchDisclosureState();
    scheduleHomeStickyHeaderVisibilitySync();
    scheduleHomeSearchFabVisibilitySync();
    if (input instanceof HTMLInputElement) {
      focusElementSoon(input);
    }
  }

  function closeHomeSearchSheet(options = {}) {
    const { restoreScroll = true } = options;
    const { placeholder, backdrop } = ensureHomeSearchSheetChrome();
    if (!(document.body instanceof HTMLElement)) return;
    if (!isHomeSearchSheetOpen()) {
      if (placeholder instanceof HTMLElement) {
        placeholder.hidden = true;
        placeholder.style.height = "0px";
        delete placeholder.dataset.sheetHeight;
      }
      if (backdrop instanceof HTMLElement) backdrop.hidden = true;
      return;
    }
    applyHomeSearchSheetState(false);
    syncHomeSearchActionPlacement();
    if (placeholder instanceof HTMLElement) {
      placeholder.hidden = true;
      placeholder.style.height = "0px";
      delete placeholder.dataset.sheetHeight;
    }
    if (backdrop instanceof HTMLElement) backdrop.hidden = true;
    updateSearchDisclosureState();
    if (restoreScroll) {
      window.requestAnimationFrame(() => {
        window.scrollTo({ top: homeSearchSheetScrollY, left: 0, behavior: "auto" });
      });
    }
    scheduleHomeStickyHeaderVisibilitySync();
    scheduleHomeSearchFabVisibilitySync();
  }

  function getHomeAdvancedFilterControls() {
    const { searchOptions } = getHomeSearchElements();
    const region = document.getElementById("region");
    const category = document.getElementById("category");
    const toggles = Array.from(searchOptions?.querySelectorAll(".filter-inline .toggle input") || []).filter(
      (input) => input instanceof HTMLInputElement
    );
    let externalToggle = null;
    let freeToggle = null;
    const locationToggle = searchOptions?.querySelector('input[data-home-location-toggle="1"]') || null;
    toggles.forEach((toggle) => {
      const label = String(toggle.closest(".toggle")?.textContent || "").trim();
      if (!externalToggle && label.includes("学外利用可")) externalToggle = toggle;
      if (!freeToggle && label.includes("無料設備")) freeToggle = toggle;
    });
    return {
      region: region instanceof HTMLSelectElement ? region : null,
      category: category instanceof HTMLSelectElement ? category : null,
      toggles,
      locationToggle: locationToggle instanceof HTMLInputElement ? locationToggle : null,
      externalToggle,
      freeToggle,
    };
  }

  function getHomeLocationPreference() {
    const raw = window.sessionStorage.getItem(HOME_LOCATION_PREFERENCE_KEY);
    return raw === "1" || raw === "0" ? raw : "";
  }

  function getHomeLocationReadyState() {
    return window.sessionStorage.getItem(HOME_LOCATION_READY_KEY) === "1";
  }

  function setHomeLocationReadyState(nextReady) {
    if (nextReady) {
      window.sessionStorage.setItem(HOME_LOCATION_READY_KEY, "1");
    } else {
      window.sessionStorage.removeItem(HOME_LOCATION_READY_KEY);
    }
  }

  function setHomeLocationPreference(nextValue, options = {}) {
    const { persist = true } = options;
    const normalized = nextValue === "1" || nextValue === "0" ? nextValue : "";
    if (persist) {
      if (normalized) {
        window.sessionStorage.setItem(HOME_LOCATION_PREFERENCE_KEY, normalized);
      } else {
        window.sessionStorage.removeItem(HOME_LOCATION_PREFERENCE_KEY);
      }
    }
    updateSearchDisclosureState();
  }

  function hasReadyHomeLocation() {
    const { locationButton } = getHomeSearchElements();
    if (locationButton instanceof HTMLButtonElement) {
      const label = String(locationButton.textContent || "").trim();
      if (label.includes("更新")) {
        setHomeLocationReadyState(true);
        return true;
      }
    }
    return getHomeLocationReadyState();
  }

  function getHomeDisclosureParts() {
    const { hero, searchPanel, searchOptions } = getHomeSearchElements();
    const root = searchPanel?.querySelector(".search-disclosure") || hero?.querySelector(".search-disclosure");
    const panel = searchOptions;
    return {
      root: root instanceof HTMLElement ? root : null,
      toggle: root instanceof HTMLElement ? root.querySelector(".search-disclosure-toggle") : null,
      panel: panel instanceof HTMLElement ? panel : null,
    };
  }

  function clearHomeDisclosurePanelTimer() {
    if (homeDisclosurePanelTimer == null) return;
    window.clearTimeout(homeDisclosurePanelTimer);
    homeDisclosurePanelTimer = null;
  }

  function clearHomeDisclosurePanelOpenRaf() {
    if (homeDisclosurePanelOpenRaf == null) return;
    window.cancelAnimationFrame(homeDisclosurePanelOpenRaf);
    homeDisclosurePanelOpenRaf = null;
  }

  function lockHomeDisclosureScrollIntent(durationMs = HOME_DISCLOSURE_PANEL_ANIM_MS) {
    homeDisclosureIntentLockUntil = Date.now() + durationMs;
    homeDisclosureLastScrollTop = window.scrollY;
  }

  function updateHomeDisclosureScrollIntent() {
    const nextScrollTop = window.scrollY;
    if (Date.now() < homeDisclosureIntentLockUntil) {
      homeDisclosureLastScrollTop = nextScrollTop;
      return;
    }
    const delta = nextScrollTop - homeDisclosureLastScrollTop;
    if (Math.abs(delta) >= 2) {
      homeDisclosureScrollIntent = delta > 0 ? "down" : "up";
    }
    homeDisclosureLastScrollTop = nextScrollTop;
  }

  function applyHomeDisclosureLayoutState(targets, nextState) {
    const { mainRow, searchPanel, heroShell, root, panel } = targets;
    const isOpen = nextState.open ? "1" : "0";
    const isVisible = nextState.visible ? "1" : "0";
    const isMounted = nextState.mounted ? "1" : "0";
    const state = nextState.state || (nextState.mounted ? "open" : "closed");

    if (panel instanceof HTMLElement) {
      panel.hidden = false;
      panel.removeAttribute("hidden");
      panel.dataset.panelMounted = isMounted;
      panel.dataset.panelState = state;
      panel.setAttribute("aria-hidden", nextState.visible ? "false" : "true");
    }

    if (mainRow instanceof HTMLElement) {
      mainRow.dataset.advancedPanelMounted = isMounted;
      mainRow.dataset.advancedPanelState = state;
    }

    if (searchPanel instanceof HTMLElement) {
      searchPanel.dataset.advancedOpen = isOpen;
      searchPanel.dataset.advancedPanelVisible = isVisible;
      searchPanel.dataset.advancedPanelMounted = isMounted;
      searchPanel.dataset.advancedPanelState = state;
    }

    if (heroShell instanceof HTMLElement) {
      heroShell.dataset.advancedOpen = isOpen;
      heroShell.dataset.advancedPanelVisible = isVisible;
      heroShell.dataset.advancedPanelMounted = isMounted;
      heroShell.dataset.advancedPanelState = state;
    }

    if (root instanceof HTMLElement) {
      root.dataset.open = isOpen;
      root.dataset.panelVisible = isVisible;
      root.dataset.panelMounted = isMounted;
      root.dataset.panelState = state;
    }
  }

  function normalizeHomeDisclosurePanelState(state) {
    return ["closed", "opening", "open", "closing"].includes(state) ? state : "";
  }

  function resolveHomeDisclosureLayoutState(targets) {
    const rootMounted = targets.root?.dataset.panelMounted === "1";
    const searchPanelMounted = targets.searchPanel?.dataset.advancedPanelMounted === "1";
    const heroShellMounted = targets.heroShell?.dataset.advancedPanelMounted === "1";
    const panelMounted = targets.panel?.dataset.panelMounted === "1";
    const mounted = rootMounted || searchPanelMounted || heroShellMounted || panelMounted;

    const open =
      targets.root instanceof HTMLElement
        ? targets.root.dataset.open === "1"
        : targets.searchPanel?.dataset.advancedOpen === "1" || targets.heroShell?.dataset.advancedOpen === "1";

    const visible =
      targets.root instanceof HTMLElement
        ? targets.root.dataset.panelVisible === "1"
        : targets.searchPanel?.dataset.advancedPanelVisible === "1" ||
          targets.heroShell?.dataset.advancedPanelVisible === "1";

    const state =
      normalizeHomeDisclosurePanelState(
        (targets.root instanceof HTMLElement ? targets.root.dataset.panelState : "") ||
          targets.searchPanel?.dataset.advancedPanelState ||
          targets.heroShell?.dataset.advancedPanelState ||
          (panelMounted ? targets.panel?.dataset.panelState : "")
      ) || (mounted ? (visible ? "open" : "closing") : "closed");

    return {
      open,
      visible,
      mounted,
      state,
    };
  }

  function syncHomeDisclosurePanelState(panel, shouldShowPanel, targets) {
    if (!(panel instanceof HTMLElement)) {
      return { mounted: false, state: "closed" };
    }

    const layoutState = resolveHomeDisclosureLayoutState(targets);
    const mounted = layoutState.mounted;
    const currentState = layoutState.state;

    if (!targets.open) {
      homeDisclosureRevealRequiresUp = false;
      homeDisclosureForceVisible = false;
      if (!mounted && currentState === "closed") {
        clearHomeDisclosurePanelTimer();
        clearHomeDisclosurePanelOpenRaf();
        applyHomeDisclosureLayoutState(targets, {
          open: false,
          visible: false,
          mounted: false,
          state: "closed",
        });
        return { mounted: false, state: "closed" };
      }
      if (currentState !== "closing") {
        clearHomeDisclosurePanelOpenRaf();
        lockHomeDisclosureScrollIntent();
        applyHomeDisclosureLayoutState(targets, {
          open: false,
          visible: false,
          mounted: true,
          state: "closing",
        });
      }
      clearHomeDisclosurePanelTimer();
      homeDisclosurePanelTimer = window.setTimeout(() => {
        homeDisclosurePanelTimer = null;
        applyHomeDisclosureLayoutState(targets, {
          open: false,
          visible: false,
          mounted: false,
          state: "closed",
        });
      }, HOME_DISCLOSURE_PANEL_ANIM_MS);
      return { mounted: true, state: "closing" };
    }

    if (!shouldShowPanel) {
      homeDisclosureRevealRequiresUp = true;
      homeDisclosureForceVisible = false;
      if (!mounted && currentState === "closed") {
        clearHomeDisclosurePanelTimer();
        clearHomeDisclosurePanelOpenRaf();
        applyHomeDisclosureLayoutState(targets, {
          open: targets.open,
          visible: false,
          mounted: false,
          state: "closed",
        });
        return { mounted: false, state: "closed" };
      }
      if (currentState !== "closing") {
        clearHomeDisclosurePanelOpenRaf();
        lockHomeDisclosureScrollIntent();
        applyHomeDisclosureLayoutState(targets, {
          open: targets.open,
          visible: false,
          mounted: true,
          state: "closing",
        });
      }
      clearHomeDisclosurePanelTimer();
      homeDisclosurePanelTimer = window.setTimeout(() => {
        homeDisclosurePanelTimer = null;
        applyHomeDisclosureLayoutState(targets, {
          open: targets.open,
          visible: false,
          mounted: false,
          state: "closed",
        });
      }, HOME_DISCLOSURE_PANEL_ANIM_MS);
      return { mounted: true, state: "closing" };
    }

    clearHomeDisclosurePanelTimer();
    clearHomeDisclosurePanelOpenRaf();
    panel.hidden = false;
    panel.removeAttribute("hidden");
    homeDisclosureForceVisible = false;

    if (mounted && currentState === "open") {
      homeDisclosureRevealRequiresUp = false;
      applyHomeDisclosureLayoutState(targets, {
        open: targets.open,
        visible: true,
        mounted: true,
        state: "open",
      });
      return { mounted: true, state: "open" };
    }

    if (mounted && currentState === "opening") {
      homeDisclosureRevealRequiresUp = false;
      applyHomeDisclosureLayoutState(targets, {
        open: targets.open,
        visible: true,
        mounted: true,
        state: "opening",
      });
      return { mounted: true, state: "opening" };
    }

    homeDisclosureRevealRequiresUp = false;
    lockHomeDisclosureScrollIntent();

    applyHomeDisclosureLayoutState(targets, {
      open: targets.open,
      visible: true,
      mounted: true,
      state: "opening",
    });
    homeDisclosurePanelOpenRaf = window.requestAnimationFrame(() => {
      homeDisclosurePanelOpenRaf = null;
      if (panel.dataset.panelMounted !== "1" || panel.dataset.panelState !== "opening") return;
      applyHomeDisclosureLayoutState(targets, {
        open: targets.open,
        visible: true,
        mounted: true,
        state: "open",
      });
    });

    return { mounted: true, state: "opening" };
  }

  function syncHomeStickyHeaderVisibility() {
    const equipmentSheetOpen = document.querySelector(".equipment-sheet.is-open:not(.home-popular-sheet)") instanceof HTMLElement;
    const popularSheetOpen = document.querySelector(".home-popular-sheet.is-open") instanceof HTMLElement;
    const sheetOpen = equipmentSheetOpen || popularSheetOpen || isHomeSearchSheetOpen();
    if (document.body) {
      document.body.dataset.homeSheetOpen = sheetOpen ? "1" : "0";
    }
    const header = document.querySelector(".home-sticky-bar");
    if (header instanceof HTMLElement) {
      header.dataset.sheetOpen = sheetOpen ? "1" : "0";
    }
    scheduleHomeSearchFabVisibilitySync();
  }

  function scheduleHomeStickyHeaderVisibilitySync() {
    if (homeSheetVisibilityRaf != null) return;
    homeSheetVisibilityRaf = window.requestAnimationFrame(() => {
      homeSheetVisibilityRaf = null;
      syncHomeStickyHeaderVisibility();
    });
  }

  function installHomeSheetVisibilityWatcher() {
    if (!document.body || document.body.dataset.homeSheetVisibilityBound === "1") return;
    document.body.dataset.homeSheetVisibilityBound = "1";
    const observer = new MutationObserver(() => {
      scheduleHomeStickyHeaderVisibilitySync();
    });
    observer.observe(document.body, {
      childList: true,
      subtree: true,
      attributes: true,
      attributeFilter: ["class"],
    });
    scheduleHomeStickyHeaderVisibilitySync();
  }

  function isHomeDisclosurePanelVisible(nextOpen = null) {
    if (!isHomeSearchSheetOpen()) {
      return true;
    }
    const { root } = getHomeDisclosureParts();
    const { searchPanel } = getHomeSearchElements();
    const isOpen = typeof nextOpen === "boolean" ? nextOpen : root?.dataset.open === "1";
    if (!isOpen) {
      homeDisclosureRevealRequiresUp = false;
      homeDisclosureForceVisible = false;
      return false;
    }
    const isCurrentlyVisible =
      root?.dataset.panelVisible === "1" ||
      searchPanel?.dataset.advancedPanelVisible === "1" ||
      searchPanel?.dataset.advancedPanelState === "opening" ||
      searchPanel?.dataset.advancedPanelState === "open";
    const scrollTop = window.scrollY;
    if (homeDisclosureForceVisible) {
      return !(homeDisclosureScrollIntent === "down" && scrollTop > HOME_DISCLOSURE_HIDE_SCROLL_THRESHOLD);
    }
    if (isCurrentlyVisible) {
      return !(homeDisclosureScrollIntent === "down" && scrollTop > HOME_DISCLOSURE_HIDE_SCROLL_THRESHOLD);
    }
    if (scrollTop > HOME_DISCLOSURE_SHOW_SCROLL_THRESHOLD) return false;
    return !homeDisclosureRevealRequiresUp || homeDisclosureScrollIntent === "up" || scrollTop <= 0;
  }

  function updateSearchDisclosureState() {
    const { mainRow, searchPanel, heroShell } = getHomeSearchElements();
    const { root, toggle, panel } = getHomeDisclosureParts();
    syncHomeLocationPreferenceToggle();
    if (!searchPanel || !root || !toggle || !panel) {
      applyHomeDisclosureLayoutState(
        {
          mainRow: mainRow instanceof HTMLElement ? mainRow : null,
          searchPanel: searchPanel instanceof HTMLElement ? searchPanel : null,
          heroShell: heroShell instanceof HTMLElement ? heroShell : null,
          root: root instanceof HTMLElement ? root : null,
          panel: null,
        },
        {
          open: root?.dataset.open === "1",
          visible: false,
          mounted: false,
          state: "closed",
        }
      );
      syncHomeFooterCoverageStat();
      return;
    }

    const isOpen = root.dataset.open === "1";
    const isSheetOpen = isHomeSearchSheetOpen();
    const isCompactNormal = !isSheetOpen && isHomeCompactSearchMode();

    if (!isSheetOpen && !isCompactNormal) {
      clearHomeDisclosurePanelTimer();
      clearHomeDisclosurePanelOpenRaf();
      homeDisclosureRevealRequiresUp = false;
      homeDisclosureForceVisible = false;
      toggle.setAttribute("role", "switch");
      toggle.setAttribute("aria-checked", isOpen ? "true" : "false");
      toggle.setAttribute("aria-expanded", "true");
      applyHomeDisclosureLayoutState(
        {
          mainRow: mainRow instanceof HTMLElement ? mainRow : null,
          searchPanel,
          heroShell: heroShell instanceof HTMLElement ? heroShell : null,
          root,
          panel,
        },
        {
          open: isOpen,
          visible: true,
          mounted: true,
          state: "open",
        }
      );
      syncHomeFooterCoverageStat();
      syncHomeStickyHeaderVisibility();
      return;
    }

    if (isCompactNormal) {
      clearHomeDisclosurePanelTimer();
      clearHomeDisclosurePanelOpenRaf();
      toggle.setAttribute("role", "switch");
      toggle.setAttribute("aria-checked", isOpen ? "true" : "false");
      toggle.setAttribute("aria-expanded", isOpen ? "true" : "false");
      applyHomeDisclosureLayoutState(
        {
          mainRow: mainRow instanceof HTMLElement ? mainRow : null,
          searchPanel,
          heroShell: heroShell instanceof HTMLElement ? heroShell : null,
          root,
          panel,
        },
        {
          open: isOpen,
          visible: isOpen,
          mounted: isOpen,
          state: isOpen ? "open" : "closed",
        }
      );
      syncHomeFooterCoverageStat();
      syncHomeStickyHeaderVisibility();
      return;
    }

    clearHomeDisclosurePanelTimer();
    clearHomeDisclosurePanelOpenRaf();
    homeDisclosureRevealRequiresUp = false;
    homeDisclosureForceVisible = false;
    toggle.setAttribute("role", "switch");
    toggle.setAttribute("aria-checked", "true");
    toggle.setAttribute("aria-expanded", "true");
    applyHomeDisclosureLayoutState(
      {
        mainRow: mainRow instanceof HTMLElement ? mainRow : null,
        searchPanel,
        heroShell: heroShell instanceof HTMLElement ? heroShell : null,
        root,
        panel,
      },
      {
        open: true,
        visible: true,
        mounted: true,
        state: "open",
      }
    );
    syncHomeFooterCoverageStat();
    syncHomeStickyHeaderVisibility();
    return;

  }

  function setHomeDisclosureOpen(nextOpen, options = {}) {
    const { persist = true, forceVisible = false } = options;
    const { root, panel } = getHomeDisclosureParts();
    if (!root || !panel) return;
    if (nextOpen) {
      homeDisclosureRevealRequiresUp = false;
      homeDisclosureForceVisible = forceVisible;
    } else {
      homeDisclosureForceVisible = false;
    }
    root.dataset.open = nextOpen ? "1" : "0";
    root.dataset.panelVisible =
      nextOpen && (forceVisible || isHomeDisclosurePanelVisible(true)) ? "1" : "0";
    if (persist) {
      window.sessionStorage.setItem(HOME_DISCLOSURE_KEY, nextOpen ? "1" : "0");
      window.sessionStorage.removeItem(HOME_DISCLOSURE_EXPANDED_KEY);
    }
    updateSearchDisclosureState();
  }

  function openHomeDisclosurePanel(targetToFocus = null) {
    if (!isHomeSearchSheetOpen() && !isHomeCompactSearchMode()) {
      if (targetToFocus instanceof HTMLElement) {
        focusElementSoon(targetToFocus);
      }
      return;
    }
    setHomeDisclosureOpen(true, { forceVisible: true });
    if (!(targetToFocus instanceof HTMLElement)) return;
    let attempts = 0;
    const tryFocus = () => {
      const { panel } = getHomeDisclosureParts();
      if (
        panel instanceof HTMLElement &&
        panel.dataset.panelMounted === "1" &&
        panel.dataset.panelState !== "closing" &&
        panel.getAttribute("aria-hidden") !== "true"
      ) {
        focusElementSoon(targetToFocus);
        return;
      }
      if (attempts >= 10) return;
      attempts += 1;
      window.setTimeout(tryFocus, 120);
    };
    tryFocus();
  }

  function scheduleHomeDisclosureScrollSync() {
    if (homeDisclosureScrollRaf != null) return;
    homeDisclosureScrollRaf = window.requestAnimationFrame(() => {
      homeDisclosureScrollRaf = null;
      updateHomeDisclosureScrollIntent();
      updateSearchDisclosureState();
      scheduleHomeSearchFabVisibilitySync();
    });
  }

  function scheduleHomeDisclosureViewportSync() {
    if (homeDisclosureScrollRaf != null) return;
    homeDisclosureScrollRaf = window.requestAnimationFrame(() => {
      homeDisclosureScrollRaf = null;
      homeDisclosureLastScrollTop = window.scrollY;
      updateSearchDisclosureState();
      scheduleHomeSearchFabVisibilitySync();
    });
  }

  function installHomeDisclosureScrollWatcher() {
    if (!document.body || document.body.dataset.homeDisclosureScrollBound === "1") return;
    document.body.dataset.homeDisclosureScrollBound = "1";
    homeDisclosureLastScrollTop = window.scrollY;
    window.addEventListener("scroll", scheduleHomeDisclosureScrollSync, { passive: true });
    window.addEventListener("resize", scheduleHomeDisclosureViewportSync);
  }

  function installSearchDisclosure() {
    if (!isHomeRefreshEligible()) return;
    const {
      searchPanel,
      searchButtons,
      searchLeft,
      searchRight,
      searchOptions,
      resetButton,
      locationButton,
    } = getHomeSearchElements();
    if (!(searchPanel instanceof HTMLElement) || !(searchOptions instanceof HTMLElement) || !(searchButtons instanceof HTMLElement)) return;

    let disclosure = searchPanel.querySelector(".search-disclosure");
    if (!(disclosure instanceof HTMLElement)) {
      disclosure = document.createElement("div");
      disclosure.className = "search-disclosure";
      disclosure.innerHTML = `
        <button type="button" class="search-disclosure-toggle" aria-expanded="false">
          <span class="search-disclosure-label">詳細設定</span>
          <span class="search-disclosure-switch" aria-hidden="true">
            <span class="search-disclosure-thumb"></span>
          </span>
        </button>
      `;
    }

    const disclosureMount = searchRight instanceof HTMLElement ? searchRight : searchButtons;
    if (disclosureMount instanceof HTMLElement && disclosure.parentElement !== disclosureMount) {
      disclosureMount.appendChild(disclosure);
    }

    searchPanel.querySelector(".search-advanced-summary")?.remove();

    let utility = searchOptions.querySelector(".home-advanced-utility");
    if (!(utility instanceof HTMLElement)) {
      utility = document.createElement("div");
      utility.className = "home-advanced-utility";
      utility.innerHTML = `
        <div class="home-advanced-actions">
          <button type="button" class="ghost home-advanced-close" data-home-advanced-close="1">閉じる</button>
        </div>
      `;
      searchOptions.appendChild(utility);
    }

    utility.querySelector(".home-location-preference-toggle")?.remove();
    utility.querySelector(".home-location-preference-note")?.remove();
    utility.querySelector(".location-note")?.remove();

    const actionRow = utility.querySelector(".home-advanced-actions");
    if (searchLeft instanceof HTMLElement) {
      searchLeft.querySelectorAll(".coverage-count-badge").forEach((badge) => {
        badge.remove();
      });
    }
    if (locationButton instanceof HTMLButtonElement) {
      locationButton.classList.add("home-advanced-location-button");
    }
    if (resetButton instanceof HTMLButtonElement) {
      resetButton.dataset.homeAdvancedReset = "1";
      resetButton.classList.add("home-advanced-reset");
    }

    syncHomeSearchActionPlacement();

    if (!searchOptions.id) searchOptions.id = "home-advanced-panel";
    disclosure.querySelector(".search-disclosure-toggle")?.setAttribute("aria-controls", searchOptions.id);

    if (disclosure.dataset.bound !== "1") {
      disclosure.dataset.bound = "1";
      disclosure.querySelector(".search-disclosure-toggle")?.addEventListener("click", () => {
        const currentlyOpen = disclosure.dataset.open === "1";
        setHomeDisclosureOpen(!currentlyOpen, { forceVisible: !currentlyOpen });
      });
    }

    syncHomeLocationPreferenceToggle();
    const { region, category, toggles } = getHomeAdvancedFilterControls();
    const controls = [region, category, ...toggles].filter(Boolean);
    controls.forEach((control) => {
      if (!(control instanceof HTMLElement) || control.dataset.homeDisclosureBound === "1") return;
      control.dataset.homeDisclosureBound = "1";
      control.addEventListener("change", () => {
        window.requestAnimationFrame(() => {
          updateSearchDisclosureState();
        });
      });
    });

    const defaultOpen = window.sessionStorage.getItem(HOME_DISCLOSURE_KEY) === "1";
    setHomeDisclosureOpen(defaultOpen, { persist: false });
  }

  function ensureHomeAnchors() {
    const hero = document.querySelector(".hero");
    const mapPanel = document.querySelector(".map-panel");
    const footer = document.querySelector(".footer");
    if (hero) hero.id = "home-search";
    if (mapPanel) mapPanel.id = "home-map";
    if (footer) footer.id = "home-updates";
  }

  function buildHomeStickyBrandMarkup() {
    return `
      <span class="home-sticky-brandtitle">キキドコ？</span>
      <img src="/brand/hero-icon-transparent.png" alt="" class="home-sticky-brandmark" />
    `;
  }

  function syncHomeStickyHeaderStructure() {
    if (!isHomeRefreshEligible()) return;
    const page = document.querySelector(".page");
    const hero = document.querySelector(".hero");
    const heroShell = hero?.querySelector(".hero-shell");
    const searchPanel = hero?.querySelector(".search-panel");
    if (!(page instanceof Element) || !(hero instanceof HTMLElement) || !(heroShell instanceof HTMLElement) || !(searchPanel instanceof HTMLElement)) return;

    Array.from(page.children).forEach((child) => {
      if (child instanceof HTMLElement && child !== hero && child.classList.contains("home-sticky-bar")) {
        child.remove();
      }
    });

    hero.classList.add("home-sticky-bar");
    heroShell.classList.add("home-sticky-shell");
    searchPanel.classList.add("home-header-search");
    if (!["0", "1"].includes(searchPanel.dataset.advancedOpen || "")) searchPanel.dataset.advancedOpen = "0";
    if (!["0", "1"].includes(searchPanel.dataset.advancedPanelVisible || "")) searchPanel.dataset.advancedPanelVisible = "0";
    if (!["0", "1"].includes(searchPanel.dataset.advancedPanelMounted || "")) searchPanel.dataset.advancedPanelMounted = "0";
    if (!searchPanel.dataset.advancedPanelState) searchPanel.dataset.advancedPanelState = "closed";
    if (!["0", "1"].includes(heroShell.dataset.advancedOpen || "")) heroShell.dataset.advancedOpen = "0";
    if (!["0", "1"].includes(heroShell.dataset.advancedPanelVisible || "")) heroShell.dataset.advancedPanelVisible = "0";
    if (!["0", "1"].includes(heroShell.dataset.advancedPanelMounted || "")) heroShell.dataset.advancedPanelMounted = "0";
    if (!heroShell.dataset.advancedPanelState) heroShell.dataset.advancedPanelState = "closed";

    let mainRow = heroShell.querySelector(":scope > .home-header-main-row");
    const heroCopy = heroShell.querySelector(":scope > .hero-copy");
    const titleRow = heroCopy instanceof HTMLElement ? heroCopy.querySelector(".title-row") : null;
    const heroMascotImage = heroCopy instanceof HTMLElement ? heroCopy.querySelector(".hero-mascot-image") : null;

    if (heroMascotImage instanceof HTMLImageElement) {
      heroMascotImage.src = "/brand/hero-icon-transparent.png";
    }

    const disclosureRoot =
      searchPanel.querySelector(".search-disclosure") ||
      (hero.querySelector(".search-disclosure") instanceof HTMLElement ? hero.querySelector(".search-disclosure") : null);

    if (mainRow instanceof HTMLElement) {
      if (searchPanel.parentElement === mainRow) {
        if (heroCopy instanceof HTMLElement) {
          heroCopy.insertAdjacentElement("afterend", searchPanel);
        } else if (mainRow.parentElement === heroShell) {
          heroShell.insertBefore(searchPanel, mainRow.nextElementSibling);
        }
      }
      mainRow.remove();
      mainRow = null;
    }

    heroShell.querySelectorAll(".home-sticky-brand").forEach((brand) => {
      brand.remove();
    });

    if (searchPanel.parentElement !== heroShell) {
      if (heroCopy instanceof HTMLElement) {
        heroCopy.insertAdjacentElement("afterend", searchPanel);
      } else {
        heroShell.appendChild(searchPanel);
      }
    } else if (heroCopy instanceof HTMLElement && heroCopy.nextElementSibling !== searchPanel) {
      heroCopy.insertAdjacentElement("afterend", searchPanel);
    }

    const searchMain = searchPanel.querySelector(":scope > .search-main");
    const searchActions = searchPanel.querySelector(":scope > .search-actions");
    const searchOptions =
      searchPanel.querySelector(":scope > .search-options") || searchPanel.querySelector(".search-options");

    if (searchMain instanceof HTMLElement && searchMain.parentElement === searchPanel && searchPanel.firstElementChild !== searchMain) {
      searchPanel.insertBefore(searchMain, searchPanel.firstElementChild);
    }

    if (searchActions instanceof HTMLElement && searchActions.parentElement !== searchPanel) {
      searchPanel.appendChild(searchActions);
    }

    if (searchOptions instanceof HTMLElement) {
      if (searchOptions.parentElement !== searchPanel) {
        searchPanel.insertBefore(searchOptions, searchActions instanceof HTMLElement ? searchActions : null);
      } else if (searchActions instanceof HTMLElement && searchOptions.nextElementSibling !== searchActions) {
        searchPanel.insertBefore(searchOptions, searchActions);
      }

      const nextLayoutState = resolveHomeDisclosureLayoutState({
        mainRow: null,
        searchPanel,
        heroShell,
        root: disclosureRoot instanceof HTMLElement ? disclosureRoot : null,
        panel: searchOptions,
      });

      applyHomeDisclosureLayoutState(
        {
          mainRow: null,
          searchPanel,
          heroShell,
          root: disclosureRoot instanceof HTMLElement ? disclosureRoot : null,
          panel: searchOptions,
        },
        {
          open: nextLayoutState.open,
          visible: nextLayoutState.visible,
          mounted: nextLayoutState.mounted,
          state: nextLayoutState.state,
        }
      );
    } else {
      applyHomeDisclosureLayoutState(
        {
          mainRow: null,
          searchPanel,
          heroShell,
          root: disclosureRoot instanceof HTMLElement ? disclosureRoot : null,
          panel: null,
        },
        {
          open: disclosureRoot?.dataset.open === "1",
          visible: false,
          mounted: false,
          state: "closed",
        }
      );
    }

    heroShell.querySelectorAll(":scope > .home-header-advanced-slot").forEach((slot) => {
      slot.remove();
    });

    if (titleRow instanceof HTMLElement) {
      titleRow.dataset.searchSheetTitleRow = "1";
    }

    ensureHomeSearchSheetChrome();
    applyHomeSearchSheetState(isHomeSearchSheetOpen());
    syncHomeSearchActionPlacement();
    document.body.classList.add("home-refresh-ready");
    syncHomeStickyHeaderVisibility();
  }

  function scheduleHomeStickyHeaderSync(delay = 0) {
    if (homeStructureSyncTimer != null) {
      window.clearTimeout(homeStructureSyncTimer);
      homeStructureSyncTimer = null;
    }
    homeStructureSyncTimer = window.setTimeout(() => {
      homeStructureSyncTimer = null;
      syncHomeStickyHeaderStructure();
      installSearchDisclosure();
      updateSearchDisclosureState();
      scheduleHomeSearchFabVisibilitySync();
    }, delay);
  }

  function installHomeStickyHeader() {
    if (!isHomeRefreshEligible()) return;
    syncHomeStickyHeaderStructure();
    const heroShell = document.querySelector(".hero .hero-shell");
    if (!(heroShell instanceof HTMLElement) || heroShell.dataset.homeHeaderWatchBound === "1") return;
    heroShell.dataset.homeHeaderWatchBound = "1";
    const observer = new MutationObserver(() => {
      scheduleHomeStickyHeaderSync(40);
    });
    observer.observe(heroShell, {
      childList: true,
      subtree: true,
    });
  }

  function collectFooterSupportLinks(footer) {
    const fallback = {
      terms: "",
      privacy: "",
      contact: "",
    };
    if (!(footer instanceof Element)) return fallback;
    const anchors = Array.from(footer.querySelectorAll(".footer-links a"));
    anchors.forEach((anchor) => {
      const label = String(anchor.textContent || "").trim();
      const href = String(anchor.getAttribute("href") || "").trim();
      if (!href) return;
      if (label.includes("利用規約")) fallback.terms = href;
      if (label.includes("プライバシー")) fallback.privacy = href;
      if (label.includes("問い合わせ")) fallback.contact = href;
    });
    return fallback;
  }

  function installHomeFooter() {
    if (!isHomeRefreshEligible()) return;
    const footer = document.querySelector(".footer");
    if (!(footer instanceof HTMLElement)) return;
    if (footer.dataset.homeFooterReady === "1") return;

    const links = collectFooterSupportLinks(footer);
    footer.classList.add("home-footer");
    footer.dataset.homeFooterReady = "1";
    footer.innerHTML = `
      <div class="home-footer-shell">
        <section class="home-footer-column home-footer-brand">
          <p class="home-footer-eyebrow">KIKIDOKO</p>
          <div class="home-footer-brandline">
            <img src="/brand/hero-icon-transparent.png" alt="" class="home-footer-brandicon" />
            <div class="home-footer-brandtitles">
              <h3>キキドコ？</h3>
              <p class="home-footer-brandlead">地域から、研究設備の次の一手へ。</p>
            </div>
          </div>
          <p>公開設備の分布、利用条件、情報元ページへの導線を一つの画面でまとめて確認できます。</p>
          <p class="home-footer-stat home-footer-coverage" data-ready="0">網羅機器数: 読み込み中...</p>
        </section>

        <section class="home-footer-column">
          <h4>検索ショートカット</h4>
          <div class="home-footer-actions">
            <button type="button" data-home-shortcut="keyword">機器名から探す</button>
            <button type="button" data-home-shortcut="region">地域から探す</button>
            <button type="button" data-home-shortcut="category">カテゴリから探す</button>
            <button type="button" data-home-shortcut="external">学外利用可で探す</button>
          </div>
        </section>

        <section class="home-footer-column">
          <h4>ガイド・記事</h4>
          <div class="home-footer-links-grid">
            <button type="button" data-home-scroll="home-popular" data-home-tab="popular">人気機器を見る</button>
            <button type="button" data-home-scroll="home-popular" data-home-tab="articles">記事ピックアップを見る</button>
            <a href="/update-info.html">アップデート情報</a>
          </div>
          <p class="home-footer-note">最新の修正内容と過去の更新履歴はアップデート情報ページに掲載しています。</p>
        </section>

        <section class="home-footer-column">
          <h4>法務・サポート</h4>
          <div class="home-footer-links-grid">
            ${links.terms ? `<a href="${escapeHtml(links.terms)}" target="_blank" rel="noreferrer">利用規約</a>` : ""}
            ${links.privacy ? `<a href="${escapeHtml(links.privacy)}" target="_blank" rel="noreferrer">プライバシーポリシー</a>` : ""}
            ${links.contact ? `<a href="${escapeHtml(links.contact)}" target="_blank" rel="noreferrer">お問い合わせ</a>` : ""}
          </div>
          <p class="home-footer-note">利用登録や申請フローは eqnet または各保有機関の案内をご確認ください。</p>
        </section>
      </div>
    `;
    syncHomeFooterCoverageStat();
  }

  function ensureHomeDiscoverySection() {
    if (!isHomeRefreshEligible()) return null;
    const page = document.querySelector(".page");
    const footer = document.querySelector(".footer");
    if (!(page instanceof Element) || !(footer instanceof Element)) return null;
    let section = document.getElementById("home-popular");
    if (section) return section;
    section = document.createElement("section");
    section.id = "home-popular";
    section.className = "home-discovery";
    section.innerHTML = `
      <div class="home-section-head">
        <h2 id="home-discovery-title">ピックアップ！</h2>
        <div class="home-discovery-switch" role="tablist" aria-label="注目コンテンツの切り替え">
        <button type="button" class="home-discovery-pill" data-home-tab-target="popular" role="tab" aria-selected="false">人気機器</button>
        <button type="button" class="home-discovery-pill" data-home-tab-target="articles" role="tab" aria-selected="false">おすすめ記事</button>
        </div>
      </div>
      <div class="home-discovery-panel" data-home-tab-panel="popular" role="tabpanel">
        <div class="home-discovery-empty">人気機器データを読み込み中です...</div>
      </div>
      <div class="home-discovery-panel" data-home-tab-panel="articles" role="tabpanel" hidden>
        <div class="home-discovery-empty">記事情報を読み込み中です...</div>
      </div>
    `;
    page.insertBefore(section, footer);
    return section;
  }

  function switchHomeDiscoveryTab(tabName) {
    const section = document.getElementById("home-popular");
    if (!(section instanceof HTMLElement)) return;
    const next = tabName === "articles" ? "articles" : "popular";
    section.dataset.currentTab = next;
    section.querySelectorAll("[data-home-tab-target]").forEach((button) => {
      const active = button.getAttribute("data-home-tab-target") === next;
      button.classList.toggle("is-active", active);
      button.setAttribute("aria-selected", active ? "true" : "false");
    });
    section.querySelectorAll("[data-home-tab-panel]").forEach((panel) => {
      panel.hidden = panel.getAttribute("data-home-tab-panel") !== next;
    });
  }

  function shouldShowHomePopularCue() {
    try {
      return window.sessionStorage.getItem(HOME_POPULAR_CUE_KEY) !== "1";
    } catch (_error) {
      return true;
    }
  }

  function dismissHomePopularCue() {
    try {
      window.sessionStorage.setItem(HOME_POPULAR_CUE_KEY, "1");
    } catch (_error) {
      // ignore storage errors
    }
    document.querySelectorAll(".home-card-click-cue").forEach((cue) => cue.remove());
  }

  function getPopularEquipmentSheetParts() {
    const root = document.querySelector(".home-popular-sheet.equipment-sheet");
    if (!(root instanceof HTMLElement)) {
      return {
        root: null,
        panel: null,
        handleText: null,
        eyebrow: null,
        name: null,
        meta: null,
        content: null,
        papers: null,
        actions: null,
        note: null,
      };
    }
    const panel = root.querySelector(".equipment-sheet-panel");
    return {
      root,
      panel: panel instanceof HTMLElement ? panel : null,
      handleText: root.querySelector(".equipment-sheet-handle-text"),
      eyebrow: root.querySelector(".equipment-sheet-eyebrow"),
      name: root.querySelector(".equipment-sheet-name"),
      meta: root.querySelector(".equipment-sheet-meta"),
      content: root.querySelector(".equipment-sheet-content"),
      papers: root.querySelector(".equipment-sheet-papers"),
      actions: root.querySelector(".equipment-sheet-actions"),
      note: root.querySelector(".equipment-sheet-note"),
    };
  }

  function closePopularEquipmentSheet() {
    const { root, panel, handleText } = getPopularEquipmentSheetParts();
    if (!(root instanceof HTMLElement)) return;
    root.classList.remove("is-open", "is-expanded");
    root.hidden = true;
    root.dataset.open = "0";
    root.dataset.equipmentId = "";
    root.dataset.equipmentName = "";
    root.dataset.prefecture = "";
    if (panel instanceof HTMLElement) {
      panel.dataset.detailSignature = "";
      panel.dataset.detailHydrated = "0";
      panel.dataset.equipmentId = "";
      panel.dataset.detailDocId = "";
      panel.dataset.sheetSource = "popular";
    }
    if (handleText instanceof HTMLElement) {
      handleText.textContent = "タップで全画面表示";
    }
    const handleButton = root.querySelector(".equipment-sheet-handle");
    if (handleButton instanceof HTMLButtonElement) {
      handleButton.setAttribute("aria-expanded", "false");
    }
    scheduleHomeStickyHeaderVisibilitySync();
  }

  function setPopularEquipmentSheetExpanded(expanded) {
    const { root, handleText } = getPopularEquipmentSheetParts();
    if (!(root instanceof HTMLElement)) return;
    const nextExpanded = Boolean(expanded);
    root.classList.toggle("is-expanded", nextExpanded);
    if (handleText instanceof HTMLElement) {
      handleText.textContent = nextExpanded ? "タップで元に戻す" : "タップで全画面表示";
    }
    const handleButton = root.querySelector(".equipment-sheet-handle");
    if (handleButton instanceof HTMLButtonElement) {
      handleButton.setAttribute("aria-expanded", nextExpanded ? "true" : "false");
    }
  }

  function ensurePopularEquipmentSheet() {
    const existing = getPopularEquipmentSheetParts().root;
    if (existing) return existing;
    const root = document.createElement("div");
    root.className = "equipment-sheet home-popular-sheet";
    root.hidden = true;
    root.dataset.open = "0";
    root.innerHTML = `
      <div class="equipment-sheet-backdrop" aria-hidden="true"></div>
      <div class="equipment-sheet-panel home-popular-sheet-panel" role="dialog" aria-modal="false" data-sheet-source="popular">
        <button type="button" class="equipment-sheet-handle" aria-expanded="false">
          <span class="equipment-sheet-handle-bar" aria-hidden="true"></span>
          <span class="equipment-sheet-handle-text">タップで全画面表示</span>
        </button>
        <div class="equipment-sheet-header">
          <div class="equipment-sheet-title">
            <p class="equipment-sheet-eyebrow">人気機器</p>
            <h4 class="equipment-sheet-name">読み込み中...</h4>
            <p class="equipment-sheet-meta">詳細データを取得しています。</p>
          </div>
          <div class="equipment-sheet-header-actions">
            <button type="button" class="equipment-sheet-close">閉じる</button>
          </div>
        </div>
        <div class="equipment-sheet-body">
          <div class="equipment-sheet-content">
            <p>機器の詳細を読み込み中です。</p>
            <ul hidden></ul>
          </div>
          <div class="equipment-sheet-papers">
            <h5>関連論文（DOI）</h5>
            <p class="paper-status">関連論文解説を読み込み中です。</p>
          </div>
        </div>
        <div class="equipment-sheet-actions"></div>
        <p class="equipment-sheet-note">詳細な用途や利用条件は機器ページでご確認ください。</p>
      </div>
    `;
    document.body.appendChild(root);

    root.querySelector(".equipment-sheet-backdrop")?.addEventListener("click", closePopularEquipmentSheet);
    root.querySelector(".equipment-sheet-close")?.addEventListener("click", closePopularEquipmentSheet);
    root.querySelector(".equipment-sheet-handle")?.addEventListener("click", () => {
      setPopularEquipmentSheetExpanded(!root.classList.contains("is-expanded"));
    });
    root.querySelector(".equipment-sheet-actions")?.addEventListener("click", (event) => {
      const target = event.target;
      if (!(target instanceof HTMLElement)) return;
      const action = target.closest("[data-popular-sheet-action]");
      if (!(action instanceof HTMLButtonElement)) return;
      const href = String(action.dataset.href || "").trim();
      if (!href) return;
      openHomeExternalLink(href);
    });

    document.addEventListener("keydown", (event) => {
      if (event.key !== "Escape") return;
      const { root: current } = getPopularEquipmentSheetParts();
      if (!(current instanceof HTMLElement) || current.hidden) return;
      closePopularEquipmentSheet();
    });

    return root;
  }

  function buildPopularSheetFallbackDetail(snapshotEntry, item) {
    const equipmentId = String(
      snapshotEntry?.equipment_id || snapshotEntry?.doc_id || item?.equipmentId || ""
    ).trim();
    return {
      equipment_id: equipmentId,
      doc_id: String(snapshotEntry?.doc_id || equipmentId).trim(),
      name: String(snapshotEntry?.name || item?.name || "名称不明").trim(),
      category_general: String(snapshotEntry?.category_general || item?.categoryGeneral || "未分類").trim(),
      category_detail: String(snapshotEntry?.category_detail || "").trim(),
      org_name: String(snapshotEntry?.org_name || item?.orgName || "").trim(),
      prefecture: String(snapshotEntry?.prefecture || item?.prefecture || "").trim(),
      source_url: normalizeHomeUrl(snapshotEntry?.source_url || item?.sourceUrl || ""),
      eqnet_url: normalizeHomeUrl(
        snapshotEntry?.eqnet_url || item?.eqnetUrl || snapshotEntry?.source_url || item?.sourceUrl || ""
      ),
      external_use: String(snapshotEntry?.external_use || item?.externalUse || "").trim(),
      fee_band: String(snapshotEntry?.fee_band || item?.feeBand || "").trim(),
    };
  }

  function mergePopularSheetDetail(detail, snapshotEntry, item) {
    const base = buildPopularSheetFallbackDetail(snapshotEntry, item);
    if (!detail || typeof detail !== "object") return base;
    const merged = {
      ...base,
      ...detail,
    };
    if (!String(merged.equipment_id || "").trim()) merged.equipment_id = base.equipment_id;
    if (!String(merged.doc_id || "").trim()) merged.doc_id = base.doc_id;
    if (!String(merged.name || "").trim()) merged.name = base.name;
    if (!String(merged.category_general || "").trim()) merged.category_general = base.category_general;
    if (!String(merged.category_detail || "").trim()) merged.category_detail = base.category_detail;
    if (!String(merged.org_name || "").trim()) merged.org_name = base.org_name;
    if (!String(merged.prefecture || "").trim()) merged.prefecture = base.prefecture;
    if (!String(merged.source_url || "").trim()) merged.source_url = base.source_url;
    if (!String(merged.eqnet_url || "").trim()) merged.eqnet_url = base.eqnet_url;
    if (!String(merged.external_use || "").trim()) merged.external_use = base.external_use;
    if (!String(merged.fee_band || "").trim()) merged.fee_band = base.fee_band;
    return merged;
  }

  function renderPopularEquipmentSheetFrame(detailLike, loadingMessage = "") {
    const { panel, eyebrow, name, meta, content, papers, actions, note } = getPopularEquipmentSheetParts();
    if (!(panel instanceof HTMLElement)) return;

    const safeDetail = detailLike && typeof detailLike === "object" ? detailLike : {};
    const equipmentId = String(safeDetail.equipment_id || "").trim();
    const docId = String(safeDetail.doc_id || equipmentId).trim();
    const category = String(safeDetail.category_general || "人気機器").trim();
    const title = cleanEquipmentName(safeDetail.name || "名称不明");
    const prefecture = String(safeDetail.prefecture || "").trim();
    const orgName = String(safeDetail.org_name || "").trim();
    const sourceUrl = normalizeHomeUrl(safeDetail.source_url || "");
    const eqnetUrl = normalizeHomeUrl(safeDetail.eqnet_url || sourceUrl);
    const signature = detailSignature(title, prefecture, orgName);

    if (panel.parentElement instanceof HTMLElement) {
      panel.parentElement.dataset.equipmentId = equipmentId;
      panel.parentElement.dataset.equipmentName = title;
      panel.parentElement.dataset.prefecture = prefecture;
    }
    panel.dataset.equipmentId = equipmentId;
    panel.dataset.detailDocId = docId;
    panel.dataset.detailSignature = signature;
    panel.dataset.detailHydrated = "0";
    panel.dataset.sheetSource = "popular";

    if (eyebrow instanceof HTMLElement) eyebrow.textContent = category || "人気機器";
    if (name instanceof HTMLElement) name.textContent = title;
    if (meta instanceof HTMLElement) {
      const metaParts = [prefecture, orgName].filter(Boolean);
      meta.textContent = metaParts.length ? metaParts.join(" ・ ") : "機関情報を表示しています。";
    }

    if (content instanceof HTMLElement) {
      content.innerHTML = `
        <p>${escapeHtml(loadingMessage || "機器の詳細を読み込み中です。")}</p>
        <ul hidden></ul>
      `;
    }

    if (papers instanceof HTMLElement) {
      papers.innerHTML = `
        <h5>関連論文（DOI）</h5>
        <p class="paper-status">関連論文解説を読み込み中です。</p>
      `;
    }

    if (actions instanceof HTMLElement) {
      actions.innerHTML = `
        ${
          sourceUrl
            ? `<button type="button" class="link-button" data-popular-sheet-action="source" data-href="${escapeHtml(sourceUrl)}">機器ページへ</button>`
            : `<span class="link-disabled">情報元なし</span>`
        }
        ${
          eqnetUrl
            ? `<button type="button" class="link-button secondary" data-popular-sheet-action="eqnet" data-href="${escapeHtml(eqnetUrl)}">eqnetで確認</button>`
            : ""
        }
      `;
    }

    if (note instanceof HTMLElement) {
      note.textContent = "詳細な用途や利用条件は機器ページでご確認ください。";
    }

    removeDetailRetry(panel);
  }

  async function openPopularEquipmentSheet(item) {
    const equipmentId = String(item?.equipmentId || "").trim();
    if (!equipmentId) return false;

    dismissHomePopularCue();
    ensurePopularEquipmentSheet();
    const token = ++popularEquipmentSheetToken;

    const { root } = getPopularEquipmentSheetParts();
    if (!(root instanceof HTMLElement)) return false;
    root.hidden = false;
    root.classList.add("is-open");
    root.classList.remove("is-expanded");
    root.dataset.open = "1";
    setPopularEquipmentSheetExpanded(false);
    scheduleHomeStickyHeaderVisibilitySync();
    focusElementSoon(root.querySelector(".equipment-sheet-close"));

    let snapshotEntry = null;
    try {
      const snapshot = await loadSnapshotLiteData();
      snapshotEntry = snapshot?.byId?.get(equipmentId) || null;
    } catch (error) {
      console.error(error);
    }

    const baseDetail = buildPopularSheetFallbackDetail(snapshotEntry, item);
    renderPopularEquipmentSheetFrame(baseDetail, "機器の詳細を読み込み中です。");

    try {
      await loadBootstrapData();
      const candidateIds = [equipmentId, String(snapshotEntry?.doc_id || "").trim()].filter(Boolean);
      const detail = await loadDetailByIds(candidateIds);
      if (token !== popularEquipmentSheetToken) return true;
      const mergedDetail = mergePopularSheetDetail(detail, snapshotEntry, item);
      renderPopularEquipmentSheetFrame(mergedDetail, "機器の詳細を表示します。");
      applyDetailToSheet(
        getPopularEquipmentSheetParts().panel,
        mergedDetail,
        detailSignature(
          cleanEquipmentName(mergedDetail.name || ""),
          String(mergedDetail.prefecture || "").trim(),
          String(mergedDetail.org_name || "").trim()
        )
      );
      return true;
    } catch (error) {
      console.error(error);
      if (token !== popularEquipmentSheetToken) return true;
      renderPopularEquipmentSheetFrame(baseDetail, "詳細データを取得できなかったため、基本情報のみ表示しています。");
      applyDetailToSheet(
        getPopularEquipmentSheetParts().panel,
        baseDetail,
        detailSignature(
          cleanEquipmentName(baseDetail.name || ""),
          String(baseDetail.prefecture || "").trim(),
          String(baseDetail.org_name || "").trim()
        )
      );
      return true;
    }
  }

  async function buildArticleCardsMarkup(payload) {
    const ids = Array.isArray(payload?.publishing_schedule?.month_1_ids)
      ? payload.publishing_schedule.month_1_ids.slice(0, 6)
      : [];
    const articles = Array.isArray(payload?.articles) ? payload.articles : [];
    const articleMap = new Map();
    articles.forEach((article) => {
      const id = String(article?.id || "").trim();
      if (id) articleMap.set(id, article);
    });
    const baseUrl = String(payload?.site?.blog_base_url || "").trim();
    const articleCards = await Promise.all(
      ids
        .map((id) => articleMap.get(id))
        .filter(Boolean)
        .map(async (article) => {
          const excerpt = await loadArticleExcerpt(article);
          const fallbackCopy = "記事本文を準備中です。公開ページから内容を確認できます。";
          const href = normalizeHomeUrl(baseUrl ? `${baseUrl}${String(article.url || "").trim()}` : article.url);
          const category = String(article?.category || "article").trim();
          return `
            <article class="home-card home-article-card">
              <p class="home-card-kicker">${escapeHtml(category)}</p>
              <h3>${escapeHtml(String(article?.title || "タイトル未設定"))}</h3>
              <p class="home-card-copy">${escapeHtml(excerpt || fallbackCopy)}</p>
              <a class="home-card-link" href="${escapeHtml(href)}" target="_blank" rel="noreferrer">記事を読む</a>
            </article>
          `;
        })
    );
    return articleCards.join("");
  }

  async function buildPopularCards(feedPayload) {
    const snapshot = await loadSnapshotLiteData();
    const snapshotMap = snapshot?.byId || snapshotLiteById || new Map();
    const feedItems = Array.isArray(feedPayload?.items) ? feedPayload.items : [];
    const cards = [];
    const seen = new Set();

    feedItems.forEach((item) => {
      const equipmentId = String(item?.equipment_id || "").trim();
      if (!equipmentId || seen.has(equipmentId)) return;
      seen.add(equipmentId);
      const snapshotEntry = snapshotMap.get(equipmentId) || null;
      const merged = {
        equipmentId,
        name: cleanEquipmentName(snapshotEntry?.name || item?.name),
        categoryGeneral: String(snapshotEntry?.category_general || item?.category_general || "未分類").trim(),
        orgName: String(snapshotEntry?.org_name || item?.org_name || "").trim(),
        prefecture: String(snapshotEntry?.prefecture || item?.prefecture || "").trim(),
        sourceUrl: normalizeHomeUrl(snapshotEntry?.source_url || item?.source_url),
        eqnetUrl: normalizeHomeUrl(snapshotEntry?.eqnet_url || item?.eqnet_url),
        externalUse: String(snapshotEntry?.external_use || "").trim(),
        feeBand: String(snapshotEntry?.fee_band || "").trim(),
        score: toNumber(item?.score || 0),
      };
      if (!merged.name || !merged.sourceUrl) return;
      cards.push(merged);
    });

    return cards.slice(0, 8);
  }

  function renderPopularCardsMarkup(items) {
    if (!items.length) {
      return '<div class="home-discovery-empty">人気機器データはまだ準備中です。記事ピックアップをご覧ください。</div>';
    }
    const showCue = shouldShowHomePopularCue();
    return `
      <div class="home-rail">
        ${items
          .map(
            (item, index) => `
              <article
                class="home-card home-popular-card"
                data-equipment-id="${escapeHtml(item.equipmentId)}"
                data-name="${escapeHtml(item.name)}"
                data-prefecture="${escapeHtml(item.prefecture)}"
                data-org-name="${escapeHtml(item.orgName || "")}"
                data-category-general="${escapeHtml(item.categoryGeneral || "")}"
                data-source-url="${escapeHtml(item.sourceUrl || "")}"
                data-eqnet-url="${escapeHtml(item.eqnetUrl || "")}"
                data-external-use="${escapeHtml(item.externalUse || "")}"
                data-fee-band="${escapeHtml(item.feeBand || "")}"
                tabindex="0"
                role="button"
                aria-label="${escapeHtml(`${item.name} の詳細を開く`)}"
              >
                ${
                  showCue && index === 0
                    ? `
                      <div class="home-card-click-cue" aria-hidden="true">
                        <span class="home-card-click-cue-icon">
                          <svg viewBox="0 0 40 40" focusable="false" aria-hidden="true">
                            <path d="M12 5.5c1.7 0 3 1.3 3 3V19h1V4.5c0-1.66 1.34-3 3-3s3 1.34 3 3V15h1V8.5c0-1.66 1.34-3 3-3s3 1.34 3 3V17h1v-3.5c0-1.66 1.34-3 3-3s3 1.34 3 3V23c0 7.73-6.27 14-14 14h-4.5C15.07 37 10 31.93 10 25.5V16c0-1.66 1.34-3 3-3s3 1.34 3 3v5h1V8.5c0-1.7-1.3-3-3-3-1.66 0-3 1.34-3 3V21h-1V8.5c0-1.7 1.3-3 3-3Z" fill="currentColor"></path>
                          </svg>
                        </span>
                        <span class="home-card-click-cue-text">クリックで機器詳細</span>
                      </div>
                    `
                    : ""
                }
                <div class="home-card-score">閲覧数${index + 1}位</div>
                <p class="home-card-kicker">${escapeHtml(item.categoryGeneral)}</p>
                <h3>${escapeHtml(item.name)}</h3>
                <p class="home-card-copy">${escapeHtml(item.orgName || "機関情報なし")}</p>
                <div class="home-card-tags">
                  ${item.prefecture ? `<span>${escapeHtml(item.prefecture)}</span>` : ""}
                  ${item.externalUse ? `<span>${escapeHtml(item.externalUse)}</span>` : ""}
                  ${item.feeBand ? `<span>${escapeHtml(item.feeBand)}</span>` : ""}
                </div>
              </article>
            `
          )
          .join("")}
      </div>
    `;
  }

  async function renderHomeDiscovery() {
    const section = ensureHomeDiscoverySection();
    if (!(section instanceof HTMLElement)) return;

    const popularPanel = section.querySelector('[data-home-tab-panel="popular"]');
    const articlesPanel = section.querySelector('[data-home-tab-panel="articles"]');
    if (!(popularPanel instanceof HTMLElement) || !(articlesPanel instanceof HTMLElement)) return;

    let popularCards = [];
    let popularFailed = false;
    try {
      const feedPayload = await loadPopularFeed();
      popularCards = await buildPopularCards(feedPayload);
    } catch (error) {
      popularFailed = true;
      console.error(error);
    }

    let articleCardsHtml = "";
    try {
      const articlePayload = await loadBlogArticles();
      articleCardsHtml = await buildArticleCardsMarkup(articlePayload);
    } catch (error) {
      console.error(error);
    }

    popularPanel.innerHTML = popularFailed
      ? '<div class="home-discovery-empty">人気機器データを取得できませんでした。</div>'
      : renderPopularCardsMarkup(popularCards);

    articlesPanel.innerHTML = articleCardsHtml
      ? `<div class="home-rail home-rail-articles">${articleCardsHtml}</div>`
      : '<div class="home-discovery-empty">記事データを取得できませんでした。</div>';

    const preferredTab = popularCards.length > 0 ? "popular" : articleCardsHtml ? "articles" : "articles";
    switchHomeDiscoveryTab(section.dataset.currentTab || preferredTab);
  }

  async function annotateHomeResultRows() {
    if (!isHomeRefreshEligible()) return;
    await ensureLookupFromSnapshotLite();

    document.querySelectorAll(".result-row").forEach((row) => {
      if (!(row instanceof HTMLElement)) return;
      const name = cleanEquipmentName(row.querySelector(".result-title strong")?.textContent || "");
      const prefecture = String(row.querySelector(".result-distance .prefecture")?.textContent || "").trim();
      const ids = resolveEquipmentIds(name, prefecture, "");
      row.dataset.equipmentId = ids[0] || "";
      row.dataset.equipmentName = name;
      row.dataset.prefecture = prefecture;
    });

    const sheet = document.querySelector(".equipment-sheet");
    if (sheet instanceof HTMLElement) {
      const name = cleanEquipmentName(sheet.querySelector(".equipment-sheet-name")?.textContent || "");
      const meta = String(sheet.querySelector(".equipment-sheet-meta")?.textContent || "").trim();
      const parts = meta
        .split("・")
        .map((part) => part.trim())
        .filter(Boolean);
      const prefecture = parts[0] || "";
      const orgName = parts.slice(1).join("・");
      const ids = resolveEquipmentIds(name, prefecture, orgName);
      sheet.dataset.equipmentId = ids[0] || "";
      sheet.dataset.equipmentName = name;
      sheet.dataset.prefecture = prefecture;
    }
  }

  function scheduleResultRowAnnotation(delay = 0) {
    if (resultRowAnnotationTimer != null) {
      window.clearTimeout(resultRowAnnotationTimer);
      resultRowAnnotationTimer = null;
    }
    resultRowAnnotationTimer = window.setTimeout(() => {
      annotateHomeResultRows().catch((error) => console.error(error));
    }, delay);
  }

  function installHomeRowAnnotationWatcher() {
    if (!document.body || document.body.dataset.homeRowAnnotationWatchBound === "1") return;
    document.body.dataset.homeRowAnnotationWatchBound = "1";
    scheduleResultRowAnnotation(0);
    const observer = new MutationObserver(() => {
      scheduleResultRowAnnotation(80);
    });
    observer.observe(document.body, {
      childList: true,
      subtree: true,
      attributes: false,
      characterData: false,
    });
  }

  function findResultRowForEquipment(item) {
    const targetId = String(item?.equipmentId || "").trim();
    const targetName = normalizeLookupPart(item?.name || "");
    const targetPrefecture = normalizeLookupPart(item?.prefecture || "");
    const rows = Array.from(document.querySelectorAll(".result-row"));
    return (
      rows.find((row) => row instanceof HTMLElement && row.dataset.equipmentId === targetId) ||
      rows.find(
        (row) =>
          row instanceof HTMLElement &&
          normalizeLookupPart(row.dataset.equipmentName || "") === targetName &&
          (!targetPrefecture || normalizeLookupPart(row.dataset.prefecture || "") === targetPrefecture)
      ) ||
      null
    );
  }

  function waitForResultRow(item, timeoutMs = 2600) {
    return new Promise((resolve) => {
      const startedAt = Date.now();
      const timer = window.setInterval(() => {
        const row = findResultRowForEquipment(item);
        if (row) {
          window.clearInterval(timer);
          resolve(row);
          return;
        }
        if (Date.now() - startedAt >= timeoutMs) {
          window.clearInterval(timer);
          resolve(null);
        }
      }, 120);
    });
  }

  async function openEquipmentFromRail(item) {
    scheduleResultRowAnnotation(0);
    let row = findResultRowForEquipment(item);
    if (!row) {
      const input = document.querySelector(".search-main input");
      const searchButton = document.querySelector(".search-right .primary");
      if (input instanceof HTMLInputElement && searchButton instanceof HTMLButtonElement) {
        input.value = String(item?.name || "");
        input.dispatchEvent(new Event("input", { bubbles: true }));
        searchButton.click();
        row = await waitForResultRow(item);
      }
    }

    if (row instanceof HTMLElement) {
      row.click();
      return true;
    }

    return false;
  }

  function handlePopularCardDetail(item) {
    openPopularEquipmentSheet(item)
      .then((opened) => {
        if (opened) {
          logPopularityEvent(item.equipmentId, "detail_open", "popular_rail");
        }
      })
      .catch((error) => console.error(error));
  }

  function canSendPopularityEvent(equipmentId, eventType) {
    const id = String(equipmentId || "").trim();
    const type = String(eventType || "").trim();
    if (!id || !type) return false;
    const key = `${POPULARITY_EVENT_KEY_PREFIX}:${type}:${id}`;
    const lastAt = Number(window.localStorage.getItem(key) || 0);
    if (Date.now() - lastAt < POPULARITY_RATE_LIMIT_MS) return false;
    window.localStorage.setItem(key, String(Date.now()));
    return true;
  }

  async function createPopularityEvent(equipmentId, eventType, surface) {
    const endpoint = `${firestoreBase()}/${POPULARITY_COLLECTION}?key=${encodeURIComponent(FIRESTORE_API_KEY)}`;
    const response = await originalFetch(endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        fields: {
          equipment_id: { stringValue: String(equipmentId || "").trim() },
          event_type: { stringValue: String(eventType || "").trim() },
          created_at: { timestampValue: new Date().toISOString() },
          client_fingerprint: { stringValue: getFingerprint() },
          surface: { stringValue: String(surface || "home").trim() },
        },
      }),
    });

    if (!response.ok) {
      const text = await response.text();
      throw new Error(`equipment_view_events_create_failed:${response.status}:${text}`);
    }

    return response.json();
  }

  function logPopularityEvent(equipmentId, eventType, surface) {
    if (!canSendPopularityEvent(equipmentId, eventType)) return;
    createPopularityEvent(equipmentId, eventType, surface).catch((error) => console.error(error));
  }

  function openHomeExternalLink(url) {
    const href = normalizeHomeUrl(url);
    if (!href) return;
    window.open(href, "_blank", "noopener,noreferrer");
  }

  function getHomeLocationPromptParts() {
    const root = document.querySelector(".home-location-prompt");
    if (!(root instanceof HTMLElement)) {
      return {
        root: null,
        title: null,
        copy: null,
        confirm: null,
      };
    }
    return {
      root,
      title: root.querySelector(".home-location-prompt-title"),
      copy: root.querySelector(".home-location-prompt-copy"),
      confirm: root.querySelector('[data-location-prompt-action="confirm"]'),
    };
  }

  function ensureHomeLocationPrompt() {
    const existing = getHomeLocationPromptParts().root;
    if (existing) return existing;
    const root = document.createElement("div");
    root.className = "home-location-prompt";
    root.hidden = true;
    root.innerHTML = `
      <button type="button" class="home-location-prompt-backdrop" data-location-prompt-action="cancel" aria-label="閉じる"></button>
      <div class="home-location-prompt-panel" role="dialog" aria-modal="true" aria-labelledby="home-location-prompt-title">
        <p class="home-location-prompt-eyebrow">Search Option</p>
        <h3 class="home-location-prompt-title" id="home-location-prompt-title">現在地を使いますか？</h3>
        <p class="home-location-prompt-copy">現在地を使うと、近い設備順で探せます。使わない場合は通常の検索を続けます。</p>
        <div class="home-location-prompt-actions">
          <button type="button" class="ghost" data-location-prompt-action="cancel">使わずに検索</button>
          <button type="button" class="primary" data-location-prompt-action="confirm">現在地を使う</button>
        </div>
      </div>
    `;
    document.body.appendChild(root);
    return root;
  }

  function closeHomeLocationPrompt(result = "cancel") {
    const { root } = getHomeLocationPromptParts();
    if (root instanceof HTMLElement) {
      root.hidden = true;
      root.dataset.open = "0";
    }
    document.body.classList.remove("home-location-prompt-open");
    const resolve = homeLocationPromptResolver;
    homeLocationPromptResolver = null;
    if (typeof resolve === "function") resolve(result);
  }

  function showHomeLocationPrompt(mode = "unset") {
    const root = ensureHomeLocationPrompt();
    const { title, copy, confirm } = getHomeLocationPromptParts();
    if (homeLocationPromptResolver) {
      closeHomeLocationPrompt("cancel");
    }
    if (title instanceof HTMLElement) {
      title.textContent =
        mode === "enabled"
          ? "現在地を取得してから検索しますか？"
          : "現在地を使って検索しますか？";
    }
    if (copy instanceof HTMLElement) {
      copy.textContent =
        mode === "enabled"
          ? "現在地を使う設定が ON ですが、まだ位置情報を取得していません。取得後に近い設備順で検索します。"
          : "現在地を使うと、近い設備順で探せます。使わない場合は通常の検索を続けます。";
    }
    root.hidden = false;
    root.dataset.open = "1";
    document.body.classList.add("home-location-prompt-open");
    focusElementSoon(confirm instanceof HTMLElement ? confirm : root);
    return new Promise((resolve) => {
      homeLocationPromptResolver = resolve;
    });
  }

  async function requestHomeLocationFromQuickButton(options = {}) {
    const { alreadyTriggered = false } = options;
    if (pendingHomeLocationRequest) return pendingHomeLocationRequest;
    if (hasReadyHomeLocation()) return true;

    const { locationButton } = getHomeSearchElements();
    if (!(locationButton instanceof HTMLButtonElement)) {
      if (!navigator.geolocation) return false;
      pendingHomeLocationRequest = new Promise((resolve) => {
        navigator.geolocation.getCurrentPosition(
          () => {
            setHomeLocationReadyState(true);
            pendingHomeLocationRequest = null;
            resolve(true);
          },
          () => {
            setHomeLocationReadyState(false);
            pendingHomeLocationRequest = null;
            resolve(false);
          },
          { enableHighAccuracy: false, timeout: 12000, maximumAge: 600000 }
        );
      });
      return pendingHomeLocationRequest;
    }

    pendingHomeLocationRequest = new Promise((resolve) => {
      const startedAt = Date.now();
      let settled = false;
      let timer = null;
      let observer = null;

      const finish = (value) => {
        if (settled) return;
        settled = true;
        pendingHomeLocationRequest = null;
        if (timer != null) window.clearInterval(timer);
        if (observer) observer.disconnect();
        setHomeLocationReadyState(Boolean(value));
        resolve(value);
      };

      const check = () => {
        const { locationButton: currentButton, locationNote } = getHomeSearchElements();
        if (!(currentButton instanceof HTMLButtonElement)) {
          finish(false);
          return;
        }
        if (hasReadyHomeLocation()) {
          finish(true);
          return;
        }
        const noteText = String(locationNote?.textContent || "").trim();
        if (
          noteText.includes("失敗") ||
          noteText.includes("許可") ||
          noteText.includes("利用できません")
        ) {
          finish(false);
          return;
        }
        if (Date.now() - startedAt >= 13000) {
          finish(hasReadyHomeLocation());
        }
      };

      observer = new MutationObserver(check);
      observer.observe(document.body, {
        childList: true,
        subtree: true,
        characterData: true,
        attributes: true,
      });

      timer = window.setInterval(check, 160);
      if (!alreadyTriggered && !locationButton.disabled) {
        locationButton.click();
      } else {
        window.setTimeout(check, 20);
      }
    });

    return pendingHomeLocationRequest;
  }

  function triggerHomeSearch(searchButton) {
    if (!(searchButton instanceof HTMLButtonElement)) return;
    allowNextHomeSearchClick = true;
    searchButton.click();
    if (isHomeSearchSheetOpen()) {
      window.setTimeout(() => {
        closeHomeSearchSheet();
      }, 0);
    }
  }

  async function handleHomeSearchIntent(searchButton) {
    if (!(searchButton instanceof HTMLButtonElement)) return;
    triggerHomeSearch(searchButton);
  }

  function handleHomeShortcut(action) {
    const { searchInput, searchButton } = getHomeSearchElements();
    const { region, category, externalToggle } = getHomeAdvancedFilterControls();

    scrollToHomeSection("home-search");

    if (action === "keyword" && searchInput instanceof HTMLInputElement) {
      searchInput.dataset.searchInstitutionHint = "0";
      searchInput.placeholder = HOME_KEYWORD_PLACEHOLDER_DEFAULT;
      focusElementSoon(searchInput);
      return;
    }

    if (action === "institution" && searchInput instanceof HTMLInputElement) {
      searchInput.dataset.searchInstitutionHint = "1";
      searchInput.placeholder = HOME_KEYWORD_PLACEHOLDER_INSTITUTION;
      focusElementSoon(searchInput);
      return;
    }

    if (action === "region" && region) {
      openHomeDisclosurePanel(region);
      return;
    }

    if (action === "category" && category) {
      openHomeDisclosurePanel(category);
      return;
    }

    if (action === "external") {
      if (externalToggle instanceof HTMLInputElement && !externalToggle.checked) {
        externalToggle.click();
      }
      openHomeDisclosurePanel(externalToggle);
      focusElementSoon(searchButton instanceof HTMLElement ? searchButton : externalToggle);
    }
  }

  function installHomeInteractionBindings() {
    if (!document.body || document.body.dataset.homeInteractionBound === "1") return;
    document.body.dataset.homeInteractionBound = "1";

    document.addEventListener(
      "click",
      (event) => {
        if (!isHomeRefreshEligible()) return;
        const target = event.target;
        if (!(target instanceof Element)) return;

        const promptAction = target.closest("[data-location-prompt-action]");
        if (promptAction instanceof HTMLElement) {
          event.preventDefault();
          closeHomeLocationPrompt(promptAction.getAttribute("data-location-prompt-action") || "cancel");
          return;
        }

        const searchFab = target.closest(".home-search-fab");
        if (searchFab instanceof HTMLButtonElement) {
          event.preventDefault();
          openHomeSearchSheet();
          return;
        }

        const searchSheetBackdrop = target.closest(".home-search-sheet-backdrop");
        if (searchSheetBackdrop instanceof HTMLButtonElement) {
          event.preventDefault();
          closeHomeSearchSheet();
          return;
        }

        const searchSheetClose = target.closest(".home-search-sheet-close");
        if (searchSheetClose instanceof HTMLButtonElement) {
          event.preventDefault();
          closeHomeSearchSheet();
          return;
        }

        const closeAdvanced = target.closest("[data-home-advanced-close]");
        if (closeAdvanced instanceof HTMLElement) {
          event.preventDefault();
          setHomeDisclosureOpen(false);
          return;
        }

        const advancedReset = target.closest("[data-home-advanced-reset]");
        if (advancedReset instanceof HTMLButtonElement) {
          window.setTimeout(() => {
            setHomeLocationPreference("0");
            syncHomeLocationPreferenceToggle();
            updateSearchDisclosureState();
          }, 0);
          return;
        }

        const searchSubmit = target.closest('[data-home-search-submit="1"]');
        if (searchSubmit instanceof HTMLButtonElement) {
          if (allowNextHomeSearchClick) {
            allowNextHomeSearchClick = false;
            return;
          }
          event.preventDefault();
          event.stopPropagation();
          event.stopImmediatePropagation();
          handleHomeSearchIntent(searchSubmit).catch((error) => console.error(error));
          return;
        }

        const quickLocation = target.closest(".location-button");
        if (quickLocation instanceof HTMLButtonElement) {
          window.setTimeout(() => {
            requestHomeLocationFromQuickButton({ alreadyTriggered: true })
              .catch((error) => console.error(error))
              .finally(() => {
                updateSearchDisclosureState();
              });
          }, 0);
        }

        const scrollTrigger = target.closest("[data-home-scroll]");
        if (scrollTrigger instanceof HTMLElement) {
          event.preventDefault();
          const nextTab = scrollTrigger.getAttribute("data-home-tab");
          if (nextTab) switchHomeDiscoveryTab(nextTab);
          scrollToHomeSection(scrollTrigger.getAttribute("data-home-scroll") || "");
          return;
        }

        const shortcutTrigger = target.closest("[data-home-shortcut]");
        if (shortcutTrigger instanceof HTMLElement) {
          event.preventDefault();
          handleHomeShortcut(shortcutTrigger.getAttribute("data-home-shortcut") || "");
          return;
        }

        const tabTrigger = target.closest("[data-home-tab-target]");
        if (tabTrigger instanceof HTMLElement) {
          event.preventDefault();
          switchHomeDiscoveryTab(tabTrigger.getAttribute("data-home-tab-target") || "popular");
          return;
        }

        const popularCard = target.closest(".home-popular-card");
        if (popularCard instanceof HTMLElement) {
          if (target.closest("a, button")) return;
          event.preventDefault();
          handlePopularCardDetail({
            equipmentId: popularCard.dataset.equipmentId || "",
            name: popularCard.dataset.name || "",
            prefecture: popularCard.dataset.prefecture || "",
            orgName: popularCard.dataset.orgName || "",
            categoryGeneral: popularCard.dataset.categoryGeneral || "",
            sourceUrl: popularCard.dataset.sourceUrl || "",
            eqnetUrl: popularCard.dataset.eqnetUrl || "",
            externalUse: popularCard.dataset.externalUse || "",
            feeBand: popularCard.dataset.feeBand || "",
          });
          return;
        }

        const resultAction = target.closest(".result-actions .link-button");
        if (resultAction instanceof HTMLElement) {
          const row = resultAction.closest(".result-row");
          if (!(row instanceof HTMLElement)) return;
          const equipmentId = row.dataset.equipmentId || "";
          const text = String(resultAction.textContent || "");
          const eventType = text.includes("eqnet") ? "eqnet_open" : "source_open";
          window.setTimeout(() => {
            logPopularityEvent(equipmentId, eventType, "results_list");
          }, 0);
          return;
        }

        const sheetAction = target.closest(".equipment-sheet-actions .link-button");
        if (sheetAction instanceof HTMLElement) {
          const sheet = sheetAction.closest(".equipment-sheet");
          const equipmentId = sheet instanceof HTMLElement ? sheet.dataset.equipmentId || "" : "";
          const text = String(sheetAction.textContent || "");
          const eventType = text.includes("eqnet") ? "eqnet_open" : "source_open";
          window.setTimeout(() => {
            logPopularityEvent(equipmentId, eventType, "equipment_sheet");
          }, 0);
          return;
        }

        const row = target.closest(".result-row");
        if (row instanceof HTMLElement && !target.closest(".link-button")) {
          const equipmentId = row.dataset.equipmentId || "";
          window.setTimeout(() => {
            logPopularityEvent(equipmentId, "detail_open", "results_list");
          }, 0);
        }
      },
      true
    );

    document.addEventListener(
      "keydown",
      (event) => {
        if (!isHomeRefreshEligible()) return;
        const target = event.target;
        if (!(target instanceof HTMLInputElement)) return;
        if (!target.closest(".search-main")) return;
        if (event.key !== "Enter") return;
        const { searchButton } = getHomeSearchElements();
        if (!(searchButton instanceof HTMLButtonElement)) return;
        event.preventDefault();
        event.stopPropagation();
        handleHomeSearchIntent(searchButton).catch((error) => console.error(error));
      },
      true
    );

    document.addEventListener("keydown", (event) => {
      if (!isHomeRefreshEligible()) return;
      if (event.key !== "Escape") return;
      if (!isHomeSearchSheetOpen()) return;
      closeHomeSearchSheet();
    });

    document.addEventListener("keydown", (event) => {
      if (!isHomeRefreshEligible()) return;
      const target = event.target;
      if (!(target instanceof HTMLElement)) return;
      if (!target.matches(".home-popular-card")) return;
      if (event.key !== "Enter" && event.key !== " ") return;
      event.preventDefault();
      handlePopularCardDetail({
        equipmentId: target.dataset.equipmentId || "",
        name: target.dataset.name || "",
        prefecture: target.dataset.prefecture || "",
        orgName: target.dataset.orgName || "",
        categoryGeneral: target.dataset.categoryGeneral || "",
        sourceUrl: target.dataset.sourceUrl || "",
        eqnetUrl: target.dataset.eqnetUrl || "",
        externalUse: target.dataset.externalUse || "",
        feeBand: target.dataset.feeBand || "",
      });
    });
  }

  function installHomeRefresh() {
    if (!isHomeRefreshEligible()) return;
    removeLegacyFeatureSection();
    ensureHomeAnchors();
    installHomeStickyHeader();
    installSearchDisclosure();
    installHomeDisclosureScrollWatcher();
    installHomeSheetVisibilityWatcher();
    ensureHomeDiscoverySection();
    installHomeFooter();
    installHomeRowAnnotationWatcher();
    installHomeInteractionBindings();
    renderHomeDiscovery().catch((error) => console.error(error));
    updateSearchDisclosureState();
    scheduleHomeSearchFabVisibilitySync();
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
      if (!document.querySelector(".equipment-sheet.is-open .equipment-sheet-panel")) return;
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

    waitForElement(".footer", () => {
      installHomeRefresh();
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
