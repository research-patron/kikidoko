import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  collection,
  doc,
  getDoc,
  getDocs,
  limit,
  orderBy,
  query as firestoreQuery,
  startAfter,
  where,
} from "firebase/firestore";
import "./App.css";
import { db } from "./firebase";

const REGION_ORDER = [
  "北海道",
  "東北",
  "関東",
  "中部",
  "関西",
  "中国",
  "四国",
  "九州",
  "沖縄",
];

const PREFECTURE_COORDS = {
  北海道: { lat: 43.06417, lng: 141.34694 },
  青森県: { lat: 40.82444, lng: 140.74 },
  岩手県: { lat: 39.70361, lng: 141.1525 },
  宮城県: { lat: 38.26889, lng: 140.87194 },
  秋田県: { lat: 39.71861, lng: 140.1025 },
  山形県: { lat: 38.24056, lng: 140.36333 },
  福島県: { lat: 37.75, lng: 140.46778 },
  茨城県: { lat: 36.34139, lng: 140.44667 },
  栃木県: { lat: 36.56583, lng: 139.88361 },
  群馬県: { lat: 36.39111, lng: 139.06083 },
  埼玉県: { lat: 35.85694, lng: 139.64889 },
  千葉県: { lat: 35.60472, lng: 140.12333 },
  東京都: { lat: 35.68944, lng: 139.69167 },
  神奈川県: { lat: 35.44778, lng: 139.6425 },
  新潟県: { lat: 37.90222, lng: 139.02361 },
  富山県: { lat: 36.69528, lng: 137.21139 },
  石川県: { lat: 36.59444, lng: 136.62556 },
  福井県: { lat: 36.06528, lng: 136.22194 },
  山梨県: { lat: 35.66389, lng: 138.56833 },
  長野県: { lat: 36.65139, lng: 138.18111 },
  岐阜県: { lat: 35.39111, lng: 136.72222 },
  静岡県: { lat: 34.97694, lng: 138.38306 },
  愛知県: { lat: 35.18028, lng: 136.90667 },
  三重県: { lat: 34.73028, lng: 136.50861 },
  滋賀県: { lat: 35.00444, lng: 135.86833 },
  京都府: { lat: 35.02139, lng: 135.75556 },
  大阪府: { lat: 34.68639, lng: 135.52 },
  兵庫県: { lat: 34.69139, lng: 135.18306 },
  奈良県: { lat: 34.68528, lng: 135.83278 },
  和歌山県: { lat: 34.22611, lng: 135.1675 },
  鳥取県: { lat: 35.50361, lng: 134.23833 },
  島根県: { lat: 35.47222, lng: 133.05056 },
  岡山県: { lat: 34.66167, lng: 133.935 },
  広島県: { lat: 34.39639, lng: 132.45944 },
  山口県: { lat: 34.18583, lng: 131.47139 },
  徳島県: { lat: 34.06583, lng: 134.55944 },
  香川県: { lat: 34.34028, lng: 134.04333 },
  愛媛県: { lat: 33.84167, lng: 132.76611 },
  高知県: { lat: 33.55972, lng: 133.53111 },
  福岡県: { lat: 33.60639, lng: 130.41806 },
  佐賀県: { lat: 33.24944, lng: 130.29889 },
  長崎県: { lat: 32.74472, lng: 129.87361 },
  熊本県: { lat: 32.78972, lng: 130.74167 },
  大分県: { lat: 33.23806, lng: 131.6125 },
  宮崎県: { lat: 31.91111, lng: 131.42389 },
  鹿児島県: { lat: 31.56028, lng: 130.55806 },
  沖縄県: { lat: 26.2125, lng: 127.68111 },
};

const PREFECTURE_REGION_MAP = {
  北海道: "北海道",
  青森県: "東北",
  岩手県: "東北",
  宮城県: "東北",
  秋田県: "東北",
  山形県: "東北",
  福島県: "東北",
  茨城県: "関東",
  栃木県: "関東",
  群馬県: "関東",
  埼玉県: "関東",
  千葉県: "関東",
  東京都: "関東",
  神奈川県: "関東",
  新潟県: "中部",
  富山県: "中部",
  石川県: "中部",
  福井県: "中部",
  山梨県: "中部",
  長野県: "中部",
  岐阜県: "中部",
  静岡県: "中部",
  愛知県: "中部",
  三重県: "中部",
  滋賀県: "関西",
  京都府: "関西",
  大阪府: "関西",
  兵庫県: "関西",
  奈良県: "関西",
  和歌山県: "関西",
  鳥取県: "中国",
  島根県: "中国",
  岡山県: "中国",
  広島県: "中国",
  山口県: "中国",
  徳島県: "四国",
  香川県: "四国",
  愛媛県: "四国",
  高知県: "四国",
  福岡県: "九州",
  佐賀県: "九州",
  長崎県: "九州",
  熊本県: "九州",
  大分県: "九州",
  宮崎県: "九州",
  鹿児島県: "九州",
  沖縄県: "沖縄",
};

const GOOGLE_MAPS_API_KEY = import.meta.env.VITE_GOOGLE_MAPS_API_KEY || "";
const JAPAN_CENTER = { lat: 36.2048, lng: 138.2529 };
const JAPAN_BOUNDS = {
  north: 46.2,
  south: 24.0,
  west: 122.5,
  east: 153.9,
};
const MAP_DEFAULT_ZOOM = 5;
const MAP_MIN_ZOOM = 4;
const MAP_MAX_ZOOM = 17;
const TOKEN_PATTERN = /[A-Za-z0-9]+|[ぁ-んァ-ン一-龥々ー]+/g;

const loadGoogleMaps = (apiKey) => {
  if (!apiKey) {
    return Promise.reject(new Error("Google Maps API key is missing."));
  }
  if (window.google?.maps) {
    return Promise.resolve(window.google.maps);
  }
  if (window.__kikidokoMapsPromise) {
    return window.__kikidokoMapsPromise;
  }
  window.__kikidokoMapsPromise = new Promise((resolve, reject) => {
    const script = document.createElement("script");
    script.src = `https://maps.googleapis.com/maps/api/js?key=${apiKey}&region=JP&language=ja&v=weekly`;
    script.async = true;
    script.defer = true;
    script.onload = () => resolve(window.google.maps);
    script.onerror = () => reject(new Error("Failed to load Google Maps."));
    document.head.appendChild(script);
  });
  return window.__kikidokoMapsPromise;
};

const NORMALIZED_KEYWORDS = {
  xrd: [
    "xrd",
    "x線回折",
    "x線回折装置",
    "x線回折測定",
    "x-ray diffraction",
    "xray diffraction",
    "x-ray diffractometer",
    "xray diffractometer",
  ],
  sem: ["sem", "走査型電子顕微鏡", "走査電子顕微鏡"],
  tem: ["tem", "透過型電子顕微鏡", "透過電子顕微鏡"],
  xps: ["xps", "x線光電子分光", "x線光電子分光法"],
  nmr: ["nmr", "核磁気共鳴", "核磁気共鳴装置"],
  ftir: ["ftir", "フーリエ変換赤外分光", "フーリエ変換赤外分光法"],
  afm: ["afm", "原子間力顕微鏡"],
  lcms: ["lcms", "液体クロマトグラフ質量分析", "液クロ質量分析"],
  gcms: ["gcms", "ガスクロマトグラフ質量分析", "ガスクロ質量分析"],
};

const PAPER_GENRE_LABELS = {
  CHEM: "化学",
  PHYS: "物理学・天文学",
  CENG: "化学工学",
  ENGI: "工学",
  MATE: "材料科学",
  COMP: "コンピュータ科学",
  MATH: "数学",
  EART: "地球・惑星科学",
  ENVI: "環境科学",
  AGRI: "農学・生物科学",
  BIOC: "生化学・遺伝・分子生物学",
  IMMU: "免疫学・微生物学",
  PHAR: "薬学・毒性学・製剤学",
  MEDI: "医学",
  NURS: "看護学",
  DENT: "歯学",
  HEAL: "保健医療",
  VETE: "獣医学",
  NEUR: "神経科学",
  PSYC: "心理学",
  SOCI: "社会科学",
  ARTS: "芸術・人文科学",
  BUSI: "ビジネス・経営・会計",
  DECI: "意思決定科学",
  ECON: "経済・計量経済・金融",
  ENER: "エネルギー",
  MULT: "学際領域",
};

const PAPER_GENRE_NAME_LABELS = [
  ["chemical engineering", "化学工学"],
  ["materials science", "材料科学"],
  ["physics and astronomy", "物理学・天文学"],
  ["computer science", "コンピュータ科学"],
  ["earth and planetary", "地球・惑星科学"],
  ["environmental science", "環境科学"],
  ["agricultural and biological sciences", "農学・生物科学"],
  ["biochemistry, genetics and molecular biology", "生化学・遺伝・分子生物学"],
  ["immunology and microbiology", "免疫学・微生物学"],
  ["pharmacology, toxicology and pharmaceutics", "薬学・毒性学・製剤学"],
  ["business, management and accounting", "ビジネス・経営・会計"],
  ["economics, econometrics and finance", "経済・計量経済・金融"],
  ["decision sciences", "意思決定科学"],
  ["arts and humanities", "芸術・人文科学"],
  ["social sciences", "社会科学"],
  ["energy", "エネルギー"],
  ["engineering", "工学"],
  ["chemistry", "化学"],
  ["mathematics", "数学"],
  ["medicine", "医学"],
  ["nursing", "看護学"],
  ["dentistry", "歯学"],
  ["health professions", "保健医療"],
  ["veterinary", "獣医学"],
  ["neuroscience", "神経科学"],
  ["psychology", "心理学"],
];

const JAPANESE_PATTERN = /[ぁ-んァ-ン一-龥]/;

const USAGE_THEME_LABELS = {
  diffraction: "回折",
  microscopy: "顕微鏡観察",
  spectrometry: "質量分析",
  spectroscopy: "分光",
  thermal: "熱特性",
  electrical: "電気特性",
  magnetic: "磁気特性",
  optical: "光学特性",
  surface: "表面",
  structure: "構造",
  structural: "構造",
  mechanical: "機械特性",
  corrosion: "腐食",
  catalyst: "触媒",
  catalytic: "触媒反応",
  battery: "電池",
  batteries: "電池",
  semiconductor: "半導体",
  semiconductors: "半導体",
  polymer: "ポリマー",
  polymers: "ポリマー",
  alloy: "合金",
  alloys: "合金",
  ceramic: "セラミック",
  ceramics: "セラミック",
  nanomaterial: "ナノ材料",
  nanomaterials: "ナノ材料",
  nanoparticle: "ナノ粒子",
  nanoparticles: "ナノ粒子",
  thinfilm: "薄膜",
  thinfilms: "薄膜",
  coating: "コーティング",
  coatings: "コーティング",
  sensor: "センサー",
  sensors: "センサー",
  imaging: "イメージング",
  characterization: "特性評価",
  evaluation: "評価",
};

const resolvePaperGenre = (value) => {
  const raw = String(value || "").trim();
  if (!raw) return "未分類";
  if (JAPANESE_PATTERN.test(raw)) return raw;
  const upper = raw.toUpperCase();
  if (PAPER_GENRE_LABELS[upper]) {
    return PAPER_GENRE_LABELS[upper];
  }
  const lower = raw.toLowerCase();
  if (lower === "uncategorized" || lower === "unclassified" || lower === "unknown") {
    return "未分類";
  }
  for (const [needle, label] of PAPER_GENRE_NAME_LABELS) {
    if (lower.includes(needle)) {
      return label;
    }
  }
  return raw;
};

const resolveUsageTheme = (value) => {
  const raw = String(value || "").trim();
  if (!raw) return "";
  if (JAPANESE_PATTERN.test(raw)) return raw;
  const normalized = raw.toLowerCase().replace(/[^a-z0-9]+/g, "");
  if (USAGE_THEME_LABELS[normalized]) {
    return USAGE_THEME_LABELS[normalized];
  }
  return raw.replace(/-/g, " ");
};

const EQUIPMENT_GUIDES = {
  xrd: {
    title: "X線回折（XRD）",
    summary: "結晶構造や相の同定に使われる分析手法です。",
    bullets: ["結晶相の同定", "結晶性や結晶サイズの評価", "処理条件による変化の追跡"],
  },
  sem: {
    title: "走査型電子顕微鏡（SEM）",
    summary: "試料表面の微細構造を観察する装置です。",
    bullets: ["表面形状の観察", "微細構造の撮影", "元素分析（EDS）の補助"],
  },
  tem: {
    title: "透過型電子顕微鏡（TEM）",
    summary: "ナノスケールの内部構造を観察する装置です。",
    bullets: ["ナノ構造の観察", "結晶格子像の取得", "電子回折による解析"],
  },
  xps: {
    title: "X線光電子分光（XPS）",
    summary: "材料表面の元素と化学状態を解析します。",
    bullets: ["表面元素の同定", "化学結合状態の解析", "薄膜・汚染評価"],
  },
  nmr: {
    title: "核磁気共鳴（NMR）",
    summary: "分子構造や組成を解析する装置です。",
    bullets: ["分子構造の解析", "化学シフトの評価", "純度・組成の確認"],
  },
  ftir: {
    title: "フーリエ変換赤外分光（FT-IR）",
    summary: "官能基や材料の状態を調べる分析手法です。",
    bullets: ["官能基の同定", "材料の劣化評価", "有機・高分子材料の解析"],
  },
  afm: {
    title: "原子間力顕微鏡（AFM）",
    summary: "表面形状や物性をナノスケールで測定します。",
    bullets: ["表面粗さの測定", "ナノ形状の観察", "局所物性の評価"],
  },
  lcms: {
    title: "液体クロマトグラフ質量分析（LC-MS）",
    summary: "分離と質量分析で複雑試料を解析します。",
    bullets: ["低揮発性化合物の分析", "微量成分の定量", "複雑試料の同定"],
  },
  gcms: {
    title: "ガスクロマトグラフ質量分析（GC-MS）",
    summary: "揮発性成分の同定・定量に用いられます。",
    bullets: ["揮発性成分の分析", "不純物の同定", "環境・化学試料の解析"],
  },
};

const normalizeKeyword = (value) => {
  return value.toLowerCase().replace(/[^a-z0-9ぁ-んァ-ン一-龥々ー]/g, "");
};

const normalizeForMatch = (value) => normalizeKeyword(value || "");

const hasTextMatch = (value, keywordNormalized, tokens) => {
  return (
    scoreTextMatch(value, keywordNormalized, tokens, {
      exact: 1,
      prefix: 1,
      partial: 1,
      token: 1,
    }) > 0
  );
};

const scoreTextMatch = (value, keywordNormalized, tokens, weights) => {
  if (!value) return 0;
  const normalized = normalizeForMatch(value);
  if (!normalized) return 0;
  let score = 0;
  if (keywordNormalized) {
    if (normalized === keywordNormalized) {
      score += weights.exact;
    } else if (normalized.startsWith(keywordNormalized)) {
      score += weights.prefix;
    } else if (normalized.includes(keywordNormalized)) {
      score += weights.partial;
    }
  }
  if (tokens.length > 0) {
    const hits = new Set();
    tokens.forEach((token) => {
      if (token.length < 2) return;
      if (normalized.includes(token)) {
        hits.add(token);
      }
    });
    score += hits.size * weights.token;
  }
  return score;
};

const buildMatchTier = (item, keywordNormalized, tokens, aliasKeys) => {
  if (!item || (!keywordNormalized && tokens.length === 0)) return 0;
  const normalizedName = normalizeForMatch(item.name);
  if (keywordNormalized && normalizedName && normalizedName === keywordNormalized) {
    return 3;
  }
  const aliasMatch =
    aliasKeys.length > 0 &&
    Array.isArray(item.searchAliases) &&
    item.searchAliases.some((alias) => aliasKeys.includes(alias));
  const primaryMatch =
    aliasMatch ||
    hasTextMatch(item.name, keywordNormalized, tokens) ||
    hasTextMatch(item.categoryGeneral, keywordNormalized, tokens) ||
    hasTextMatch(item.categoryDetail, keywordNormalized, tokens) ||
    hasTextMatch(item.orgName, keywordNormalized, tokens) ||
    hasTextMatch(item.prefecture, keywordNormalized, tokens) ||
    hasTextMatch(item.address, keywordNormalized, tokens) ||
    hasTextMatch(item.orgType, keywordNormalized, tokens) ||
    hasTextMatch(item.feeBand, keywordNormalized, tokens);
  if (primaryMatch) {
    return 2;
  }
  const descriptionText = [
    item.usageManualSummary,
    ...(Array.isArray(item.usageManualBullets) ? item.usageManualBullets : []),
  ]
    .filter(Boolean)
    .join(" ");
  if (hasTextMatch(descriptionText, keywordNormalized, tokens)) {
    return 1;
  }
  return 0;
};

const buildSearchScore = (item, keywordNormalized, tokens, aliasKeys) => {
  if (!item || (!keywordNormalized && tokens.length === 0)) return 0;
  let score = 0;
  score += scoreTextMatch(item.name, keywordNormalized, tokens, {
    exact: 1200,
    prefix: 900,
    partial: 700,
    token: 60,
  });
  score += scoreTextMatch(item.categoryGeneral, keywordNormalized, tokens, {
    exact: 420,
    prefix: 320,
    partial: 240,
    token: 20,
  });
  score += scoreTextMatch(item.categoryDetail, keywordNormalized, tokens, {
    exact: 360,
    prefix: 260,
    partial: 200,
    token: 16,
  });
  score += scoreTextMatch(item.orgName, keywordNormalized, tokens, {
    exact: 320,
    prefix: 240,
    partial: 180,
    token: 14,
  });
  score += scoreTextMatch(item.prefecture, keywordNormalized, tokens, {
    exact: 180,
    prefix: 140,
    partial: 100,
    token: 8,
  });
  score += scoreTextMatch(item.address, keywordNormalized, tokens, {
    exact: 140,
    prefix: 110,
    partial: 80,
    token: 6,
  });
  score += scoreTextMatch(item.orgType, keywordNormalized, tokens, {
    exact: 120,
    prefix: 90,
    partial: 70,
    token: 5,
  });
  score += scoreTextMatch(item.feeBand, keywordNormalized, tokens, {
    exact: 80,
    prefix: 60,
    partial: 40,
    token: 4,
  });
  if (
    aliasKeys.length > 0 &&
    Array.isArray(item.searchAliases) &&
    item.searchAliases.some((alias) => aliasKeys.includes(alias))
  ) {
    score += 500;
  }
  const descriptionText = [
    item.usageManualSummary,
    ...(Array.isArray(item.usageManualBullets) ? item.usageManualBullets : []),
  ]
    .filter(Boolean)
    .join(" ");
  score += scoreTextMatch(descriptionText, keywordNormalized, tokens, {
    exact: 40,
    prefix: 24,
    partial: 16,
    token: 3,
  });
  return score;
};

const detectAliasKeys = (value) => {
  const raw = value || "";
  const compact = normalizeKeyword(raw);
  if (!compact) return [];
  const tokens = (raw.toLowerCase().match(TOKEN_PATTERN) || [])
    .map((token) => normalizeKeyword(token))
    .filter(Boolean);
  const tokenSet = new Set(tokens);
  return Object.entries(NORMALIZED_KEYWORDS)
    .filter(([key, terms]) => {
      const variants = [key, ...terms];
      return variants.some((term) => {
        const normalized = normalizeKeyword(term);
        if (!normalized || normalized.length <= 1) return false;
        if (normalized.length <= 3) {
          return tokenSet.has(normalized);
        }
        return compact.includes(normalized);
      });
    })
    .map(([key]) => key);
};

const EQNET_BASE_URL = "https://eqnet.jp";
const PAGE_SIZE = 6;

const badgeClass = (value) => {
  if (value === "可") return "badge badge-ok";
  if (value === "要相談") return "badge badge-warn";
  return "badge badge-muted";
};

const externalLabel = (value) => {
  return value || "不明";
};

const buildReferenceUsage = (item) => {
  if (!item) return null;
  const themes = Array.isArray(item.usageThemes) ? item.usageThemes : [];
  const genres = Array.isArray(item.usageGenres) ? item.usageGenres : [];
  const themeLabels = themes
    .map(resolveUsageTheme)
    .filter(Boolean)
    .slice(0, 2);
  const genreLabels = genres
    .map(resolvePaperGenre)
    .filter(Boolean)
    .slice(0, 2);
  if (themeLabels.length === 0 && genreLabels.length === 0) {
    return null;
  }
  const summaryParts = [];
  if (themeLabels.length > 0) {
    summaryParts.push(`主題: ${themeLabels.join("・")}`);
  }
  if (genreLabels.length > 0) {
    summaryParts.push(`分野: ${genreLabels.join("・")}`);
  }
  const summary = `参考文献の題名から抽出した${summaryParts.join(
    "、",
  )}を基に用途を整理しています。`;
  const bullets = [];
  themeLabels.forEach((theme) => {
    bullets.push(`主題例: ${theme}`);
  });
  if (genreLabels.length > 0) {
    bullets.push(`関連分野: ${genreLabels.join(" / ")}`);
  }
  return { summary, bullets };
};

const buildEquipmentGuide = (item) => {
  const referenceUsage = buildReferenceUsage(item);
  const manualSummary = item?.usageManualSummary || "";
  const manualBullets = Array.isArray(item?.usageManualBullets)
    ? item.usageManualBullets.filter(Boolean)
    : [];
  const applyManual = (guide) => {
    if (!manualSummary && manualBullets.length === 0) {
      return guide;
    }
    return {
      ...guide,
      summary: manualSummary || guide.summary,
      bullets: manualBullets.length > 0 ? manualBullets : guide.bullets,
    };
  };
  if (!item) {
    return applyManual({
      title: "研究機器の概要",
      summary: "研究開発の基礎データを得るために使われます。",
      bullets: ["測定・解析の基本データ取得", "条件や材料の比較評価", "研究開発の仮説検証"],
    });
  }
  const combined = `${item.name || ""} ${item.categoryGeneral || ""} ${item.categoryDetail || ""}`;
  const aliasKey = detectAliasKeys(combined)[0];
  if (aliasKey && EQUIPMENT_GUIDES[aliasKey]) {
    const guide = EQUIPMENT_GUIDES[aliasKey];
    const guided = referenceUsage
      ? { ...guide, summary: referenceUsage.summary, bullets: referenceUsage.bullets }
      : guide;
    return applyManual(guided);
  }
  const category = item.categoryGeneral || "";
  if (category.includes("分析") || category.includes("解析")) {
    const guide = {
      title: "分析・解析装置",
      summary: "材料の組成や構造を調べるために使われます。",
      bullets: ["物質の同定と分類", "特性差の比較評価", "プロセス条件の検討"],
    };
    const guided = referenceUsage
      ? { ...guide, summary: referenceUsage.summary, bullets: referenceUsage.bullets }
      : guide;
    return applyManual(guided);
  }
  if (category.includes("計測") || category.includes("測定")) {
    const guide = {
      title: "計測・測定装置",
      summary: "寸法や物性などを定量的に評価します。",
      bullets: ["寸法・形状の測定", "物性値の評価", "変化のモニタリング"],
    };
    const guided = referenceUsage
      ? { ...guide, summary: referenceUsage.summary, bullets: referenceUsage.bullets }
      : guide;
    return applyManual(guided);
  }
  if (category.includes("評価")) {
    const guide = {
      title: "評価装置",
      summary: "性能や品質を比較・判定するために使われます。",
      bullets: ["性能・品質の評価", "条件比較と検証", "信頼性の確認"],
    };
    const guided = referenceUsage
      ? { ...guide, summary: referenceUsage.summary, bullets: referenceUsage.bullets }
      : guide;
    return applyManual(guided);
  }
  if (category.includes("加工") || category.includes("試作") || category.includes("製作")) {
    const guide = {
      title: "加工・試作装置",
      summary: "試作や加工プロセスの検討に活用されます。",
      bullets: ["試作プロセスの検討", "加工条件の最適化", "試料作製の支援"],
    };
    const guided = referenceUsage
      ? { ...guide, summary: referenceUsage.summary, bullets: referenceUsage.bullets }
      : guide;
    return applyManual(guided);
  }
  const guide = {
    title: "研究機器の概要",
    summary: "研究開発の基礎データを得るために使われます。",
    bullets: ["測定・解析の基本データ取得", "条件や材料の比較評価", "研究開発の仮説検証"],
  };
  const guided = referenceUsage
    ? { ...guide, summary: referenceUsage.summary, bullets: referenceUsage.bullets }
    : guide;
  return applyManual(guided);
};

const feeLabel = (value) => {
  if (!value || value === "不明") return "料金要相談";
  return value;
};

const formatDate = (value) => {
  if (!value) return "未設定";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "未設定";
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}.${month}.${day}`;
};

const formatDistance = (distanceKm) => {
  if (distanceKm == null) return "距離未計算";
  if (distanceKm < 1) return "1km未満";
  return `${Math.round(distanceKm)}km`;
};

const escapeHtml = (value) => {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
};

const toRad = (value) => (value * Math.PI) / 180;

const getDistanceKm = (from, to) => {
  if (!from || !to) return null;
  const earthRadiusKm = 6371;
  const dLat = toRad(to.lat - from.lat);
  const dLng = toRad(to.lng - from.lng);
  const fromLat = toRad(from.lat);
  const toLat = toRad(to.lat);
  const a =
    Math.sin(dLat / 2) * Math.sin(dLat / 2) +
    Math.sin(dLng / 2) * Math.sin(dLng / 2) * Math.cos(fromLat) * Math.cos(toLat);
  const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
  return earthRadiusKm * c;
};

const buildEqnetLink = (item) => {
  if (item.eqnetUrl) return item.eqnetUrl;
  return EQNET_BASE_URL;
};

export default function App() {
  const [pages, setPages] = useState([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [keywordInput, setKeywordInput] = useState("");
  const [keyword, setKeyword] = useState("");
  const [latestUpdate, setLatestUpdate] = useState("未設定");
  const [prefectureSummary, setPrefectureSummary] = useState([]);
  const [prefectureSummaryLoaded, setPrefectureSummaryLoaded] = useState(false);
  const [prefectureFilter, setPrefectureFilter] = useState("");
  const [region, setRegion] = useState("all");
  const [category, setCategory] = useState("all");
  const [externalOnly, setExternalOnly] = useState(false);
  const [freeOnly, setFreeOnly] = useState(false);
  const [page, setPage] = useState(1);
  const [activeExternal, setActiveExternal] = useState(null);
  const [mapsReady, setMapsReady] = useState(false);
  const [mapsError, setMapsError] = useState("");
  const [detailItem, setDetailItem] = useState(null);
  const [detailOpen, setDetailOpen] = useState(false);
  const [sheetExpanded, setSheetExpanded] = useState(false);
  const [selectedItemId, setSelectedItemId] = useState(null);
  const [exactMatches, setExactMatches] = useState([]);
  const [userLocation, setUserLocation] = useState(null);
  const [locationStatus, setLocationStatus] = useState("idle");
  const [locationError, setLocationError] = useState("");
  const [isComposing, setIsComposing] = useState(false);
  const pagingRef = useRef(false);
  const pagesRef = useRef(pages);
  const mapRef = useRef(null);
  const mapInstanceRef = useRef(null);
  const markersRef = useRef(new Map());
  const infoWindowRef = useRef(null);
  const listItemRefs = useRef(new Map());
  const resultsRef = useRef(null);
  const sheetTouchStartRef = useRef(null);
  const prefectureSnapshotRef = useRef(null);

  useEffect(() => {
    setPage(1);
  }, [keyword, region, category, externalOnly, freeOnly, prefectureFilter]);

  useEffect(() => {
    pagesRef.current = pages;
  }, [pages]);

  useEffect(() => {
    if (!GOOGLE_MAPS_API_KEY) {
      setMapsError("Google Maps APIキーが未設定です。");
      return;
    }
    let cancelled = false;
    loadGoogleMaps(GOOGLE_MAPS_API_KEY)
      .then(() => {
        if (!cancelled) {
          setMapsReady(true);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setMapsError("Google Mapsの読み込みに失敗しました。");
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!activeExternal) return undefined;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = previousOverflow;
    };
  }, [activeExternal]);

  useEffect(() => {
    if (!activeExternal && !detailOpen) {
      document.body.style.overflow = "";
      document.documentElement.style.overflow = "";
    }
  }, [activeExternal, detailOpen]);

  useEffect(() => {
    if (!detailOpen) {
      setSheetExpanded(false);
    }
  }, [detailOpen]);

  useEffect(() => {
    if (activeExternal && detailOpen) {
      setDetailOpen(false);
    }
  }, [activeExternal, detailOpen]);

  useEffect(() => {
    if (!activeExternal) return undefined;
    const handleKeyDown = (event) => {
      if (event.key === "Escape") {
        setActiveExternal(null);
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => {
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [activeExternal]);

  useEffect(() => {
    if (!detailOpen) return undefined;
    const handleKeyDown = (event) => {
      if (event.key === "Escape") {
        setDetailOpen(false);
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => {
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [detailOpen]);

  useEffect(() => {
    if (detailItem && !detailOpen) {
      const timer = setTimeout(() => setDetailItem(null), 240);
      return () => clearTimeout(timer);
    }
    return undefined;
  }, [detailItem, detailOpen]);

  useEffect(() => {
    if (!mapsReady || !mapRef.current || mapInstanceRef.current) return;
    const isMobile = window.matchMedia("(max-width: 860px)").matches;
    const map = new window.google.maps.Map(mapRef.current, {
      center: JAPAN_CENTER,
      zoom: MAP_DEFAULT_ZOOM,
      minZoom: MAP_MIN_ZOOM,
      maxZoom: MAP_MAX_ZOOM,
      mapTypeControl: false,
      fullscreenControl: false,
      streetViewControl: false,
      gestureHandling: isMobile ? "cooperative" : "auto",
      scrollwheel: !isMobile,
      restriction: {
        latLngBounds: JAPAN_BOUNDS,
        strictBounds: true,
      },
    });
    mapInstanceRef.current = map;
    infoWindowRef.current = new window.google.maps.InfoWindow();
  }, [mapsReady]);

  const handleReset = () => {
    setKeywordInput("");
    setKeyword("");
    setPrefectureFilter("");
    prefectureSnapshotRef.current = null;
    setRegion("all");
    setCategory("all");
    setExternalOnly(false);
    setFreeOnly(false);
    setPage(1);
  };

  const handleSearch = () => {
    const trimmed = keywordInput.trim();
    setKeywordInput(trimmed);
    setKeyword(trimmed);
  };

  const handlePrefectureSelect = (prefecture) => {
    if (!prefecture) return;
    if (!prefectureFilter) {
      prefectureSnapshotRef.current = {
        keywordInput,
        keyword,
        region,
        category,
        externalOnly,
        freeOnly,
      };
    }
    setPrefectureFilter(prefecture);
    setRegion(PREFECTURE_REGION_MAP[prefecture] || "all");
    setPage(1);
    if (resultsRef.current) {
      resultsRef.current.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  };

  const handlePrefectureRestore = () => {
    const snapshot = prefectureSnapshotRef.current;
    setPrefectureFilter("");
    if (snapshot) {
      setKeywordInput(snapshot.keywordInput);
      setKeyword(snapshot.keyword);
      setRegion(snapshot.region);
      setCategory(snapshot.category);
      setExternalOnly(snapshot.externalOnly);
      setFreeOnly(snapshot.freeOnly);
    }
    prefectureSnapshotRef.current = null;
    setPage(1);
  };

  const mapDocToItem = useCallback((doc) => {
    const data = doc.data() || {};
    const rawLat = typeof data.lat === "number" ? data.lat : Number.parseFloat(data.lat);
    const rawLng = typeof data.lng === "number" ? data.lng : Number.parseFloat(data.lng);
    const lat = Number.isFinite(rawLat) ? rawLat : null;
    const lng = Number.isFinite(rawLng) ? rawLng : null;
    return {
      id: data.equipment_id || doc.id,
      name: data.name || "名称不明",
      categoryGeneral: data.category_general || "未分類",
      categoryDetail: data.category_detail || "",
      orgName: data.org_name || "不明",
      orgType: data.org_type || "不明",
      prefecture: data.prefecture || "不明",
      region: data.region || "不明",
      externalUse: data.external_use || "不明",
      feeBand: feeLabel(data.fee_band),
      address: data.address_raw || "所在地不明",
      lat,
      lng,
      sourceUrl: data.source_url || "",
      eqnetUrl: data.eqnet_url || "",
      crawledAt: data.crawled_at || "",
      papers: Array.isArray(data.papers) ? data.papers : [],
      papersStatus: data.papers_status || "",
      papersUpdatedAt: data.papers_updated_at || "",
      papersError: data.papers_error || "",
      searchAliases: Array.isArray(data.search_aliases) ? data.search_aliases : [],
      usageThemes: Array.isArray(data.usage_themes) ? data.usage_themes : [],
      usageGenres: Array.isArray(data.usage_genres) ? data.usage_genres : [],
      usageManualSummary: data.usage_manual_summary || "",
      usageManualBullets: Array.isArray(data.usage_manual_bullets)
        ? data.usage_manual_bullets
        : [],
    };
  }, []);

  useEffect(() => {
    let isMounted = true;
    const loadExactMatches = async () => {
      const trimmed = keyword.trim();
      if (!trimmed) {
        setExactMatches([]);
        return;
      }
      try {
        const exactQuery = firestoreQuery(
          collection(db, "equipment"),
          where("name", "==", trimmed),
          limit(5),
        );
        const snap = await getDocs(exactQuery);
        if (!isMounted) return;
        const matches = snap.docs.map(mapDocToItem);
        const filtered = matches.filter((item) => {
          if (region !== "all" && item.region !== region) return false;
          if (category !== "all" && item.categoryGeneral !== category) return false;
          if (externalOnly && item.externalUse !== "可") return false;
          if (freeOnly && item.feeBand !== "無料") return false;
          if (prefectureFilter && item.prefecture !== prefectureFilter) return false;
          return true;
        });
        setExactMatches(filtered);
      } catch (error) {
        console.error(error);
        if (isMounted) {
          setExactMatches([]);
        }
      }
    };
    loadExactMatches();
    return () => {
      isMounted = false;
    };
  }, [
    category,
    externalOnly,
    freeOnly,
    keyword,
    mapDocToItem,
    prefectureFilter,
    region,
  ]);

  useEffect(() => {
    let isMounted = true;
    const loadLatestUpdate = async () => {
      try {
        const latestQuery = firestoreQuery(
          collection(db, "equipment"),
          orderBy("crawled_at", "desc"),
          limit(1),
        );
        const latestSnap = await getDocs(latestQuery);
        const latestDoc = latestSnap.docs[0];
        const latestValue = latestDoc?.data()?.crawled_at || "";
        if (isMounted) {
          setLatestUpdate(formatDate(latestValue));
        }
      } catch (error) {
        console.error(error);
      }
    };
    loadLatestUpdate();
    return () => {
      isMounted = false;
    };
  }, []);

  useEffect(() => {
    let isMounted = true;
    const loadPrefectureSummary = async () => {
      try {
        const summarySnap = await getDoc(doc(db, "stats", "prefecture_summary"));
        const data = summarySnap.exists() ? summarySnap.data() : null;
        const items = Array.isArray(data?.top_prefectures) ? data.top_prefectures : [];
        if (isMounted) {
          setPrefectureSummary(items);
        }
      } catch (error) {
        console.error(error);
      } finally {
        if (isMounted) {
          setPrefectureSummaryLoaded(true);
        }
      }
    };
    loadPrefectureSummary();
    return () => {
      isMounted = false;
    };
  }, []);

  const buildKeywordTokens = useCallback((value) => {
    const normalized = value.trim().toLowerCase();
    if (!normalized) return [];
    const tokens = new Set();
    const japanesePattern = /[ぁ-んァ-ン一-龥々ー]/;
    const addTermTokens = (term) => {
      if (!term) return;
      if (/^[a-z0-9]+$/i.test(term) && term.length <= 1) return;
      tokens.add(term);
      if (japanesePattern.test(term)) {
        const compact = term.replace(/\s+/g, "");
        for (let size = 2; size <= 3; size += 1) {
          for (let index = 0; index <= compact.length - size; index += 1) {
            tokens.add(compact.slice(index, index + size));
          }
        }
      }
    };
    const addFromText = (text) => {
      if (!text) return;
      const matches = text.match(TOKEN_PATTERN);
      if (!matches) return;
      matches.forEach((match) => addTermTokens(match.toLowerCase()));
    };

    addFromText(normalized);
    return Array.from(tokens).slice(0, 10);
  }, []);

  const keywordTokens = useMemo(() => buildKeywordTokens(keyword), [buildKeywordTokens, keyword]);
  const aliasKeys = useMemo(() => detectAliasKeys(keyword), [keyword]);
  const normalizedKeyword = useMemo(() => normalizeForMatch(keyword), [keyword]);
  const normalizedKeywordTokens = useMemo(
    () => keywordTokens.map((token) => normalizeForMatch(token)).filter(Boolean),
    [keywordTokens],
  );

  const buildBaseQuery = useCallback(
    (tokens) => {
      const constraints = [];
      if (region !== "all") {
        constraints.push(where("region", "==", region));
      }
      if (category !== "all") {
        constraints.push(where("category_general", "==", category));
      }
      if (externalOnly) {
        constraints.push(where("external_use", "==", "可"));
      }
      if (freeOnly) {
        constraints.push(where("fee_band", "==", "無料"));
      }
      if (prefectureFilter) {
        constraints.push(where("prefecture", "==", prefectureFilter));
      }
      if (aliasKeys.length > 0) {
        constraints.push(where("search_aliases", "array-contains-any", aliasKeys));
      } else if (tokens.length > 0) {
        constraints.push(where("search_tokens", "array-contains-any", tokens));
      }
      if (tokens.length === 0 && aliasKeys.length === 0) {
        constraints.push(orderBy("name"));
      }
      return firestoreQuery(collection(db, "equipment"), ...constraints);
    },
    [aliasKeys, category, externalOnly, freeOnly, prefectureFilter, region],
  );

  const loadPage = useCallback(
    async ({ pageIndex, cursor, reset }) => {
      setLoading(true);
      setLoadError("");
      try {
        const baseQuery = buildBaseQuery(keywordTokens);
        let pageQuery = baseQuery;
        if (cursor) {
          pageQuery = firestoreQuery(pageQuery, startAfter(cursor));
        }
        pageQuery = firestoreQuery(pageQuery, limit(PAGE_SIZE + 1));
        const snapshot = await getDocs(pageQuery);
        const docs = snapshot.docs;
        const hasNext = docs.length > PAGE_SIZE;
        const pageDocs = hasNext ? docs.slice(0, PAGE_SIZE) : docs;
        const pageItems = pageDocs.map(mapDocToItem);
        const lastDoc = pageDocs.length ? pageDocs[pageDocs.length - 1] : null;
        setPages((prev) => {
          const next = reset ? [] : [...prev];
          next[pageIndex] = { items: pageItems, lastDoc, hasNext };
          pagesRef.current = next;
          return next;
        });
      } catch (error) {
        console.error(error);
        setLoadError("データ取得に失敗しました。時間をおいて再読み込みしてください。");
      } finally {
        setLoading(false);
      }
    },
    [buildBaseQuery, keywordTokens, mapDocToItem],
  );

  useEffect(() => {
    let isMounted = true;
    const loadFirstPage = async () => {
      setLoading(true);
      setLoadError("");
      setPages([]);
      pagesRef.current = [];
      setSelectedItemId(null);
      try {
        const baseQuery = buildBaseQuery(keywordTokens);
        const pageQuery = firestoreQuery(baseQuery, limit(PAGE_SIZE + 1));
        const pageSnap = await getDocs(pageQuery);
        if (!isMounted) return;
        const docs = pageSnap.docs;
        const hasNext = docs.length > PAGE_SIZE;
        const pageDocs = hasNext ? docs.slice(0, PAGE_SIZE) : docs;
        const pageItems = pageDocs.map(mapDocToItem);
        const lastDoc = pageDocs.length ? pageDocs[pageDocs.length - 1] : null;
        const nextPages = [{ items: pageItems, lastDoc, hasNext }];
        setPages(nextPages);
        pagesRef.current = nextPages;
        setPage(1);
      } catch (error) {
        console.error(error);
        if (isMounted) {
          setLoadError("データ取得に失敗しました。時間をおいて再読み込みしてください。");
        }
      } finally {
        if (isMounted) {
          setLoading(false);
        }
      }
    };
    loadFirstPage();
    return () => {
      isMounted = false;
    };
  }, [buildBaseQuery, keywordTokens, mapDocToItem]);

  const handleExternalOpen = (item) => {
    if (!item.sourceUrl) return;
    setActiveExternal({
      url: item.sourceUrl,
      name: item.name,
      orgName: item.orgName,
    });
  };

  const handleExternalClose = () => {
    setActiveExternal(null);
  };

  const requestLocation = () => {
    if (!navigator.geolocation) {
      setLocationError("このブラウザでは位置情報が利用できません。");
      setLocationStatus("error");
      return;
    }
    setLocationStatus("loading");
    setLocationError("");
    navigator.geolocation.getCurrentPosition(
      (position) => {
        setUserLocation({
          lat: position.coords.latitude,
          lng: position.coords.longitude,
        });
        setLocationStatus("ready");
      },
      () => {
        setLocationError("現在地の取得に失敗しました。許可設定をご確認ください。");
        setLocationStatus("error");
      },
      { enableHighAccuracy: false, timeout: 12000, maximumAge: 600000 },
    );
  };

  const currentPageData = useMemo(() => {
    return pages[page - 1] || { items: [], hasNext: false, lastDoc: null };
  }, [pages, page]);

  const lastLoadedIndex = useMemo(() => {
    let last = -1;
    pages.forEach((pageData, index) => {
      if (pageData) last = index;
    });
    return last;
  }, [pages]);

  const loadedPageCount = lastLoadedIndex + 1;

  const currentItems = useMemo(() => {
    return currentPageData.items || [];
  }, [currentPageData]);

  const combinedItems = useMemo(() => {
    if (exactMatches.length === 0) {
      return currentItems;
    }
    const map = new Map();
    exactMatches.forEach((item) => map.set(item.id, item));
    currentItems.forEach((item) => {
      if (!map.has(item.id)) {
        map.set(item.id, item);
      }
    });
    return Array.from(map.values());
  }, [currentItems, exactMatches]);

  const rankedItems = useMemo(() => {
    if (!normalizedKeyword && normalizedKeywordTokens.length === 0) {
      return combinedItems.map((item) => ({ ...item, searchScore: 0, matchTier: 0 }));
    }
    const scored = combinedItems.map((item) => {
      const matchTier = buildMatchTier(
        item,
        normalizedKeyword,
        normalizedKeywordTokens,
        aliasKeys,
      );
      const score = buildSearchScore(item, normalizedKeyword, normalizedKeywordTokens, aliasKeys);
      return { ...item, searchScore: score, matchTier };
    });
    scored.sort((a, b) => {
      if (b.matchTier !== a.matchTier) {
        return b.matchTier - a.matchTier;
      }
      if (b.searchScore !== a.searchScore) {
        return b.searchScore - a.searchScore;
      }
      return (a.name || "").localeCompare(b.name || "", "ja");
    });
    return scored.slice(0, PAGE_SIZE);
  }, [aliasKeys, combinedItems, normalizedKeyword, normalizedKeywordTokens]);

  const displayedItemIds = useMemo(() => {
    return new Set(rankedItems.map((item) => item.id));
  }, [rankedItems]);

  const loadedItems = useMemo(() => {
    const map = new Map();
    pages.forEach((pageData) => {
      if (!pageData) return;
      pageData.items.forEach((item) => {
        if (!map.has(item.id)) {
          map.set(item.id, item);
        }
      });
    });
    return Array.from(map.values());
  }, [pages]);

  const categoryOptions = useMemo(() => {
    return Array.from(
      new Set(loadedItems.map((item) => item.categoryGeneral).filter(Boolean)),
    ).sort();
  }, [loadedItems]);

  const itemsWithDistance = useMemo(() => {
    const withDistance = rankedItems.map((item) => {
      const coord =
        Number.isFinite(item.lat) && Number.isFinite(item.lng)
          ? { lat: item.lat, lng: item.lng }
          : PREFECTURE_COORDS[item.prefecture];
      return {
        ...item,
        distanceKm: userLocation ? (coord ? getDistanceKm(userLocation, coord) : null) : null,
      };
    });
    if (!userLocation) {
      return withDistance;
    }
    const hasKeyword = Boolean(normalizedKeyword || normalizedKeywordTokens.length > 0);
    return [...withDistance].sort((a, b) => {
      if (hasKeyword) {
        if (b.matchTier !== a.matchTier) {
          return b.matchTier - a.matchTier;
        }
        if (b.searchScore !== a.searchScore) {
          return b.searchScore - a.searchScore;
        }
      }
      if (a.distanceKm == null && b.distanceKm == null) return 0;
      if (a.distanceKm == null) return 1;
      if (b.distanceKm == null) return -1;
      return a.distanceKm - b.distanceKm;
    });
  }, [normalizedKeyword, normalizedKeywordTokens, rankedItems, userLocation]);

  const itemPageMap = useMemo(() => {
    const map = new Map();
    pages.forEach((pageData, index) => {
      if (!pageData) return;
      pageData.items.forEach((item) => map.set(item.id, index + 1));
    });
    return map;
  }, [pages]);

  const selectItemById = useCallback(
    (itemId) => {
      if (!itemId) return;
      setSelectedItemId(itemId);
      const targetPage = itemPageMap.get(itemId);
      if (targetPage) {
        setPage(targetPage);
      }
    },
    [itemPageMap],
  );

  const openEquipmentDetail = useCallback((item) => {
    if (!item) return;
    setDetailItem(item);
    setDetailOpen(true);
    setSheetExpanded(false);
  }, []);

  const handleSheetToggle = useCallback(() => {
    setSheetExpanded((prev) => !prev);
  }, []);

  const handleItemSelect = useCallback(
    (item) => {
      if (!item) return;
      selectItemById(item.id);
      openEquipmentDetail(item);
    },
    [openEquipmentDetail, selectItemById],
  );

  const handleSheetTouchStart = (event) => {
    const target = event.target;
    const canHandle =
      target?.closest?.(".equipment-sheet-handle") ||
      target?.closest?.(".equipment-sheet-header");
    if (!canHandle) {
      sheetTouchStartRef.current = null;
      return;
    }
    sheetTouchStartRef.current = event.touches[0]?.clientY ?? null;
  };

  const handleSheetTouchEnd = (event) => {
    const startY = sheetTouchStartRef.current;
    if (startY == null) return;
    const endY = event.changedTouches[0]?.clientY ?? startY;
    const delta = endY - startY;
    if (delta < -80) {
      setSheetExpanded(true);
    } else if (delta > 80) {
      if (sheetExpanded) {
        setSheetExpanded(false);
      } else {
        setDetailOpen(false);
      }
    }
    sheetTouchStartRef.current = null;
  };

  useEffect(() => {
    if (!selectedItemId) {
      if (detailOpen) {
        setDetailOpen(false);
      }
      return;
    }
    if (!displayedItemIds.has(selectedItemId) && !itemPageMap.has(selectedItemId)) {
      setSelectedItemId(null);
      if (detailOpen) {
        setDetailOpen(false);
      }
    }
  }, [detailOpen, displayedItemIds, itemPageMap, selectedItemId]);

  const registerListItemRef = useCallback((itemId) => {
    return (node) => {
      if (!itemId) return;
      if (node) {
        listItemRefs.current.set(itemId, node);
      } else {
        listItemRefs.current.delete(itemId);
      }
    };
  }, []);

  useEffect(() => {
    if (!selectedItemId) return;
    const node = listItemRefs.current.get(selectedItemId);
    if (node) {
      node.scrollIntoView({ behavior: "smooth", block: "center" });
    }
  }, [selectedItemId, page]);

  const handlePrevPage = () => {
    if (page > 1) {
      setPage((current) => Math.max(1, current - 1));
    }
  };

  const handleNextPage = () => {
    const nextPage = page + 1;
    if (!currentPageData.hasNext) return;
    if (pages[nextPage - 1]) {
      setPage(nextPage);
      return;
    }
    const cursor = currentPageData.lastDoc;
    if (cursor) {
      loadPage({ pageIndex: nextPage - 1, cursor, reset: false });
      setPage(nextPage);
    }
  };

  const jumpToPage = useCallback(
    async (targetPage) => {
      if (targetPage < 1 || loading || pagingRef.current) return;
      if (loadedPageCount === 0) return;
      if (targetPage === page) return;
      if (targetPage <= loadedPageCount) {
        setPage(targetPage);
        return;
      }
      pagingRef.current = true;
      try {
        let currentIndex = loadedPageCount;
        while (currentIndex < targetPage) {
          const prevPageData = pagesRef.current[currentIndex - 1];
          if (!prevPageData?.lastDoc) break;
          if (pagesRef.current[currentIndex]) {
            currentIndex += 1;
            continue;
          }
          await loadPage({
            pageIndex: currentIndex,
            cursor: prevPageData.lastDoc,
            reset: false,
          });
          const loaded = pagesRef.current[currentIndex];
          if (!loaded) break;
          currentIndex += 1;
          if (!loaded.hasNext) break;
        }
        const nextLastIndex = pagesRef.current.reduce(
          (acc, pageData, index) => (pageData ? index : acc),
          -1,
        );
        const nextPage = Math.min(targetPage, nextLastIndex + 1);
        if (nextPage >= 1) {
          setPage(nextPage);
        }
      } finally {
        pagingRef.current = false;
      }
    },
    [loadedPageCount, loadPage, loading, page],
  );

  const handleJumpBy = (step) => {
    const target = Math.max(1, page + step);
    if (step > 0) {
      jumpToPage(target);
    } else {
      setPage(target);
    }
  };

  const handleJumpToFirst = () => {
    if (page !== 1) setPage(1);
  };

  const handleJumpToLast = () => {
    if (loadedPageCount > 0) {
      setPage(loadedPageCount);
    }
  };

  const canJumpForward = page < loadedPageCount || currentPageData.hasNext;
  const canJumpBackward = page > 1;

  const mapItems = useMemo(() => {
    return loadedItems
      .map((item) => {
        const coord =
          Number.isFinite(item.lat) && Number.isFinite(item.lng)
            ? { lat: item.lat, lng: item.lng }
            : PREFECTURE_COORDS[item.prefecture];
        if (!coord) return null;
        return { ...item, position: coord };
      })
      .filter(Boolean);
  }, [loadedItems]);

  const mapItemById = useMemo(() => {
    const map = new Map();
    mapItems.forEach((item) => {
      map.set(item.id, item);
    });
    return map;
  }, [mapItems]);

  const mapData = useMemo(() => {
    const prefectureCounts = {};
    const prefectureOrgs = {};
    const missingCoords = loadedItems.filter(
      (item) => !Number.isFinite(item.lat) || !Number.isFinite(item.lng),
    ).length;
    loadedItems.forEach((item) => {
      const key = item.prefecture || "不明";
      if (!prefectureCounts[key]) {
        prefectureCounts[key] = 0;
        prefectureOrgs[key] = new Set();
      }
      prefectureCounts[key] += 1;
      if (item.orgName) {
        prefectureOrgs[key].add(item.orgName);
      }
    });
    const totalFacilities = new Set(
      loadedItems.map((item) => item.orgName).filter(Boolean),
    ).size;

    const topPrefectures = Object.keys(prefectureCounts)
      .map((prefecture) => ({
        prefecture,
        equipmentCount: prefectureCounts[prefecture],
        facilityCount: prefectureOrgs[prefecture].size,
      }))
      .sort((a, b) => b.equipmentCount - a.equipmentCount)
      .slice(0, 6);

    return {
      totalFacilities,
      totalEquipment: loadedItems.length,
      prefectureCount: Object.keys(prefectureCounts).length,
      topPrefectures,
      missingCoords,
    };
  }, [loadedItems]);

  const summaryTopPrefectures = useMemo(() => {
    return prefectureSummary
      .map((item) => ({
        prefecture: item.prefecture,
        equipmentCount: item.equipmentCount ?? item.equipment_count ?? 0,
        facilityCount: item.facilityCount ?? item.facility_count ?? 0,
      }))
      .filter((item) => item.prefecture);
  }, [prefectureSummary]);

  const displayTopPrefectures = useMemo(() => {
    if (summaryTopPrefectures.length > 0) {
      return summaryTopPrefectures;
    }
    return mapData.topPrefectures;
  }, [mapData.topPrefectures, summaryTopPrefectures]);

  const usingFallbackTopPrefectures =
    summaryTopPrefectures.length === 0 && mapData.topPrefectures.length > 0;

  const sortedTopPrefectures = useMemo(() => {
    if (!userLocation) {
      return displayTopPrefectures;
    }
    return [...displayTopPrefectures].sort((a, b) => {
      const coordA = PREFECTURE_COORDS[a.prefecture];
      const coordB = PREFECTURE_COORDS[b.prefecture];
      const distA = coordA ? getDistanceKm(userLocation, coordA) : null;
      const distB = coordB ? getDistanceKm(userLocation, coordB) : null;
      if (distA == null && distB == null) return 0;
      if (distA == null) return 1;
      if (distB == null) return -1;
      return distA - distB;
    });
  }, [displayTopPrefectures, userLocation]);

  useEffect(() => {
    if (!mapsReady || !mapInstanceRef.current) return;
    const map = mapInstanceRef.current;
    const markers = markersRef.current;
    const nextIds = new Set(mapItems.map((item) => item.id));
    markers.forEach((marker, id) => {
      if (!nextIds.has(id)) {
        marker.setMap(null);
        markers.delete(id);
      }
    });
    mapItems.forEach((item) => {
      const existing = markers.get(item.id);
      if (existing) {
        existing.setPosition(item.position);
        existing.setTitle(item.name);
        return;
      }
      const marker = new window.google.maps.Marker({
        position: item.position,
        map,
        title: item.name,
      });
      marker.addListener("click", () => {
        handleItemSelect(item);
      });
      markers.set(item.id, marker);
    });
  }, [handleItemSelect, mapsReady, mapItems]);

  useEffect(() => {
    if (!mapsReady || !mapInstanceRef.current || !infoWindowRef.current) return;
    const selected = selectedItemId ? mapItemById.get(selectedItemId) : null;
    if (!selected) {
      infoWindowRef.current.close();
      return;
    }
    const marker = markersRef.current.get(selectedItemId);
    if (!marker) return;
    const content = `<div><strong>${escapeHtml(selected.name)}</strong><br />${escapeHtml(
      selected.prefecture || "",
    )}</div>`;
    infoWindowRef.current.setContent(content);
    infoWindowRef.current.open({ map: mapInstanceRef.current, anchor: marker });
    mapInstanceRef.current.panTo(marker.getPosition());
  }, [mapsReady, mapItemById, selectedItemId]);

  const detailGuide = useMemo(() => buildEquipmentGuide(detailItem), [detailItem]);
  const currentPapers = detailItem?.papers || [];
  const papersStatus = detailItem?.papersStatus || "";
  const paperMessage =
    papersStatus === "no_query"
      ? "関連論文の検索語が不足しています。"
      : papersStatus === "no_results"
        ? "該当する論文が見つかりませんでした。"
        : papersStatus === "error"
          ? detailItem?.papersError || "論文データの取得に失敗しました。"
          : "関連論文データを準備中です。";

  return (
    <div className="page">
      <header className="hero">
        <div className="hero-copy">
          <p className="eyebrow">公的機関の研究設備を、地域から探す</p>
          <div className="title-row">
            <div className="title-stack">
              <h1>
                Kikidoko
                <span>研究設備の横断検索</span>
              </h1>
            </div>
            <div className="hero-meta">
              <div>
                <span>最終更新</span>
                <strong>{latestUpdate}</strong>
              </div>
            </div>
          </div>
          <p className="lead">
            国立研究機関・国立大学・私立大学・高専の共用設備を一箇所で検索。
            地域別の分布を俯瞰しながら、最適な設備へアクセスできます。
          </p>
        </div>
        <div className="search-panel">
          <div className="search-main">
            <input
              type="text"
              placeholder="機器名 / 機関名で検索（例: XRD, SEM）"
              value={keywordInput}
              onChange={(event) => setKeywordInput(event.target.value)}
              onCompositionStart={() => setIsComposing(true)}
              onCompositionEnd={() => setIsComposing(false)}
              onKeyDown={(event) => {
                if (event.key === "Enter" && !isComposing) {
                  event.preventDefault();
                  handleSearch();
                }
              }}
            />
          </div>
          <div className="search-options">
            <div className="filter">
              <label htmlFor="region">地域</label>
              <select
                id="region"
                value={region}
                onChange={(event) => setRegion(event.target.value)}
              >
                <option value="all">全国</option>
                {REGION_ORDER.map((item) => (
                  <option key={item} value={item}>
                    {item}
                  </option>
                ))}
              </select>
            </div>
            <div className="filter">
              <label htmlFor="category">カテゴリ</label>
              <select
                id="category"
                value={category}
                onChange={(event) => setCategory(event.target.value)}
              >
                <option value="all">すべて</option>
                {categoryOptions.map((item) => (
                  <option key={item} value={item}>
                    {item}
                  </option>
                ))}
              </select>
            </div>
            <div className="filter-inline">
              <label className="toggle">
                <input
                  type="checkbox"
                  checked={externalOnly}
                  onChange={(event) => setExternalOnly(event.target.checked)}
                />
                <span>学外利用可のみ</span>
              </label>
              <label className="toggle">
                <input
                  type="checkbox"
                  checked={freeOnly}
                  onChange={(event) => setFreeOnly(event.target.checked)}
                />
                <span>無料設備のみ</span>
              </label>
            </div>
          </div>
          <div className="search-actions">
            <div className="search-buttons">
              <div className="search-left">
                <button
                  className="ghost"
                  type="button"
                  onClick={requestLocation}
                  disabled={locationStatus === "loading"}
                >
                  {userLocation ? "現在地を更新" : "現在地を使う"}
                </button>
              </div>
              <div className="search-right">
                <button className="ghost" type="button" onClick={handleReset}>
                  条件をリセット
                </button>
                <button className="primary" type="button" onClick={handleSearch}>
                  検索する
                </button>
              </div>
            </div>
            {locationStatus === "error" && (
              <p className="location-note error">{locationError}</p>
            )}
          </div>
        </div>
      </header>

      <section className="results" ref={resultsRef}>
        <div className="results-head">
          <div>
            <h2>検索結果</h2>
            <p>{loading ? "検索結果を読み込んでいます..." : `${rankedItems.length} 件を表示`}</p>
          </div>
          {prefectureFilter && (
            <div className="prefecture-filter">
              <span>都道府県: {prefectureFilter}</span>
              <button type="button" onClick={handlePrefectureRestore}>
                元に戻す
              </button>
            </div>
          )}
        </div>
        <div className="results-body">
          <div className="results-list">
            {loading ? (
              <p className="results-status">データを読み込んでいます...</p>
            ) : loadError ? (
              <p className="results-status error">{loadError}</p>
            ) : rankedItems.length === 0 ? (
              <p className="results-status">該当する設備が見つかりませんでした。</p>
            ) : (
              <>
                <div className="list-header">
                  <span>設備</span>
                  <span>所在地 / 近さ</span>
                  <span>利用</span>
                  <span>リンク</span>
                </div>
                <div className="list-body">
                  {itemsWithDistance.map((item) => (
                    <div
                      key={item.id}
                      className={`result-row${selectedItemId === item.id ? " is-selected" : ""}`}
                      role="button"
                      tabIndex={0}
                      onClick={() => handleItemSelect(item)}
                      onKeyDown={(event) => {
                        if (event.key === "Enter" || event.key === " ") {
                          event.preventDefault();
                          handleItemSelect(item);
                        }
                      }}
                      ref={registerListItemRef(item.id)}
                    >
                      <div className="result-title">
                        <p className="category">{item.categoryGeneral}</p>
                        <strong>{item.name}</strong>
                        {item.categoryDetail && (
                          <span className="detail">{item.categoryDetail}</span>
                        )}
                      </div>
                      <div className="result-meta">
                        <div className="result-distance">
                          <span className="prefecture">{item.prefecture}</span>
                          <span className="distance-value">
                            {formatDistance(item.distanceKm)}
                          </span>
                        </div>
                        <div className="result-tags">
                          <span className={badgeClass(item.externalUse)}>
                            {externalLabel(item.externalUse)}
                          </span>
                          <span className="fee">{item.feeBand}</span>
                        </div>
                      </div>
                      <div className="result-actions">
                        {item.sourceUrl ? (
                          <button
                            type="button"
                            className="link-button"
                            onClick={(event) => {
                              event.stopPropagation();
                              handleExternalOpen(item);
                            }}
                          >
                            機器ページへ
                          </button>
                        ) : (
                          <span className="link-disabled">情報元なし</span>
                        )}
                        <a
                          href={buildEqnetLink(item)}
                          className="link-button secondary"
                          target="_blank"
                          rel="noreferrer"
                          onClick={(event) => event.stopPropagation()}
                        >
                          eqnetで利用登録
                        </a>
                      </div>
                    </div>
                  ))}
                </div>
              </>
            )}
            {!loading && !loadError && (loadedPageCount > 1 || currentPageData.hasNext) && (
              <div className="pagination">
                <div className="pagination-bar" role="navigation" aria-label="ページ送り">
                  <button
                    type="button"
                    className="pager-button"
                    onClick={handleJumpToFirst}
                    disabled={!canJumpBackward || loading}
                    aria-label="最初のページへ"
                  >
                    {"<<"}
                  </button>
                  <button
                    type="button"
                    className="pager-button pager-skip"
                    onClick={() => handleJumpBy(-5)}
                    disabled={!canJumpBackward || loading}
                    aria-label="5ページ戻る"
                  >
                    {"<5"}
                  </button>
                  <button
                    type="button"
                    className="pager-button"
                    onClick={handlePrevPage}
                    disabled={!canJumpBackward || loading}
                    aria-label="前のページへ"
                  >
                    {"<"}
                  </button>
                  <button type="button" className="page-number is-active" disabled>
                    {page}
                  </button>
                  <button
                    type="button"
                    className="pager-button"
                    onClick={handleNextPage}
                    disabled={!currentPageData.hasNext || loading}
                    aria-label="次のページへ"
                  >
                    {">"}
                  </button>
                  <button
                    type="button"
                    className="pager-button pager-skip"
                    onClick={() => handleJumpBy(5)}
                    disabled={!canJumpForward || loading}
                    aria-label="5ページ進む"
                  >
                    {"5>"}
                  </button>
                  <button
                    type="button"
                    className="pager-button"
                    onClick={handleJumpToLast}
                    disabled={loadedPageCount === 0 || page === loadedPageCount || loading}
                    aria-label="読み込み済みの最後へ"
                  >
                    {">>"}
                  </button>
                </div>
              </div>
            )}
          </div>
          <aside className="map-panel">
            <div className="map-head">
              <div>
                <h3>全国分布</h3>
                <p>全国の総合集計から拠点と機器数を俯瞰します。</p>
              </div>
            </div>
            <div className="map-canvas">
              {mapsError ? (
                <div className="map-placeholder error">{mapsError}</div>
              ) : !mapsReady ? (
                <div className="map-placeholder">地図を読み込んでいます...</div>
              ) : (
                <div ref={mapRef} className="map-container" />
              )}
              <div className="map-legend">
                <span>ピンをクリックして設備を選択</span>
                <span>表示範囲: 日本のみ</span>
                <span>表示は読み込み済みの設備のみ</span>
                {mapData.missingCoords > 0 && (
                  <span>
                    座標未取得: {mapData.missingCoords} 件（都道府県中心で表示）
                  </span>
                )}
              </div>
            </div>
            <div className="map-list">
              <h4>機器が多い都道府県</h4>
              {displayTopPrefectures.length === 0 ? (
                <p className="map-list-empty">
                  {prefectureSummaryLoaded
                    ? "集計データを準備中です。"
                    : "集計データを読み込み中..."}
                </p>
              ) : (
                <>
                  {usingFallbackTopPrefectures && (
                    <p className="map-list-note">検索結果から暫定表示中</p>
                  )}
                  <ul>
                    {sortedTopPrefectures.map((item) => (
                      <li key={item.prefecture}>
                        <button
                          type="button"
                          className="prefecture-link"
                          onClick={() => handlePrefectureSelect(item.prefecture)}
                        >
                          <span>{item.prefecture}</span>
                          <span>{item.equipmentCount} 件</span>
                          <span>{item.facilityCount} 拠点</span>
                        </button>
                      </li>
                    ))}
                  </ul>
                </>
              )}
            </div>
          </aside>
        </div>
      </section>

      {activeExternal && (
        <div className="external-viewer" role="dialog" aria-modal="true">
          <button
            type="button"
            className="external-backdrop"
            onClick={handleExternalClose}
            aria-label="閉じる"
          />
          <div className="external-panel">
            <div className="external-header">
              <div>
                <p className="external-title">{activeExternal.name}</p>
                <p className="external-sub">{activeExternal.orgName}</p>
              </div>
              <div className="external-actions">
                <a href={activeExternal.url} target="_blank" rel="noreferrer">
                  別タブで開く
                </a>
                <button type="button" onClick={handleExternalClose}>
                  閉じる
                </button>
              </div>
            </div>
            <div className="external-body">
              <iframe
                src={activeExternal.url}
                title={`${activeExternal.name} 外部ページ`}
                loading="lazy"
              />
              <p className="external-note">
                外部サイトの表示制限で読み込めない場合は「別タブで開く」をご利用ください。
              </p>
            </div>
          </div>
        </div>
      )}

      {detailItem && (
        <div
          className={`equipment-sheet${detailOpen ? " is-open" : ""}${
            sheetExpanded ? " is-expanded" : ""
          }`}
        >
          <div className="equipment-sheet-backdrop" aria-hidden="true" />
          <div
            className="equipment-sheet-panel"
            onTouchStart={handleSheetTouchStart}
            onTouchEnd={handleSheetTouchEnd}
            role="dialog"
            aria-modal="false"
          >
            <button
              type="button"
              className="equipment-sheet-handle"
              onClick={handleSheetToggle}
              aria-expanded={sheetExpanded}
            >
              <span className="equipment-sheet-handle-bar" aria-hidden="true" />
              <span className="equipment-sheet-handle-text">
                {sheetExpanded ? "タップで元に戻す" : "タップで全画面表示"}
              </span>
            </button>
            <div className="equipment-sheet-header">
              <div className="equipment-sheet-title">
                <p className="equipment-sheet-eyebrow">{detailGuide.title}</p>
                <h4 className="equipment-sheet-name">{detailItem.name}</h4>
                <p className="equipment-sheet-meta">
                  {detailItem.prefecture} ・ {detailItem.orgName}
                </p>
              </div>
              <button
                type="button"
                className="equipment-sheet-close"
                onClick={() => setDetailOpen(false)}
              >
                閉じる
              </button>
            </div>
            <div className="equipment-sheet-body">
              <p>{detailGuide.summary}</p>
              <ul>
                {detailGuide.bullets.map((text) => (
                  <li key={text}>{text}</li>
                ))}
              </ul>
              <div className="equipment-sheet-papers">
                <h5>関連論文（DOI）</h5>
                {currentPapers.length === 0 ? (
                  <p className="paper-status">{paperMessage}</p>
                ) : (
                  <ul className="paper-list">
                    {currentPapers.map((paper) => (
                      <li key={paper.doi} className="paper-item">
                        <p className="paper-title">{paper.title || "タイトル不明"}</p>
                        <div className="paper-meta">
                          <span className="paper-genre">
                            {paper.genre_ja || resolvePaperGenre(paper.genre)}
                          </span>
                          {paper.source && <span>{paper.source}</span>}
                          {paper.year && <span>{paper.year}</span>}
                          <a
                            href={paper.url || `https://doi.org/${paper.doi}`}
                            target="_blank"
                            rel="noreferrer"
                          >
                            DOI: {paper.doi}
                          </a>
                        </div>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </div>
            <div className="equipment-sheet-actions">
              {detailItem.sourceUrl ? (
                <button
                  type="button"
                  className="link-button"
                  onClick={() => handleExternalOpen(detailItem)}
                >
                  機器ページへ
                </button>
              ) : (
                <span className="link-disabled">情報元なし</span>
              )}
              <a
                href={buildEqnetLink(detailItem)}
                className="link-button secondary"
                target="_blank"
                rel="noreferrer"
              >
                eqnetで利用登録
              </a>
            </div>
            <p className="equipment-sheet-note">
              詳細な用途や利用条件は機器ページでご確認ください。
            </p>
          </div>
        </div>
      )}

      <footer className="footer">
        <p>データは公的機関が公開する情報をもとに収集・更新します。</p>
        <p>利用登録や手続きはeqnet側で実施してください。</p>
      </footer>
    </div>
  );
}
