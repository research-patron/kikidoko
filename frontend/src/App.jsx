import { useEffect, useMemo, useState } from "react";
import { collection, getDocs } from "firebase/firestore";
import "./App.css";
import { db } from "./firebase";

const REGION_MAP = {
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

const PREFECTURE_COORD_VALUES = Object.values(PREFECTURE_COORDS);
const MAP_BOUNDS = PREFECTURE_COORD_VALUES.reduce(
  (acc, coord) => {
    acc.minLat = Math.min(acc.minLat, coord.lat);
    acc.maxLat = Math.max(acc.maxLat, coord.lat);
    acc.minLng = Math.min(acc.minLng, coord.lng);
    acc.maxLng = Math.max(acc.maxLng, coord.lng);
    return acc;
  },
  { minLat: 90, maxLat: -90, minLng: 180, maxLng: -180 },
);
const MAP_RANGE = {
  lat: MAP_BOUNDS.maxLat - MAP_BOUNDS.minLat || 1,
  lng: MAP_BOUNDS.maxLng - MAP_BOUNDS.minLng || 1,
};
const MAP_WIDTH = 100;
const MAP_HEIGHT = 140;

const ALIAS_MAP = {
  xrd: ["x線回折", "x線回折装置", "x-ray diffraction", "xray diffraction"],
  sem: ["走査型電子顕微鏡", "scanning electron microscope"],
  tem: ["透過型電子顕微鏡", "transmission electron microscope"],
  xps: ["x線光電子分光", "x-ray photoelectron spectroscopy"],
  nmr: ["核磁気共鳴", "nuclear magnetic resonance"],
  ftir: ["フーリエ変換赤外分光", "fourier transform infrared"],
  afm: ["原子間力顕微鏡", "atomic force microscope"],
  "lc-ms": ["液体クロマトグラフ質量分析", "lcms"],
  "gc-ms": ["ガスクロマトグラフ質量分析", "gcms"],
  "x-ray": ["x線", "xray"],
};

const EQNET_BASE_URL = "https://eqnet.jp";
const PAGE_SIZE = 8;

const badgeClass = (value) => {
  if (value === "可") return "badge badge-ok";
  if (value === "要相談") return "badge badge-warn";
  return "badge badge-muted";
};

const externalLabel = (value) => {
  return value || "不明";
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

const toMapPosition = (coord) => {
  if (!coord) return null;
  const x = ((coord.lng - MAP_BOUNDS.minLng) / MAP_RANGE.lng) * MAP_WIDTH;
  const y = (1 - (coord.lat - MAP_BOUNDS.minLat) / MAP_RANGE.lat) * MAP_HEIGHT;
  return { x, y };
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
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [query, setQuery] = useState("");
  const [region, setRegion] = useState("all");
  const [category, setCategory] = useState("all");
  const [externalOnly, setExternalOnly] = useState(false);
  const [freeOnly, setFreeOnly] = useState(false);
  const [page, setPage] = useState(1);
  const [activeExternal, setActiveExternal] = useState(null);
  const [userLocation, setUserLocation] = useState(null);
  const [locationStatus, setLocationStatus] = useState("idle");
  const [locationError, setLocationError] = useState("");

  useEffect(() => {
    let isMounted = true;
    const load = async () => {
      setLoading(true);
      setLoadError("");
      try {
        const snapshot = await getDocs(collection(db, "equipment"));
        const nextItems = snapshot.docs.map((doc) => {
          const data = doc.data() || {};
          return {
            id: data.equipment_id || doc.id,
            name: data.name || "名称不明",
            categoryGeneral: data.category_general || "未分類",
            categoryDetail: data.category_detail || "",
            orgName: data.org_name || "不明",
            orgType: data.org_type || "不明",
            prefecture: data.prefecture || "不明",
            externalUse: data.external_use || "不明",
            feeBand: feeLabel(data.fee_band),
            address: data.address_raw || "所在地不明",
            sourceUrl: data.source_url || "",
            eqnetUrl: data.eqnet_url || "",
            crawledAt: data.crawled_at || "",
          };
        });
        nextItems.sort((a, b) => a.name.localeCompare(b.name, "ja"));
        if (isMounted) {
          setItems(nextItems);
        }
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
    load();
    return () => {
      isMounted = false;
    };
  }, []);

  useEffect(() => {
    setPage(1);
  }, [query, region, category, externalOnly, freeOnly]);

  useEffect(() => {
    if (!activeExternal) return undefined;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = previousOverflow;
    };
  }, [activeExternal]);

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

  const handleReset = () => {
    setQuery("");
    setRegion("all");
    setCategory("all");
    setExternalOnly(false);
    setFreeOnly(false);
    setPage(1);
  };

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

  const categoryOptions = useMemo(() => {
    return Array.from(
      new Set(items.map((item) => item.categoryGeneral).filter(Boolean)),
    ).sort();
  }, [items]);

  const termGroups = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    if (!normalized) return [];
    return normalized.split(/\s+/).map((term) => [term, ...(ALIAS_MAP[term] || [])]);
  }, [query]);

  const analysisItems = useMemo(() => {
    return items.filter((item) => {
      const haystack = `${item.name} ${item.orgName} ${item.categoryGeneral} ${item.categoryDetail} ${item.prefecture}`.toLowerCase();
      const matchesQuery =
        termGroups.length === 0 ||
        termGroups.every((group) => group.some((term) => haystack.includes(term)));
      const matchesCategory = category === "all" || item.categoryGeneral === category;
      const matchesExternal = !externalOnly || item.externalUse === "可";
      const matchesFree = !freeOnly || item.feeBand === "無料";
      return matchesQuery && matchesCategory && matchesExternal && matchesFree;
    });
  }, [items, termGroups, category, externalOnly, freeOnly]);

  const filteredItems = useMemo(() => {
    return analysisItems.filter((item) => {
      const mappedRegion = REGION_MAP[item.prefecture] || "その他";
      return region === "all" || mappedRegion === region;
    });
  }, [analysisItems, region]);

  const itemsWithDistance = useMemo(() => {
    if (!userLocation) {
      return filteredItems.map((item) => ({ ...item, distanceKm: null }));
    }
    return filteredItems.map((item) => {
      const coord = PREFECTURE_COORDS[item.prefecture];
      return {
        ...item,
        distanceKm: coord ? getDistanceKm(userLocation, coord) : null,
      };
    });
  }, [filteredItems, userLocation]);

  const sortedItems = useMemo(() => {
    if (!userLocation) return itemsWithDistance;
    return [...itemsWithDistance].sort((a, b) => {
      if (a.distanceKm == null && b.distanceKm == null) {
        return a.name.localeCompare(b.name, "ja");
      }
      if (a.distanceKm == null) return 1;
      if (b.distanceKm == null) return -1;
      return a.distanceKm - b.distanceKm;
    });
  }, [itemsWithDistance, userLocation]);

  const totalPages = useMemo(() => {
    return Math.max(1, Math.ceil(sortedItems.length / PAGE_SIZE));
  }, [sortedItems.length]);

  const pagedItems = useMemo(() => {
    const start = (page - 1) * PAGE_SIZE;
    return sortedItems.slice(start, start + PAGE_SIZE);
  }, [sortedItems, page]);

  const pageStart = sortedItems.length === 0 ? 0 : (page - 1) * PAGE_SIZE + 1;
  const pageEnd = Math.min(page * PAGE_SIZE, sortedItems.length);

  const latestUpdate = useMemo(() => {
    if (!items.length) return "未設定";
    const latest = items.reduce((acc, item) => {
      if (!item.crawledAt) return acc;
      return !acc || item.crawledAt > acc ? item.crawledAt : acc;
    }, "");
    return formatDate(latest);
  }, [items]);

  const mapData = useMemo(() => {
    const prefectureCounts = {};
    const prefectureOrgs = {};
    analysisItems.forEach((item) => {
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

    const points = Object.keys(prefectureCounts)
      .map((prefecture) => {
        const coord = PREFECTURE_COORDS[prefecture];
        const pos = toMapPosition(coord);
        if (!coord || !pos) return null;
        return {
          prefecture,
          equipmentCount: prefectureCounts[prefecture],
          facilityCount: prefectureOrgs[prefecture].size,
          x: pos.x,
          y: pos.y,
        };
      })
      .filter(Boolean);

    const maxEquipment = Math.max(1, ...points.map((point) => point.equipmentCount));
    const totalFacilities = new Set(
      analysisItems.map((item) => item.orgName).filter(Boolean),
    ).size;

    const topPrefectures = Object.keys(prefectureCounts)
      .map((prefecture) => ({
        prefecture,
        equipmentCount: prefectureCounts[prefecture],
        facilityCount: prefectureOrgs[prefecture].size,
      }))
      .sort((a, b) => b.equipmentCount - a.equipmentCount)
      .slice(0, 6);

    const userPoint = userLocation ? toMapPosition(userLocation) : null;

    return {
      points,
      maxEquipment,
      totalFacilities,
      totalEquipment: analysisItems.length,
      prefectureCount: Object.keys(prefectureCounts).length,
      topPrefectures,
      userPoint,
    };
  }, [analysisItems, userLocation]);

  const locationBadge = (() => {
    if (locationStatus === "loading") return "現在地を取得中...";
    if (locationStatus === "error") return locationError;
    if (userLocation) return "現在地から近い順に並び替え中";
    return "距離順にするには現在地を設定";
  })();

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
              <div>
                <span>登録設備</span>
                <strong>{items.length} 件</strong>
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
              value={query}
              onChange={(event) => setQuery(event.target.value)}
            />
            <button type="button" onClick={() => setPage(1)}>
              検索する
            </button>
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
              <button
                className="ghost"
                type="button"
                onClick={requestLocation}
                disabled={locationStatus === "loading"}
              >
                {userLocation ? "現在地を更新" : "現在地を使う"}
              </button>
              <button className="ghost" type="button" onClick={handleReset}>
                条件をリセット
              </button>
            </div>
            <p className={locationStatus === "error" ? "location-note error" : "location-note"}>
              {locationBadge}
            </p>
          </div>
        </div>
      </header>

      <section className="results">
        <div className="results-head">
          <div>
            <h2>検索結果</h2>
            <p>
              {sortedItems.length} 件の設備が見つかりました{" "}
              {sortedItems.length > 0 && `(${pageStart}-${pageEnd}件を表示)`}
            </p>
          </div>
          {userLocation && <p className="distance-note">現在地から近い順に表示中</p>}
        </div>
        <div className="results-body">
          <div className="results-list">
            {loading ? (
              <p className="results-status">データを読み込んでいます...</p>
            ) : loadError ? (
              <p className="results-status error">{loadError}</p>
            ) : sortedItems.length === 0 ? (
              <p className="results-status">該当する設備が見つかりませんでした。</p>
            ) : (
              <>
                <div className="list-header">
                  <span>設備</span>
                  <span>機関</span>
                  <span>所在地</span>
                  <span>距離</span>
                  <span>利用</span>
                  <span>リンク</span>
                </div>
                <div className="list-body">
                  {pagedItems.map((item) => (
                    <div key={item.id} className="result-row">
                      <div className="result-title">
                        <p className="category">{item.categoryGeneral}</p>
                        <strong>{item.name}</strong>
                        {item.categoryDetail && (
                          <span className="detail">{item.categoryDetail}</span>
                        )}
                      </div>
                      <div className="result-org">
                        <span>{item.orgName}</span>
                        <span className="muted">{item.orgType}</span>
                      </div>
                      <div className="result-location">
                        <span>{item.prefecture}</span>
                        <span className="muted">{item.address}</span>
                      </div>
                      <div className="result-distance">
                        {formatDistance(item.distanceKm)}
                      </div>
                      <div className="result-tags">
                        <span className={badgeClass(item.externalUse)}>
                          {externalLabel(item.externalUse)}
                        </span>
                        <span className="fee">{item.feeBand}</span>
                      </div>
                      <div className="result-actions">
                        {item.sourceUrl ? (
                          <button
                            type="button"
                            className="link-button"
                            onClick={() => handleExternalOpen(item)}
                          >
                            機器紹介・問い合わせへ
                          </button>
                        ) : (
                          <span className="link-disabled">情報元なし</span>
                        )}
                        <a
                          href={buildEqnetLink(item)}
                          className="link-button secondary"
                          target="_blank"
                          rel="noreferrer"
                        >
                          eqnetで利用登録
                        </a>
                      </div>
                    </div>
                  ))}
                </div>
              </>
            )}
            {!loading && !loadError && sortedItems.length > PAGE_SIZE && (
              <div className="pagination">
                <button
                  type="button"
                  className="ghost"
                  onClick={() => setPage((current) => Math.max(1, current - 1))}
                  disabled={page === 1}
                >
                  前へ
                </button>
                <span>
                  {page} / {totalPages}
                </span>
                <button
                  type="button"
                  className="ghost"
                  onClick={() => setPage((current) => Math.min(totalPages, current + 1))}
                  disabled={page === totalPages}
                >
                  次へ
                </button>
              </div>
            )}
          </div>
          <aside className="map-panel">
            <div className="map-head">
              <div>
                <h3>全国分布</h3>
                <p>検索条件（地域以外）に合わせて拠点と機器数を俯瞰します。</p>
              </div>
              <div className="map-stats">
                <div>
                  <span>拠点</span>
                  <strong>{mapData.totalFacilities} 拠点</strong>
                </div>
                <div>
                  <span>機器</span>
                  <strong>{mapData.totalEquipment} 件</strong>
                </div>
                <div>
                  <span>都道府県</span>
                  <strong>{mapData.prefectureCount} 都道府県</strong>
                </div>
              </div>
            </div>
            <div className="map-canvas">
              <svg
                viewBox={`0 0 ${MAP_WIDTH} ${MAP_HEIGHT}`}
                className="map-svg"
                role="img"
                aria-label="研究設備の分布"
              >
                {mapData.points.map((point) => {
                  const radius = 3 + (point.equipmentCount / mapData.maxEquipment) * 9;
                  return (
                    <circle
                      key={point.prefecture}
                      cx={point.x}
                      cy={point.y}
                      r={radius}
                      className="map-dot"
                    >
                      <title>
                        {`${point.prefecture} / 機器 ${point.equipmentCount} 件 / 拠点 ${point.facilityCount} 拠点`}
                      </title>
                    </circle>
                  );
                })}
                {mapData.userPoint && (
                  <circle
                    cx={mapData.userPoint.x}
                    cy={mapData.userPoint.y}
                    r={4}
                    className="map-user"
                  >
                    <title>現在地</title>
                  </circle>
                )}
              </svg>
              <div className="map-legend">
                <span>点の大きさ: 機器件数</span>
                <span>点の位置: 都道府県の中心</span>
              </div>
            </div>
            <div className="map-list">
              <h4>機器が多い都道府県</h4>
              <ul>
                {mapData.topPrefectures.map((item) => (
                  <li key={item.prefecture}>
                    <span>{item.prefecture}</span>
                    <span>{item.equipmentCount} 件</span>
                    <span>{item.facilityCount} 拠点</span>
                  </li>
                ))}
              </ul>
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

      <footer className="footer">
        <p>データは公的機関が公開する情報をもとに収集・更新します。</p>
        <p>利用登録や手続きはeqnet側で実施してください。</p>
      </footer>
    </div>
  );
}
