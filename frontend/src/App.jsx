import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import {
  collection,
  doc,
  documentId,
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

const MAP_VIEWBOX_SIZE = 1000;
const MAP_PADDING = 24;
const MAP_ZOOM_MIN = 1;
const MAP_ZOOM_MAX = 6;
const MAP_ZOOM_STEP = 1.15;
const DEFAULT_MAP_ZOOM = 5.0;
const MAP_ORG_FETCH_LIMIT = 400;
const MAP_ORG_FETCH_MAX_PAGES = 10;
const REGION_CATEGORY_FETCH_LIMIT = 400;
const REGION_CATEGORY_FETCH_MAX_PAGES = 20;

const toMercatorY = (lat) => {
  const clamped = Math.max(-85, Math.min(85, lat));
  return Math.log(Math.tan(Math.PI / 4 + (clamped * Math.PI) / 360));
};

const collectCoordinates = (coords, output) => {
  if (!coords) return;
  if (typeof coords[0] === "number") {
    output.push(coords);
    return;
  }
  coords.forEach((item) => collectCoordinates(item, output));
};

const getGeoBounds = (features) => {
  let minLng = Infinity;
  let maxLng = -Infinity;
  let minY = Infinity;
  let maxY = -Infinity;
  features.forEach((feature) => {
    const coords = [];
    collectCoordinates(feature?.geometry?.coordinates, coords);
    coords.forEach(([lng, lat]) => {
      if (!Number.isFinite(lng) || !Number.isFinite(lat)) return;
      minLng = Math.min(minLng, lng);
      maxLng = Math.max(maxLng, lng);
      const y = toMercatorY(lat);
      minY = Math.min(minY, y);
      maxY = Math.max(maxY, y);
    });
  });
  if (!Number.isFinite(minLng)) {
    return null;
  }
  return { minLng, maxLng, minY, maxY };
};

const buildGeoPath = (geometry, project) => {
  if (!geometry || !project) return "";
  const ringToPath = (ring) => {
    if (!ring || ring.length === 0) return "";
    return (
      ring
        .map((coord, index) => {
          const [x, y] = project(coord);
          return `${index === 0 ? "M" : "L"}${x.toFixed(2)} ${y.toFixed(2)}`;
        })
        .join(" ") + " Z"
    );
  };
  if (geometry.type === "Polygon") {
    return geometry.coordinates.map(ringToPath).join(" ");
  }
  if (geometry.type === "MultiPolygon") {
    return geometry.coordinates.map((polygon) => polygon.map(ringToPath).join(" ")).join(" ");
  }
  if (geometry.type === "GeometryCollection") {
    return geometry.geometries.map((geom) => buildGeoPath(geom, project)).join(" ");
  }
  return "";
};

const getPrefectureName = (properties) => {
  if (!properties) return "";
  const candidates = [
    properties.nam_ja,
    properties.name_ja,
    properties.N03_001,
    properties.N03_004,
    properties.name,
    properties.nam,
  ];
  const found = candidates.find((value) => typeof value === "string" && value.trim());
  const cleaned = found ? found.trim() : "";
  if (PREFECTURE_COORDS[cleaned]) return cleaned;
  return cleaned;
};

const getProjectedBounds = (geometry, project) => {
  if (!geometry || !project) return null;
  let minX = Infinity;
  let maxX = -Infinity;
  let minY = Infinity;
  let maxY = -Infinity;
  const updateBounds = (coords) => {
    const list = [];
    collectCoordinates(coords, list);
    list.forEach((coord) => {
      const [x, y] = project(coord);
      if (!Number.isFinite(x) || !Number.isFinite(y)) return;
      minX = Math.min(minX, x);
      maxX = Math.max(maxX, x);
      minY = Math.min(minY, y);
      maxY = Math.max(maxY, y);
    });
  };
  if (geometry.type === "GeometryCollection") {
    geometry.geometries?.forEach((geom) => updateBounds(geom.coordinates));
  } else {
    updateBounds(geometry.coordinates);
  }
  if (!Number.isFinite(minX)) return null;
  return { minX, minY, maxX, maxY };
};
const TOKEN_PATTERN = /[A-Za-z0-9]+|[ぁ-んァ-ン一-龥々ー]+/g;

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
  const normalizedOrg = normalizeForMatch(item.orgName);
  if (keywordNormalized && normalizedOrg && normalizedOrg === keywordNormalized) {
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

const ORG_KEYWORD_TERMS = [
  "大学",
  "高専",
  "研究所",
  "研究院",
  "研究科",
  "研究室",
  "研究機関",
  "機構",
  "機関",
  "センター",
  "病院",
  "学院",
];

const APP_BASE_URL = import.meta.env.BASE_URL || "/";
const TERMS_URL = `${APP_BASE_URL}terms.html`;
const PRIVACY_POLICY_URL = `${APP_BASE_URL}privacy-policy.html`;
const CONTACT_URL = "https://student-subscription.com/contact/";
const EQNET_PUBLIC_EQUIPMENT_URL = "https://eqnet.jp/top#/public/equipment";
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

const buildOrgListFromItems = (items) => {
  const orgCounts = new Map();
  items.forEach((item) => {
    const orgName = item.orgName || item.org_name || "不明";
    orgCounts.set(orgName, (orgCounts.get(orgName) || 0) + 1);
  });
  return Array.from(orgCounts.entries())
    .map(([orgName, count]) => ({ orgName, count }))
    .sort((a, b) => b.count - a.count);
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

const buildEqnetHints = (item) => {
  if (!item) return [];
  const values = [
    item.name,
    item.orgName,
    item.categoryGeneral,
    item.prefecture,
    item.eqnetEquipmentId ? `設備ID: ${item.eqnetEquipmentId}` : "",
  ];
  const seen = new Set();
  const hints = [];
  values.forEach((value) => {
    const text = String(value || "").trim();
    if (!text || seen.has(text)) return;
    seen.add(text);
    hints.push(text);
  });
  return hints.slice(0, 4);
};

const clampValue = (value, min, max) => Math.max(min, Math.min(max, value));

export default function App() {
  const [pages, setPages] = useState([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [keywordInput, setKeywordInput] = useState("");
  const [keyword, setKeyword] = useState("");
  const [latestUpdate, setLatestUpdate] = useState("未設定");
  const [prefectureSummary, setPrefectureSummary] = useState([]);
  const [prefectureSummaryLoaded, setPrefectureSummaryLoaded] = useState(false);
  const [prefectureStats, setPrefectureStats] = useState({
    counts: {},
    facilityCounts: {},
    updatedAt: "",
  });
  const [prefectureGeoJson, setPrefectureGeoJson] = useState({
    type: "FeatureCollection",
    features: [],
  });
  const [geoJsonStatus, setGeoJsonStatus] = useState("loading");
  const [mapZoom, setMapZoom] = useState(DEFAULT_MAP_ZOOM);
  const [mapPan, setMapPan] = useState({ x: 0, y: 0 });
  const [resultsListHeight, setResultsListHeight] = useState(0);
  const [isNarrowLayout, setIsNarrowLayout] = useState(false);
  const [prefectureFilter, setPrefectureFilter] = useState("");
  const [orgFilter, setOrgFilter] = useState("");
  const [region, setRegion] = useState("all");
  const [category, setCategory] = useState("all");
  const [regionInput, setRegionInput] = useState("all");
  const [categoryInput, setCategoryInput] = useState("all");
  const [regionCategoryOptionsMap, setRegionCategoryOptionsMap] = useState({});
  const [categoryOptionsLoading, setCategoryOptionsLoading] = useState(false);
  const [externalOnly, setExternalOnly] = useState(false);
  const [freeOnly, setFreeOnly] = useState(false);
  const [page, setPage] = useState(1);
  const [activeExternal, setActiveExternal] = useState(null);
  const [eqnetAssistItem, setEqnetAssistItem] = useState(null);
  const [eqnetCopiedField, setEqnetCopiedField] = useState("");
  const [eqnetAssistAttention, setEqnetAssistAttention] = useState(false);
  const [mapInfoPrefecture, setMapInfoPrefecture] = useState("");
  const [mapHover, setMapHover] = useState(null);
  const [mapOrgCache, setMapOrgCache] = useState({});
  const [mapOrgRequest, setMapOrgRequest] = useState({
    prefecture: "",
    loading: false,
    error: "",
  });
  const [skipNameOrder, setSkipNameOrder] = useState(false);
  const [detailItem, setDetailItem] = useState(null);
  const [detailOpen, setDetailOpen] = useState(false);
  const [sheetExpanded, setSheetExpanded] = useState(false);
  const [selectedItemId, setSelectedItemId] = useState(null);
  const [exactMatches, setExactMatches] = useState([]);
  const [orgMatches, setOrgMatches] = useState([]);
  const [userLocation, setUserLocation] = useState(null);
  const [locationStatus, setLocationStatus] = useState("idle");
  const [locationError, setLocationError] = useState("");
  const [isComposing, setIsComposing] = useState(false);
  const pagingRef = useRef(false);
  const pagesRef = useRef(pages);
  const listItemRefs = useRef(new Map());
  const resultsRef = useRef(null);
  const resultsListRef = useRef(null);
  const sheetTouchStartRef = useRef(null);
  const prefectureSnapshotRef = useRef(null);
  const mapContainerRef = useRef(null);
  const mapDragRef = useRef(null);
  const mapPointersRef = useRef(new Map());
  const mapPinchRef = useRef(null);
  const eqnetCopyTimerRef = useRef(null);
  const eqnetAssistAttentionTimerRef = useRef(null);

  useEffect(() => {
    setPage(1);
    setSkipNameOrder(false);
  }, [keyword, region, category, externalOnly, freeOnly, orgFilter, prefectureFilter]);

  useEffect(() => {
    setRegionInput(region);
  }, [region]);

  useEffect(() => {
    setCategoryInput(category);
  }, [category]);

  useEffect(() => {
    pagesRef.current = pages;
  }, [pages]);

  useEffect(() => {
    if (typeof window === "undefined") return undefined;
    const media = window.matchMedia("(max-width: 860px)");
    const handleChange = () => setIsNarrowLayout(media.matches);
    handleChange();
    if (media.addEventListener) {
      media.addEventListener("change", handleChange);
    } else if (media.addListener) {
      media.addListener(handleChange);
    }
    return () => {
      if (media.removeEventListener) {
        media.removeEventListener("change", handleChange);
      } else if (media.removeListener) {
        media.removeListener(handleChange);
      }
    };
  }, []);

  useLayoutEffect(() => {
    const element = resultsListRef.current;
    if (!element) return undefined;
    const updateHeight = () => {
      const nextHeight = element.offsetHeight;
      if (!nextHeight) return;
      setResultsListHeight((prev) =>
        Math.abs(prev - nextHeight) > 1 ? nextHeight : prev,
      );
    };
    updateHeight();
    const observer =
      typeof ResizeObserver !== "undefined"
        ? new ResizeObserver(() => updateHeight())
        : null;
    observer?.observe(element);
    window.addEventListener("resize", updateHeight);
    return () => {
      observer?.disconnect();
      window.removeEventListener("resize", updateHeight);
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
    if (!eqnetAssistItem) return undefined;
    const handleKeyDown = (event) => {
      if (event.key === "Escape") {
        setEqnetAssistItem(null);
        setEqnetCopiedField("");
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => {
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [eqnetAssistItem]);

  useEffect(() => {
    return () => {
      if (eqnetCopyTimerRef.current) {
        clearTimeout(eqnetCopyTimerRef.current);
      }
      if (eqnetAssistAttentionTimerRef.current) {
        clearTimeout(eqnetAssistAttentionTimerRef.current);
      }
    };
  }, []);

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
    if (mapInfoPrefecture) {
      setMapHover(null);
    }
  }, [mapInfoPrefecture]);

  const handleReset = () => {
    setKeywordInput("");
    setKeyword("");
    setOrgFilter("");
    setPrefectureFilter("");
    prefectureSnapshotRef.current = null;
    setRegion("all");
    setCategory("all");
    setRegionInput("all");
    setCategoryInput("all");
    setExternalOnly(false);
    setFreeOnly(false);
    setPage(1);
  };

  const handleSearch = () => {
    const trimmed = keywordInput.trim();
    setOrgFilter("");
    setKeywordInput(trimmed);
    setKeyword(trimmed);
    setRegion(regionInput);
    setCategory(categoryInput);
  };

  const handlePrefectureSelect = (prefecture) => {
    if (!prefecture) return;
    if (!prefectureFilter && !orgFilter) {
      prefectureSnapshotRef.current = {
        keywordInput,
        keyword,
        orgFilter,
        region,
        category,
        externalOnly,
        freeOnly,
      };
    }
    setOrgFilter("");
    setPrefectureFilter(prefecture);
    setRegion(PREFECTURE_REGION_MAP[prefecture] || "all");
    setRegionInput(PREFECTURE_REGION_MAP[prefecture] || "all");
    setPage(1);
    if (resultsRef.current) {
      resultsRef.current.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  };

  const handleMapPrefectureClick = useCallback((prefecture) => {
    if (!prefecture) return;
    setMapInfoPrefecture((prev) => (prev === prefecture ? "" : prefecture));
  }, []);

  const handleOrgSelect = useCallback(
    (orgName, prefecture) => {
      if (!orgName) return;
      if (!prefectureFilter && !orgFilter) {
        prefectureSnapshotRef.current = {
          keywordInput,
          keyword,
          orgFilter,
          region,
          category,
          externalOnly,
          freeOnly,
        };
      }
      const trimmed = orgName.trim();
      setKeywordInput(trimmed);
      setKeyword(trimmed);
      setOrgFilter(trimmed);
      if (prefecture) {
        setPrefectureFilter(prefecture);
        setRegion(PREFECTURE_REGION_MAP[prefecture] || "all");
        setRegionInput(PREFECTURE_REGION_MAP[prefecture] || "all");
      }
      setPage(1);
      if (resultsRef.current) {
        resultsRef.current.scrollIntoView({ behavior: "smooth", block: "start" });
      }
    },
    [
      category,
      externalOnly,
      freeOnly,
      keyword,
      keywordInput,
      orgFilter,
      prefectureFilter,
      region,
    ],
  );

  const handlePrefectureRestore = () => {
    const snapshot = prefectureSnapshotRef.current;
    setPrefectureFilter("");
    setOrgFilter(snapshot?.orgFilter || "");
    if (snapshot) {
      setKeywordInput(snapshot.keywordInput);
      setKeyword(snapshot.keyword);
      setRegion(snapshot.region);
      setCategory(snapshot.category);
      setRegionInput(snapshot.region);
      setCategoryInput(snapshot.category);
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
      eqnetEquipmentId: data.eqnet_equipment_id || "",
      eqnetMatchStatus: data.eqnet_match_status || "",
      eqnetCandidates: Array.isArray(data.eqnet_candidates) ? data.eqnet_candidates : [],
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
          if (orgFilter && item.orgName !== orgFilter) return false;
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
    orgFilter,
    prefectureFilter,
    region,
  ]);

  const isOrgKeyword = useMemo(() => {
    const raw = keyword.trim();
    if (!raw) return false;
    return ORG_KEYWORD_TERMS.some((term) => raw.includes(term));
  }, [keyword]);

  useEffect(() => {
    let isMounted = true;
    const loadOrgMatches = async () => {
      const trimmed = keyword.trim();
      if (!trimmed || !isOrgKeyword) {
        setOrgMatches([]);
        return;
      }
      try {
        const orgQuery = firestoreQuery(
          collection(db, "equipment"),
          where("org_name", "==", trimmed),
          limit(15),
        );
        const snap = await getDocs(orgQuery);
        if (!isMounted) return;
        const matches = snap.docs.map(mapDocToItem);
        const filtered = matches.filter((item) => {
          if (region !== "all" && item.region !== region) return false;
          if (category !== "all" && item.categoryGeneral !== category) return false;
          if (externalOnly && item.externalUse !== "可") return false;
          if (freeOnly && item.feeBand !== "無料") return false;
          if (prefectureFilter && item.prefecture !== prefectureFilter) return false;
          if (orgFilter && item.orgName !== orgFilter) return false;
          return true;
        });
        setOrgMatches(filtered);
      } catch (error) {
        console.error(error);
        if (isMounted) {
          setOrgMatches([]);
        }
      }
    };
    loadOrgMatches();
    return () => {
      isMounted = false;
    };
  }, [
    category,
    externalOnly,
    freeOnly,
    isOrgKeyword,
    keyword,
    mapDocToItem,
    orgFilter,
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
    const loadGeoJson = async () => {
      try {
        const baseUrl = import.meta.env.BASE_URL || "/";
        const response = await fetch(`${baseUrl}japan-prefectures.geojson`, {
          cache: "force-cache",
        });
        if (!response.ok) {
          throw new Error("GeoJSON fetch failed");
        }
        const data = await response.json();
        if (isMounted) {
          setPrefectureGeoJson(data);
          setGeoJsonStatus("ready");
        }
      } catch (error) {
        console.error(error);
        if (isMounted) {
          setGeoJsonStatus("error");
        }
      }
    };
    loadGeoJson();
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
          setPrefectureStats({
            counts:
              data?.prefecture_counts && typeof data.prefecture_counts === "object"
                ? data.prefecture_counts
                : {},
            facilityCounts:
              data?.facility_counts && typeof data.facility_counts === "object"
                ? data.facility_counts
                : {},
            updatedAt: typeof data?.updated_at === "string" ? data.updated_at : "",
          });
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
    (tokens, options = {}) => {
      const { skipOrder = false } = options;
      const constraints = [];
      if (region !== "all" && !prefectureFilter) {
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
      if (orgFilter) {
        constraints.push(where("org_name", "==", orgFilter));
      } else if (aliasKeys.length > 0) {
        constraints.push(where("search_aliases", "array-contains-any", aliasKeys));
      } else if (tokens.length > 0) {
        constraints.push(where("search_tokens", "array-contains-any", tokens));
      }
      if (
        !skipOrder &&
        !skipNameOrder &&
        tokens.length === 0 &&
        aliasKeys.length === 0 &&
        !orgFilter
      ) {
        constraints.push(orderBy("name"));
      }
      return firestoreQuery(collection(db, "equipment"), ...constraints);
    },
    [
      aliasKeys,
      category,
      externalOnly,
      freeOnly,
      orgFilter,
      prefectureFilter,
      region,
      skipNameOrder,
    ],
  );

  const shouldRetryQuery = useCallback((error) => {
    const code = error?.code;
    if (code === "failed-precondition" || code === "invalid-argument") {
      return true;
    }
    const message = String(error?.message || "");
    return message.toLowerCase().includes("index");
  }, []);

  const fetchPageData = useCallback(
    async (baseQuery, cursor) => {
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
      return { pageItems, lastDoc, hasNext };
    },
    [mapDocToItem],
  );

  const loadPage = useCallback(
    async ({ pageIndex, cursor, reset }) => {
      setLoading(true);
      setLoadError("");
      try {
        let data;
        try {
          const baseQuery = buildBaseQuery(keywordTokens);
          data = await fetchPageData(baseQuery, cursor);
        } catch (error) {
          if (shouldRetryQuery(error)) {
            const baseQuery = buildBaseQuery(keywordTokens, { skipOrder: true });
            data = await fetchPageData(baseQuery, cursor);
            setSkipNameOrder(true);
          } else {
            throw error;
          }
        }
        setPages((prev) => {
          const next = reset ? [] : [...prev];
          next[pageIndex] = {
            items: data.pageItems,
            lastDoc: data.lastDoc,
            hasNext: data.hasNext,
          };
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
    [buildBaseQuery, fetchPageData, keywordTokens, shouldRetryQuery],
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
        let data;
        try {
          const baseQuery = buildBaseQuery(keywordTokens);
          data = await fetchPageData(baseQuery, null);
        } catch (error) {
          if (shouldRetryQuery(error)) {
            const baseQuery = buildBaseQuery(keywordTokens, { skipOrder: true });
            data = await fetchPageData(baseQuery, null);
            setSkipNameOrder(true);
          } else {
            throw error;
          }
        }
        if (!isMounted) return;
        const nextPages = [
          { items: data.pageItems, lastDoc: data.lastDoc, hasNext: data.hasNext },
        ];
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
  }, [buildBaseQuery, fetchPageData, keywordTokens, shouldRetryQuery]);

  const openExternalViewer = (payload) => {
    if (!payload?.url) return;
    setActiveExternal({
      url: payload.url,
      name: payload.name || "外部ページ",
      orgName: payload.orgName || "",
    });
  };

  const handleExternalOpen = (item) => {
    if (!item.sourceUrl) return;
    openExternalViewer({
      url: item.sourceUrl,
      name: item.name,
      orgName: item.orgName,
    });
  };

  const handlePaperOpen = (paper) => {
    const url = paper?.url || (paper?.doi ? `https://doi.org/${paper.doi}` : "");
    openExternalViewer({
      url,
      name: paper?.title || "関連論文",
      orgName: paper?.source || detailItem?.orgName || "",
    });
  };

  const handleExternalClose = () => {
    setActiveExternal(null);
  };

  const openEqnetPage = () => {
    if (typeof window === "undefined") return;
    window.open(EQNET_PUBLIC_EQUIPMENT_URL, "_blank", "noopener,noreferrer");
  };

  const copyText = async (value) => {
    const text = String(value || "").trim();
    if (!text) return false;
    if (navigator?.clipboard?.writeText && window.isSecureContext) {
      try {
        await navigator.clipboard.writeText(text);
        return true;
      } catch (error) {
        console.error(error);
      }
    }
    try {
      const textArea = document.createElement("textarea");
      textArea.value = text;
      textArea.setAttribute("readonly", "");
      textArea.style.position = "fixed";
      textArea.style.opacity = "0";
      textArea.style.pointerEvents = "none";
      document.body.appendChild(textArea);
      textArea.focus();
      textArea.select();
      const copied = document.execCommand("copy");
      document.body.removeChild(textArea);
      return copied;
    } catch (error) {
      console.error(error);
      return false;
    }
  };

  const setEqnetCopyFeedback = (key) => {
    if (eqnetCopyTimerRef.current) {
      clearTimeout(eqnetCopyTimerRef.current);
    }
    setEqnetCopiedField(key);
    eqnetCopyTimerRef.current = setTimeout(() => {
      setEqnetCopiedField("");
      eqnetCopyTimerRef.current = null;
    }, 1600);
  };

  const handleEqnetFieldCopy = async (key, value) => {
    const copied = await copyText(value);
    if (copied) {
      setEqnetCopyFeedback(key);
    }
  };

  const handleEqnetSummaryCopy = async () => {
    if (!eqnetAssistItem) return;
    const summary = [
      eqnetAssistItem.name ? `機器名: ${eqnetAssistItem.name}` : "",
      eqnetAssistItem.orgName ? `保有機関: ${eqnetAssistItem.orgName}` : "",
      eqnetAssistItem.prefecture ? `都道府県: ${eqnetAssistItem.prefecture}` : "",
      eqnetAssistItem.category ? `カテゴリ: ${eqnetAssistItem.category}` : "",
    ]
      .filter(Boolean)
      .join("\n");
    const copied = await copyText(summary);
    if (copied) {
      setEqnetCopyFeedback("summary");
    }
  };

  const handleEqnetAssistOpen = (item) => {
    if (!item) return;
    if (eqnetAssistAttentionTimerRef.current) {
      clearTimeout(eqnetAssistAttentionTimerRef.current);
    }
    setEqnetAssistItem({
      name: item.name || "機器名不明",
      orgName: item.orgName || "",
      category: item.categoryGeneral || "",
      prefecture: item.prefecture || "",
      hints: buildEqnetHints(item),
    });
    setEqnetCopiedField("");
    setEqnetAssistAttention(true);
    eqnetAssistAttentionTimerRef.current = setTimeout(() => {
      setEqnetAssistAttention(false);
      eqnetAssistAttentionTimerRef.current = null;
    }, 1800);
  };

  const handleEqnetAssistClose = () => {
    setEqnetAssistItem(null);
    setEqnetCopiedField("");
    setEqnetAssistAttention(false);
    if (eqnetAssistAttentionTimerRef.current) {
      clearTimeout(eqnetAssistAttentionTimerRef.current);
      eqnetAssistAttentionTimerRef.current = null;
    }
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
    if (exactMatches.length === 0 && orgMatches.length === 0) {
      return currentItems;
    }
    const map = new Map();
    exactMatches.forEach((item) => map.set(item.id, item));
    orgMatches.forEach((item) => {
      if (!map.has(item.id)) {
        map.set(item.id, item);
      }
    });
    currentItems.forEach((item) => {
      if (!map.has(item.id)) {
        map.set(item.id, item);
      }
    });
    return Array.from(map.values());
  }, [currentItems, exactMatches, orgMatches]);

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
      let score = buildSearchScore(
        item,
        normalizedKeyword,
        normalizedKeywordTokens,
        aliasKeys,
      );
      if (isOrgKeyword) {
        const orgHit = scoreTextMatch(
          item.orgName,
          normalizedKeyword,
          normalizedKeywordTokens,
          {
            exact: 1200,
            prefix: 800,
            partial: 500,
            token: 40,
          },
        );
        score += orgHit;
      }
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
    if (isOrgKeyword) {
      const orgFiltered = scored.filter((item) =>
        hasTextMatch(item.orgName, normalizedKeyword, normalizedKeywordTokens),
      );
      if (orgFiltered.length > 0) {
        return orgFiltered.slice(0, PAGE_SIZE);
      }
    }
    return scored.slice(0, PAGE_SIZE);
  }, [aliasKeys, combinedItems, isOrgKeyword, normalizedKeyword, normalizedKeywordTokens]);

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

  const globalCategoryOptions = useMemo(() => {
    return Array.from(
      new Set(loadedItems.map((item) => item.categoryGeneral).filter(Boolean)),
    ).sort();
  }, [loadedItems]);

  useEffect(() => {
    if (regionInput === "all") {
      setCategoryOptionsLoading(false);
      return undefined;
    }
    const cached = regionCategoryOptionsMap[regionInput];
    if (Array.isArray(cached)) {
      setCategoryOptionsLoading(false);
      return undefined;
    }
    let isMounted = true;
    const loadRegionCategories = async () => {
      setCategoryOptionsLoading(true);
      try {
        const categories = new Set();
        let lastDoc = null;
        let pageCount = 0;
        let hasMore = true;
        while (hasMore && pageCount < REGION_CATEGORY_FETCH_MAX_PAGES) {
          const queryParts = [
            collection(db, "equipment"),
            where("region", "==", regionInput),
            orderBy(documentId()),
            limit(REGION_CATEGORY_FETCH_LIMIT),
          ];
          if (lastDoc) {
            queryParts.splice(-1, 0, startAfter(lastDoc));
          }
          const snap = await getDocs(firestoreQuery(...queryParts));
          snap.forEach((docSnap) => {
            const value = docSnap.data()?.category_general;
            if (typeof value === "string" && value.trim()) {
              categories.add(value.trim());
            }
          });
          lastDoc = snap.docs[snap.docs.length - 1] || null;
          hasMore = snap.size === REGION_CATEGORY_FETCH_LIMIT && Boolean(lastDoc);
          pageCount += 1;
        }
        if (!isMounted) return;
        const sorted = Array.from(categories).sort((a, b) => a.localeCompare(b, "ja"));
        setRegionCategoryOptionsMap((prev) => ({ ...prev, [regionInput]: sorted }));
      } catch (error) {
        console.error(error);
        if (!isMounted) return;
        setRegionCategoryOptionsMap((prev) => ({ ...prev, [regionInput]: [] }));
      } finally {
        if (isMounted) {
          setCategoryOptionsLoading(false);
        }
      }
    };
    loadRegionCategories();
    return () => {
      isMounted = false;
    };
  }, [regionCategoryOptionsMap, regionInput]);

  const categoryOptions = useMemo(() => {
    if (regionInput === "all") {
      return globalCategoryOptions;
    }
    return regionCategoryOptionsMap[regionInput] || [];
  }, [globalCategoryOptions, regionCategoryOptionsMap, regionInput]);

  useEffect(() => {
    if (categoryInput === "all") return;
    if (categoryOptions.includes(categoryInput)) return;
    setCategoryInput("all");
  }, [categoryInput, categoryOptions]);

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

  const mapData = useMemo(() => {
    const fallbackCounts = {};
    const fallbackOrgs = {};
    loadedItems.forEach((item) => {
      const key = item.prefecture || "不明";
      if (!fallbackCounts[key]) {
        fallbackCounts[key] = 0;
        fallbackOrgs[key] = new Set();
      }
      fallbackCounts[key] += 1;
      if (item.orgName) {
        fallbackOrgs[key].add(item.orgName);
      }
    });

    const fallbackFacilityCounts = Object.keys(fallbackOrgs).reduce((acc, key) => {
      acc[key] = fallbackOrgs[key].size;
      return acc;
    }, {});

    const summaryCounts = prefectureStats?.counts || {};
    const summaryFacilityCounts = prefectureStats?.facilityCounts || {};
    const hasSummaryCounts = Object.keys(summaryCounts).length > 0;
    const activeCounts = hasSummaryCounts ? summaryCounts : fallbackCounts;
    const activeFacilityCounts = hasSummaryCounts
      ? summaryFacilityCounts
      : fallbackFacilityCounts;

    const totalEquipment = hasSummaryCounts
      ? Object.values(activeCounts).reduce((acc, value) => acc + (value || 0), 0)
      : loadedItems.length;
    const totalFacilities = hasSummaryCounts
      ? Object.values(activeFacilityCounts).reduce((acc, value) => acc + (value || 0), 0)
      : new Set(loadedItems.map((item) => item.orgName).filter(Boolean)).size;

    const topPrefectures = Object.keys(activeCounts)
      .map((prefecture) => ({
        prefecture,
        equipmentCount: activeCounts[prefecture],
        facilityCount: activeFacilityCounts[prefecture] || 0,
      }))
      .sort((a, b) => b.equipmentCount - a.equipmentCount)
      .slice(0, 6);

    return {
      totalFacilities,
      totalEquipment,
      prefectureCount: Object.keys(activeCounts).length,
      topPrefectures,
      prefectureCounts: activeCounts,
      prefectureFacilityCounts: activeFacilityCounts,
      usingSummaryCounts: hasSummaryCounts,
      summaryUpdatedAt: prefectureStats?.updatedAt || "",
    };
  }, [loadedItems, prefectureStats]);

  const handleMapHover = useCallback(
    (prefecture, event) => {
      if (!prefecture || !event) return;
      const rect = mapContainerRef.current?.getBoundingClientRect();
      if (!rect) return;
      const equipmentCount = mapData.prefectureCounts?.[prefecture] || 0;
      const facilityCount = mapData.prefectureFacilityCounts?.[prefecture] || 0;
      setMapHover({
        prefecture,
        equipmentCount,
        facilityCount,
        x: event.clientX - rect.left,
        y: event.clientY - rect.top,
      });
    },
    [mapData.prefectureCounts, mapData.prefectureFacilityCounts],
  );

  const summaryPrefectureCounts = useMemo(() => {
    return prefectureSummary
      .map((item) => ({
        prefecture: item.prefecture,
        equipmentCount: item.equipmentCount ?? item.equipment_count ?? 0,
        facilityCount: item.facilityCount ?? item.facility_count ?? 0,
      }))
      .filter((item) => item.prefecture);
  }, [prefectureSummary]);

  const fallbackPrefectureCounts = useMemo(() => {
    return Object.entries(mapData.prefectureCounts || {})
      .map(([prefecture, equipmentCount]) => ({
        prefecture,
        equipmentCount,
        facilityCount: mapData.prefectureFacilityCounts?.[prefecture] || 0,
      }))
      .filter((item) => item.prefecture);
  }, [mapData.prefectureCounts, mapData.prefectureFacilityCounts]);

  const topPrefecturesByRegion = useMemo(() => {
    const source =
      summaryPrefectureCounts.length > 0
        ? summaryPrefectureCounts
        : fallbackPrefectureCounts;
    const regionMap = new Map();
    source.forEach((item) => {
      if (!item.prefecture || item.equipmentCount <= 0) return;
      const regionName = PREFECTURE_REGION_MAP[item.prefecture];
      if (!regionName) return;
      const existing = regionMap.get(regionName);
      if (
        !existing ||
        item.equipmentCount > existing.equipmentCount ||
        (item.equipmentCount === existing.equipmentCount &&
          item.facilityCount > existing.facilityCount)
      ) {
        regionMap.set(regionName, { ...item, region: regionName });
      }
    });
    return Array.from(regionMap.values()).sort(
      (a, b) =>
        REGION_ORDER.indexOf(a.region) - REGION_ORDER.indexOf(b.region),
    );
  }, [fallbackPrefectureCounts, summaryPrefectureCounts]);

  const usingFallbackTopPrefectures =
    summaryPrefectureCounts.length === 0 && topPrefecturesByRegion.length > 0;

  const sortedTopPrefectures = useMemo(() => {
    if (!userLocation) {
      return topPrefecturesByRegion;
    }
    return [...topPrefecturesByRegion].sort((a, b) => {
      const coordA = PREFECTURE_COORDS[a.prefecture];
      const coordB = PREFECTURE_COORDS[b.prefecture];
      const distA = coordA ? getDistanceKm(userLocation, coordA) : null;
      const distB = coordB ? getDistanceKm(userLocation, coordB) : null;
      if (distA == null && distB == null) return 0;
      if (distA == null) return 1;
      if (distB == null) return -1;
      return distA - distB;
    });
  }, [topPrefecturesByRegion, userLocation]);

  useEffect(() => {
    if (!mapInfoPrefecture) return undefined;
    if (!mapData.usingSummaryCounts) return undefined;
    if (mapOrgCache[mapInfoPrefecture]) return undefined;
    let isMounted = true;
    const targetPrefecture = mapInfoPrefecture;
    const targetCount = mapData.prefectureCounts?.[targetPrefecture] || 0;
    const loadMapOrgs = async () => {
      setMapOrgRequest({ prefecture: targetPrefecture, loading: true, error: "" });
      try {
        const equipmentRef = collection(db, "equipment");
        const docMap = new Map();
        const fetchPagedDocs = async (constraints) => {
          let lastDoc = null;
          let pageCount = 0;
          let hasMore = true;
          while (
            hasMore &&
            (targetCount === 0 || docMap.size < targetCount) &&
            pageCount < MAP_ORG_FETCH_MAX_PAGES
          ) {
            const queryParts = [
              equipmentRef,
              ...constraints,
              orderBy(documentId()),
              limit(MAP_ORG_FETCH_LIMIT),
            ];
            if (lastDoc) {
              queryParts.splice(-1, 0, startAfter(lastDoc));
            }
            const snap = await getDocs(firestoreQuery(...queryParts));
            snap.forEach((docSnap) => {
              docMap.set(docSnap.id, docSnap);
            });
            lastDoc = snap.docs[snap.docs.length - 1] || null;
            hasMore = snap.size === MAP_ORG_FETCH_LIMIT;
            pageCount += 1;
          }
        };
        if (targetCount > 0) {
          await fetchPagedDocs([where("prefecture", "==", targetPrefecture)]);
          if (docMap.size < targetCount) {
            await fetchPagedDocs([
              where("search_tokens", "array-contains", targetPrefecture),
            ]);
          }
        }
        const items = [];
        docMap.forEach((docSnap) => {
          const data = docSnap.data() || {};
          items.push({
            orgName: data.org_name || "不明",
          });
        });
        const orgList = buildOrgListFromItems(items);
        if (isMounted) {
          setMapOrgCache((prev) => ({
            ...prev,
            [targetPrefecture]: {
              orgList,
              sampleCount: docMap.size,
            },
          }));
          setMapOrgRequest((prev) =>
            prev.prefecture === targetPrefecture
              ? { prefecture: targetPrefecture, loading: false, error: "" }
              : prev,
          );
        }
      } catch (error) {
        console.error(error);
        if (isMounted) {
          setMapOrgRequest((prev) =>
            prev.prefecture === targetPrefecture
              ? {
                  prefecture: targetPrefecture,
                  loading: false,
                  error: "機関情報の取得に失敗しました。",
                }
              : prev,
          );
        }
      }
    };
    loadMapOrgs();
    return () => {
      isMounted = false;
    };
  }, [
    mapData.prefectureCounts,
    mapData.usingSummaryCounts,
    mapInfoPrefecture,
    mapOrgCache,
  ]);

  const mapProjection = useMemo(() => {
    const features = prefectureGeoJson?.features || [];
    const bounds = getGeoBounds(features);
    if (!bounds) return null;
    const { minLng, maxLng, minY, maxY } = bounds;
    const width = MAP_VIEWBOX_SIZE;
    const height = MAP_VIEWBOX_SIZE;
    const project = ([lng, lat]) => {
      const x =
        MAP_PADDING +
        ((lng - minLng) / (maxLng - minLng)) * (width - MAP_PADDING * 2);
      const y =
        MAP_PADDING +
        ((maxY - toMercatorY(lat)) / (maxY - minY)) * (height - MAP_PADDING * 2);
      return [x, y];
    };
    return { project, width, height };
  }, [prefectureGeoJson]);

  const mapDefaultPan = useMemo(() => {
    if (!mapProjection) return { x: 0, y: 0 };
    const coord = PREFECTURE_COORDS["群馬県"];
    if (!coord) return { x: 0, y: 0 };
    const [x, y] = mapProjection.project([coord.lng, coord.lat]);
    const center = MAP_VIEWBOX_SIZE / 2;
    return { x: x - center, y: y - center };
  }, [mapProjection]);

  useEffect(() => {
    if (!mapProjection) return;
    setMapZoom(mapInfoPrefecture ? MAP_ZOOM_MIN : DEFAULT_MAP_ZOOM);
    setMapPan(mapInfoPrefecture ? { x: 0, y: 0 } : mapDefaultPan);
  }, [mapDefaultPan, mapInfoPrefecture, mapProjection]);

  const prefectureShapes = useMemo(() => {
    if (!mapProjection) return [];
    return (prefectureGeoJson?.features || [])
      .map((feature) => {
        const name = getPrefectureName(feature.properties);
        if (!name || !PREFECTURE_COORDS[name]) return null;
        const path = buildGeoPath(feature.geometry, mapProjection.project);
        if (!path) return null;
        const bounds = getProjectedBounds(feature.geometry, mapProjection.project);
        return bounds ? { prefecture: name, path, bounds } : null;
      })
      .filter(Boolean);
  }, [mapProjection]);

  const prefectureBoundsMap = useMemo(() => {
    const map = new Map();
    prefectureShapes.forEach((shape) => {
      map.set(shape.prefecture, shape.bounds);
    });
    return map;
  }, [prefectureShapes]);

  const mapViewBox = useMemo(() => {
    const base = { minX: 0, minY: 0, width: MAP_VIEWBOX_SIZE, height: MAP_VIEWBOX_SIZE };
    if (!mapInfoPrefecture) return base;
    const bounds = prefectureBoundsMap.get(mapInfoPrefecture);
    if (!bounds) return base;
    const padding = 60;
    let minX = Math.max(0, bounds.minX - padding);
    let minY = Math.max(0, bounds.minY - padding);
    let maxX = Math.min(MAP_VIEWBOX_SIZE, bounds.maxX + padding);
    let maxY = Math.min(MAP_VIEWBOX_SIZE, bounds.maxY + padding);
    let width = maxX - minX;
    let height = maxY - minY;
    const minSize = 200;
    if (width < minSize) {
      const expand = (minSize - width) / 2;
      minX = Math.max(0, minX - expand);
      maxX = Math.min(MAP_VIEWBOX_SIZE, maxX + expand);
      width = maxX - minX;
    }
    if (height < minSize) {
      const expand = (minSize - height) / 2;
      minY = Math.max(0, minY - expand);
      maxY = Math.min(MAP_VIEWBOX_SIZE, maxY + expand);
      height = maxY - minY;
    }
    return { minX, minY, width, height };
  }, [mapInfoPrefecture, prefectureBoundsMap]);

  const mapViewport = useMemo(() => {
    const zoom = Math.max(MAP_ZOOM_MIN, mapZoom);
    const width = mapViewBox.width / zoom;
    const height = mapViewBox.height / zoom;
    const baseCenterX = mapViewBox.minX + mapViewBox.width / 2;
    const baseCenterY = mapViewBox.minY + mapViewBox.height / 2;
    let minX = baseCenterX - width / 2 + mapPan.x;
    let minY = baseCenterY - height / 2 + mapPan.y;
    minX = clampValue(minX, 0, MAP_VIEWBOX_SIZE - width);
    minY = clampValue(minY, 0, MAP_VIEWBOX_SIZE - height);
    return { minX, minY, width, height };
  }, [mapPan.x, mapPan.y, mapViewBox, mapZoom]);

  const maxMapCount = useMemo(() => {
    return Object.values(mapData.prefectureCounts || {}).reduce(
      (acc, value) => Math.max(acc, value || 0),
      0,
    );
  }, [mapData.prefectureCounts]);

  const prefectureMarkers = useMemo(() => {
    if (!mapProjection) return [];
    return Object.entries(PREFECTURE_COORDS).map(([prefecture, coord]) => {
      const [x, y] = mapProjection.project([coord.lng, coord.lat]);
      return {
        prefecture,
        x,
        y,
        equipmentCount: mapData.prefectureCounts?.[prefecture] || 0,
        facilityCount: mapData.prefectureFacilityCounts?.[prefecture] || 0,
      };
    });
  }, [mapData.prefectureCounts, mapData.prefectureFacilityCounts, mapProjection]);

  const prefectureMarkerMap = useMemo(() => {
    const map = new Map();
    prefectureMarkers.forEach((marker) => {
      map.set(marker.prefecture, marker);
    });
    return map;
  }, [prefectureMarkers]);

  const mapInfoAnchor = useMemo(() => {
    if (!mapInfoPrefecture) return null;
    const marker = prefectureMarkerMap.get(mapInfoPrefecture);
    if (!marker) return null;
    const leftPct =
      mapViewport.width > 0
        ? ((marker.x - mapViewport.minX) / mapViewport.width) * 100
        : 50;
    const topPct =
      mapViewport.height > 0
        ? ((marker.y - mapViewport.minY) / mapViewport.height) * 100
        : 50;
    return {
      left: clampValue(leftPct, 12, 88),
      top: clampValue(topPct, 16, 90),
    };
  }, [mapInfoPrefecture, mapViewport, prefectureMarkerMap]);

  const mapInfoData = useMemo(() => {
    if (!mapInfoPrefecture) return null;
    const summaryCount = mapData.prefectureCounts?.[mapInfoPrefecture] || 0;
    const items = loadedItems.filter((item) => item.prefecture === mapInfoPrefecture);
    const orgListFromItems = buildOrgListFromItems(items);
    const cachedOrg = mapOrgCache[mapInfoPrefecture];
    const orgList =
      cachedOrg?.orgList?.length > 0 ? cachedOrg.orgList : orgListFromItems;
    const orgSampleCount = cachedOrg?.sampleCount ?? items.length;
    const categoryCounts = new Map();
    items.forEach((item) => {
      const categoryKey = item.categoryDetail || item.categoryGeneral || "未分類";
      categoryCounts.set(categoryKey, (categoryCounts.get(categoryKey) || 0) + 1);
    });
    const topCategories = Array.from(categoryCounts.entries())
      .map(([category, count]) => ({ category, count }))
      .sort((a, b) => b.count - a.count)
      .slice(0, 6);
    return {
      prefecture: mapInfoPrefecture,
      totalEquipment: summaryCount || items.length,
      totalFacilities: mapData.prefectureFacilityCounts?.[mapInfoPrefecture] || orgList.length,
      orgList,
      topCategories,
      isPartial: summaryCount > 0 && orgSampleCount < summaryCount,
    };
  }, [
    loadedItems,
    mapData.prefectureCounts,
    mapData.prefectureFacilityCounts,
    mapInfoPrefecture,
    mapOrgCache,
  ]);

  const mapOrgStatus =
    mapOrgRequest.prefecture === mapInfoPrefecture
      ? mapOrgRequest
      : { loading: false, error: "" };
  const isMapOrgLoading = mapOrgStatus.loading;
  const mapOrgError = mapOrgStatus.error;

  const handleMapZoomIn = useCallback(() => {
    setMapZoom((prev) => clampValue(prev * 1.25, MAP_ZOOM_MIN, MAP_ZOOM_MAX));
  }, []);

  const handleMapZoomOut = useCallback(() => {
    setMapZoom((prev) => clampValue(prev / 1.25, MAP_ZOOM_MIN, MAP_ZOOM_MAX));
  }, []);

  const handleMapZoomReset = useCallback(() => {
    setMapZoom(mapInfoPrefecture ? MAP_ZOOM_MIN : DEFAULT_MAP_ZOOM);
    setMapPan(mapInfoPrefecture ? { x: 0, y: 0 } : mapDefaultPan);
  }, [mapDefaultPan, mapInfoPrefecture]);

  const handleMapWheel = useCallback(
    (event) => {
      if (!event) return;
      if (mapInfoPrefecture) return;
      if (event.target?.closest?.(".map-info")) return;
      if (!event.ctrlKey && !event.metaKey) return;
      event.preventDefault();
      const direction = event.deltaY < 0 ? 1 : -1;
      setMapZoom((prev) => {
        const next =
          direction > 0 ? prev * MAP_ZOOM_STEP : prev / MAP_ZOOM_STEP;
        return clampValue(next, MAP_ZOOM_MIN, MAP_ZOOM_MAX);
      });
    },
    [mapInfoPrefecture],
  );

  useEffect(() => {
    const container = mapContainerRef.current;
    if (!container) return undefined;
    const handler = (event) => handleMapWheel(event);
    container.addEventListener("wheel", handler, { passive: false });
    return () => {
      container.removeEventListener("wheel", handler);
    };
  }, [handleMapWheel]);

  const handleMapPointerDown = useCallback(
    (event) => {
      if (!event || event.button > 0) return;
      const target = event.target;
      if (
        target?.closest?.(".map-info") ||
        target?.closest?.(".map-zoom-controls") ||
        target?.closest?.(".jp-map-shape") ||
        target?.closest?.(".jp-map-marker")
      ) {
        return;
      }
      const rect = mapContainerRef.current?.getBoundingClientRect();
      if (!rect) return;
      if (event.pointerType === "touch") {
        const pointers = mapPointersRef.current;
        pointers.set(event.pointerId, { x: event.clientX, y: event.clientY });
        if (pointers.size === 2) {
          const [first, second] = Array.from(pointers.values());
          const distance = Math.hypot(first.x - second.x, first.y - second.y);
          const centerX = (first.x + second.x) / 2 - rect.left;
          const centerY = (first.y + second.y) / 2 - rect.top;
          mapPinchRef.current = {
            startDistance: distance,
            startZoom: mapZoom,
            startMapPoint: {
              x: mapViewport.minX + (centerX / rect.width) * mapViewport.width,
              y: mapViewport.minY + (centerY / rect.height) * mapViewport.height,
            },
            rect,
          };
          mapDragRef.current = null;
        } else if (pointers.size === 1) {
          mapPinchRef.current = null;
          mapDragRef.current = {
            pointerId: event.pointerId,
            startX: event.clientX,
            startY: event.clientY,
            startPan: { ...mapPan },
            rect,
          };
        }
        mapContainerRef.current?.setPointerCapture?.(event.pointerId);
        return;
      }
      mapDragRef.current = {
        pointerId: event.pointerId,
        startX: event.clientX,
        startY: event.clientY,
        startPan: { ...mapPan },
        rect,
      };
      mapContainerRef.current?.setPointerCapture?.(event.pointerId);
    },
    [mapPan, mapViewport, mapZoom],
  );

  const handleMapPointerMove = useCallback(
    (event) => {
      if (!event) return;
      if (event.pointerType === "touch") {
        const pointers = mapPointersRef.current;
        if (pointers.has(event.pointerId)) {
          pointers.set(event.pointerId, { x: event.clientX, y: event.clientY });
        }
        const pinch = mapPinchRef.current;
        if (pinch && pointers.size >= 2) {
          const [first, second] = Array.from(pointers.values());
          const distance = Math.hypot(first.x - second.x, first.y - second.y);
          if (distance > 0 && pinch.startDistance > 0) {
            const scale = distance / pinch.startDistance;
            const nextZoom = clampValue(
              pinch.startZoom * scale,
              MAP_ZOOM_MIN,
              MAP_ZOOM_MAX,
            );
            const rect = pinch.rect;
            const centerX = (first.x + second.x) / 2 - rect.left;
            const centerY = (first.y + second.y) / 2 - rect.top;
            const width = mapViewBox.width / nextZoom;
            const height = mapViewBox.height / nextZoom;
            const baseCenterX = mapViewBox.minX + mapViewBox.width / 2;
            const baseCenterY = mapViewBox.minY + mapViewBox.height / 2;
            let minX =
              pinch.startMapPoint.x - (centerX / rect.width) * width;
            let minY =
              pinch.startMapPoint.y - (centerY / rect.height) * height;
            minX = clampValue(minX, 0, MAP_VIEWBOX_SIZE - width);
            minY = clampValue(minY, 0, MAP_VIEWBOX_SIZE - height);
            setMapZoom(nextZoom);
            setMapPan({
              x: minX - (baseCenterX - width / 2),
              y: minY - (baseCenterY - height / 2),
            });
          }
          return;
        }
      }
      const drag = mapDragRef.current;
      if (!drag) return;
      const dx = event.clientX - drag.startX;
      const dy = event.clientY - drag.startY;
      const scaleX = mapViewport.width / drag.rect.width;
      const scaleY = mapViewport.height / drag.rect.height;
      setMapPan({
        x: drag.startPan.x - dx * scaleX,
        y: drag.startPan.y - dy * scaleY,
      });
    },
    [mapViewport.height, mapViewport.width, mapViewBox],
  );

  const handleMapPointerUp = useCallback((event) => {
    if (!event) return;
    const pointers = mapPointersRef.current;
    if (pointers.has(event.pointerId)) {
      pointers.delete(event.pointerId);
    }
    if (pointers.size < 2) {
      mapPinchRef.current = null;
    }
    if (mapDragRef.current?.pointerId === event.pointerId) {
      mapDragRef.current = null;
    }
  }, []);

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
        <div className="hero-shell">
          <div className="hero-copy">
            <p className="eyebrow">公的機関の研究設備を、地域から探す</p>
            <div className="title-row">
            <div className="title-stack">
              <h1>
                キキドコ
                <span>その装置、国内にあります。</span>
              </h1>
            </div>
          </div>
          <p className="lead">
            国立研究機関・国立大学・私立大学・高専の共用設備を一箇所で検索。
            地域別の分布を俯瞰しながら、最適な設備へアクセスできます。
          </p>
          <div className="hero-meta hero-meta-right">
            <div className="hero-meta-inline">
              <span>最終更新</span>
              <strong>{latestUpdate}</strong>
            </div>
          </div>
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
                  value={regionInput}
                  onChange={(event) => {
                    setRegionInput(event.target.value);
                    setCategoryInput("all");
                  }}
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
                  value={categoryInput}
                  onChange={(event) => setCategoryInput(event.target.value)}
                  disabled={regionInput !== "all" && categoryOptionsLoading}
                >
                  <option value="all">すべて</option>
                  {regionInput !== "all" && categoryOptionsLoading && (
                    <option value="" disabled>
                      読み込み中...
                    </option>
                  )}
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
                    className="ghost location-button"
                    type="button"
                    onClick={requestLocation}
                    disabled={locationStatus === "loading"}
                  >
                    <span className="location-button-icon" aria-hidden="true">
                      <svg viewBox="0 0 24 24" focusable="false">
                        <path
                          d="M12 2a7 7 0 0 0-7 7c0 5.05 5.5 11.55 6.23 12.39a1 1 0 0 0 1.54 0C13.5 20.55 19 14.05 19 9a7 7 0 0 0-7-7zm0 9.5A2.5 2.5 0 1 1 12 6a2.5 2.5 0 0 1 0 5.5z"
                          fill="currentColor"
                        />
                      </svg>
                    </span>
                    <span>{userLocation ? "現在地を更新" : "現在地を使う"}</span>
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
        </div>
      </header>

      <section className="results" ref={resultsRef}>
        <div className="results-body">
          <div className="results-list" ref={resultsListRef}>
            <div className="results-head">
              <h2>検索結果</h2>
              {(prefectureFilter || orgFilter) && (
                <div className="prefecture-filter">
                  {prefectureFilter && <span>都道府県: {prefectureFilter}</span>}
                  {orgFilter && <span>機関: {orgFilter}</span>}
                  <button type="button" onClick={handlePrefectureRestore}>
                    元に戻す
                  </button>
                </div>
              )}
            </div>
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
                        <button
                          type="button"
                          className="link-button secondary"
                          onClick={(event) => {
                            event.stopPropagation();
                            handleEqnetAssistOpen(item);
                          }}
                        >
                          eqnetで確認
                        </button>
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
          <aside
            className="map-panel"
            style={
              !isNarrowLayout && resultsListHeight
                ? { height: `${resultsListHeight}px` }
                : undefined
            }
          >
            <div className="map-head" aria-hidden="true" />
            <div className="map-canvas">
              <div
                className="jp-map-geo"
                role="img"
                aria-label="全国分布の地図"
                ref={mapContainerRef}
                onMouseLeave={() => setMapHover(null)}
                onPointerDown={handleMapPointerDown}
                onPointerMove={handleMapPointerMove}
                onPointerUp={handleMapPointerUp}
                onPointerCancel={handleMapPointerUp}
              >
                {geoJsonStatus === "error" ? (
                  <div className="jp-map-empty">地図データの読み込みに失敗しました。</div>
                ) : prefectureShapes.length === 0 ? (
                  <div className="jp-map-empty">地図データを読み込み中です。</div>
                ) : (
                  <svg
                    className="jp-map-svg"
                    viewBox={`${mapViewport.minX} ${mapViewport.minY} ${mapViewport.width} ${mapViewport.height}`}
                    preserveAspectRatio="xMidYMid meet"
                  >
                    <g className="jp-map-shapes">
                      {prefectureShapes.map((shape) => {
                        const equipmentCount =
                          mapData.prefectureCounts?.[shape.prefecture] || 0;
                        const facilityCount =
                          mapData.prefectureFacilityCounts?.[shape.prefecture] || 0;
                        const alpha =
                          maxMapCount > 0
                            ? 0.2 + (equipmentCount / maxMapCount) * 0.6
                            : 0.2;
                        const isSelected =
                          mapInfoPrefecture === shape.prefecture ||
                          prefectureFilter === shape.prefecture;
                        const isEmpty = equipmentCount === 0;
                        return (
                          <path
                            key={shape.prefecture}
                            d={shape.path}
                            className={`jp-map-shape${isSelected ? " is-selected" : ""}${
                              isEmpty ? " is-empty" : ""
                            }`}
                            style={{ "--shape-alpha": alpha.toFixed(2) }}
                            fillRule="evenodd"
                            role="button"
                            tabIndex={0}
                            onClick={() => handleMapPrefectureClick(shape.prefecture)}
                            onMouseEnter={(event) =>
                              handleMapHover(shape.prefecture, event)
                            }
                            onMouseMove={(event) =>
                              handleMapHover(shape.prefecture, event)
                            }
                            onMouseLeave={() => setMapHover(null)}
                            onKeyDown={(event) => {
                              if (event.key === "Enter" || event.key === " ") {
                                event.preventDefault();
                                handleMapPrefectureClick(shape.prefecture);
                              }
                            }}
                          >
                            <title>
                              {shape.prefecture} {equipmentCount}件 / {facilityCount}拠点
                            </title>
                          </path>
                        );
                      })}
                    </g>
                    <g className="jp-map-markers">
                      {prefectureMarkers.map((marker) => {
                        const radius =
                          maxMapCount > 0
                            ? 6 + (marker.equipmentCount / maxMapCount) * 8
                            : 6;
                        const isSelected =
                          mapInfoPrefecture === marker.prefecture ||
                          prefectureFilter === marker.prefecture;
                        const isEmpty = marker.equipmentCount === 0;
                        return (
                          <g
                            key={marker.prefecture}
                            className={`jp-map-marker${isSelected ? " is-selected" : ""}${
                              isEmpty ? " is-empty" : ""
                            }`}
                            transform={`translate(${marker.x} ${marker.y})`}
                            role="button"
                            tabIndex={0}
                            onClick={() => handleMapPrefectureClick(marker.prefecture)}
                            onMouseEnter={(event) =>
                              handleMapHover(marker.prefecture, event)
                            }
                            onMouseMove={(event) =>
                              handleMapHover(marker.prefecture, event)
                            }
                            onMouseLeave={() => setMapHover(null)}
                            onKeyDown={(event) => {
                              if (event.key === "Enter" || event.key === " ") {
                                event.preventDefault();
                                handleMapPrefectureClick(marker.prefecture);
                              }
                            }}
                          >
                            <title>
                              {marker.prefecture} {marker.equipmentCount}件 / {marker.facilityCount}拠点
                            </title>
                            <circle
                              className="jp-map-marker-dot"
                              r={radius.toFixed(2)}
                            />
                            {marker.equipmentCount > 0 && (
                              <text className="jp-map-marker-text" y="4">
                                {marker.equipmentCount}
                              </text>
                            )}
                          </g>
                        );
                      })}
                    </g>
                  </svg>
                )}
                <div className="map-zoom-controls" role="group" aria-label="地図の拡大縮小">
                  <button type="button" onClick={handleMapZoomIn} aria-label="拡大">
                    +
                  </button>
                  <button type="button" onClick={handleMapZoomOut} aria-label="縮小">
                    −
                  </button>
                  <button type="button" onClick={handleMapZoomReset} aria-label="リセット">
                    リセット
                  </button>
                </div>
                {mapInfoData && mapInfoAnchor && (
                  <div
                    className="map-info"
                    style={{
                      "--info-left": `${mapInfoAnchor.left}%`,
                      "--info-top": `${mapInfoAnchor.top}%`,
                    }}
                  >
                    <div className="map-info-head">
                      <div>
                        <h4>{mapInfoData.prefecture}</h4>
                        <p>
                          {mapInfoData.totalEquipment}件 / {mapInfoData.totalFacilities}拠点
                        </p>
                      </div>
                      <div className="map-info-actions">
                        <button
                          type="button"
                          className="ghost"
                          onClick={() => setMapInfoPrefecture("")}
                        >
                          閉じる
                        </button>
                      </div>
                    </div>
                    <div className="map-info-body">
                      <div className="map-info-section">
                        <h5>機器保有機関</h5>
                        {isMapOrgLoading ? (
                          <p className="map-info-empty">読み込み中...</p>
                        ) : mapOrgError ? (
                          <p className="map-info-empty">{mapOrgError}</p>
                        ) : mapInfoData.orgList.length === 0 ? (
                          <p className="map-info-empty">
                            {mapInfoData.totalEquipment > 0
                              ? "機関情報を取得できませんでした。"
                              : "該当なし"}
                          </p>
                        ) : (
                          <ul className="map-info-list">
                            {mapInfoData.orgList.map((org) => (
                              <li key={org.orgName}>
                                <button
                                  type="button"
                                  className="map-org-button"
                                  onClick={() =>
                                    handleOrgSelect(org.orgName, mapInfoData.prefecture)
                                  }
                                >
                                  <span>{org.orgName}</span>
                                  <span>{org.count}件</span>
                                </button>
                              </li>
                            ))}
                          </ul>
                        )}
                      </div>
                    </div>
                    <p className="map-info-note">
                      集計対象: {mapData.usingSummaryCounts ? "集計データ" : "読み込み済みの設備のみ"}
                    </p>
                    {mapInfoData.isPartial && (
                      <p className="map-info-note">
                        詳細一覧は検索結果の読み込み範囲に限られます。
                      </p>
                    )}
                  </div>
                )}
                {mapHover && (
                  <div
                    className="map-tooltip"
                    style={{ left: mapHover.x, top: mapHover.y }}
                  >
                    <strong>{mapHover.prefecture}</strong>
                    <span>
                      {mapHover.equipmentCount}件 / {mapHover.facilityCount}拠点
                    </span>
                  </div>
                )}
              </div>
              <div className="map-legend">
                <span>都道府県をクリックして情報を表示</span>
                {mapData.summaryUpdatedAt && (
                  <span>集計更新: {formatDate(mapData.summaryUpdatedAt)}</span>
                )}
              </div>
            </div>
            <div className="map-list">
              <h4>機器が多い都道府県（地方別）</h4>
              {sortedTopPrefectures.length === 0 ? (
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
                          className="prefecture-row"
                          onClick={() => handlePrefectureSelect(item.prefecture)}
                        >
                          <span className="prefecture-name">
                            <span className="prefecture-main">{item.prefecture}</span>
                            <span className="prefecture-region">{item.region}地方</span>
                          </span>
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

      {eqnetAssistItem && (
        <aside
          className={`eqnet-assist-panel${eqnetAssistAttention ? " is-attention" : ""}`}
          aria-live="polite"
        >
          <div className="eqnet-assist-head">
            <div>
              <h4>eqnet検索補助</h4>
              <p>先に検索語をコピーしてから「eqnetを開く」を押してください。</p>
            </div>
            <button type="button" onClick={handleEqnetAssistClose} aria-label="補助パネルを閉じる">
              閉じる
            </button>
          </div>
          <div className="eqnet-assist-fields">
            <div className="eqnet-assist-field">
              <span>機器名</span>
              <strong>{eqnetAssistItem.name}</strong>
              <button type="button" onClick={() => handleEqnetFieldCopy("name", eqnetAssistItem.name)}>
                {eqnetCopiedField === "name" ? "コピー済み" : "コピー"}
              </button>
            </div>
            {eqnetAssistItem.orgName && (
              <div className="eqnet-assist-field">
                <span>保有機関</span>
                <strong>{eqnetAssistItem.orgName}</strong>
                <button
                  type="button"
                  onClick={() => handleEqnetFieldCopy("org", eqnetAssistItem.orgName)}
                >
                  {eqnetCopiedField === "org" ? "コピー済み" : "コピー"}
                </button>
              </div>
            )}
            {eqnetAssistItem.prefecture && (
              <div className="eqnet-assist-field">
                <span>都道府県</span>
                <strong>{eqnetAssistItem.prefecture}</strong>
                <button
                  type="button"
                  onClick={() => handleEqnetFieldCopy("prefecture", eqnetAssistItem.prefecture)}
                >
                  {eqnetCopiedField === "prefecture" ? "コピー済み" : "コピー"}
                </button>
              </div>
            )}
            {eqnetAssistItem.category && (
              <div className="eqnet-assist-field">
                <span>カテゴリ</span>
                <strong>{eqnetAssistItem.category}</strong>
                <button
                  type="button"
                  onClick={() => handleEqnetFieldCopy("category", eqnetAssistItem.category)}
                >
                  {eqnetCopiedField === "category" ? "コピー済み" : "コピー"}
                </button>
              </div>
            )}
          </div>
          {eqnetAssistItem.hints.length > 0 && (
            <div className="eqnet-assist-hints">
              {eqnetAssistItem.hints.map((hint) => (
                <span key={hint}>{hint}</span>
              ))}
            </div>
          )}
          <div className="eqnet-assist-actions">
            <button type="button" onClick={handleEqnetSummaryCopy}>
              {eqnetCopiedField === "summary" ? "コピー済み" : "まとめてコピー"}
            </button>
            <button type="button" onClick={openEqnetPage}>
              eqnetを開く
            </button>
          </div>
        </aside>
      )}

      {detailItem && (
        <div
          className={`equipment-sheet${detailOpen ? " is-open" : ""}${
            sheetExpanded ? " is-expanded" : ""
          }`}
        >
          <div
            className="equipment-sheet-backdrop"
            aria-hidden="true"
            onClick={() => setDetailOpen(false)}
          />
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
                      <li
                        key={paper.doi}
                        className="paper-item"
                        role="button"
                        tabIndex={0}
                        onClick={() => handlePaperOpen(paper)}
                        onKeyDown={(event) => {
                          if (event.key === "Enter" || event.key === " ") {
                            event.preventDefault();
                            handlePaperOpen(paper);
                          }
                        }}
                      >
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
                            onClick={(event) => event.stopPropagation()}
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
              <button
                type="button"
                className="link-button secondary"
                onClick={() => handleEqnetAssistOpen(detailItem)}
              >
                eqnetで確認
              </button>
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
        <p className="footer-links">
          <a href={TERMS_URL} target="_blank" rel="noreferrer">
            利用規約
          </a>
          <a href={PRIVACY_POLICY_URL} target="_blank" rel="noreferrer">
            プライバシーポリシー
          </a>
          <a href={CONTACT_URL} target="_blank" rel="noreferrer">
            お問い合わせ
          </a>
        </p>
      </footer>
    </div>
  );
}
