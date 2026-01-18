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

const PAGE_SIZE = 8;

const formatDate = (value) => {
  if (!value) return "未設定";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "未設定";
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}.${month}.${day}`;
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
            crawledAt: data.crawled_at || "",
          };
        });
        nextItems.sort((a, b) => a.name.localeCompare(b.name, "ja"));
        if (isMounted) {
          setItems(nextItems);
        }
      } catch (error) {
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

  const handleReset = () => {
    setQuery("");
    setRegion("all");
    setCategory("all");
    setExternalOnly(false);
    setFreeOnly(false);
    setPage(1);
  };

  const categoryOptions = useMemo(() => {
    return Array.from(
      new Set(items.map((item) => item.categoryGeneral).filter(Boolean)),
    ).sort();
  }, [items]);

  const analysisItems = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    const terms = normalized.length ? normalized.split(/\s+/) : [];
    return items.filter((item) => {
      const haystack = `${item.name} ${item.orgName}`.toLowerCase();
      const matchesQuery =
        terms.length === 0 || terms.every((term) => haystack.includes(term));
      const matchesCategory = category === "all" || item.categoryGeneral === category;
      const matchesExternal = !externalOnly || item.externalUse === "可";
      const matchesFree = !freeOnly || item.feeBand === "無料";
      return matchesQuery && matchesCategory && matchesExternal && matchesFree;
    });
  }, [items, query, category, externalOnly, freeOnly]);

  const filteredItems = useMemo(() => {
    return analysisItems.filter((item) => {
      const mappedRegion = REGION_MAP[item.prefecture] || "その他";
      return region === "all" || mappedRegion === region;
    });
  }, [analysisItems, region]);

  const totalPages = useMemo(() => {
    return Math.max(1, Math.ceil(filteredItems.length / PAGE_SIZE));
  }, [filteredItems.length]);

  const pagedItems = useMemo(() => {
    const start = (page - 1) * PAGE_SIZE;
    return filteredItems.slice(start, start + PAGE_SIZE);
  }, [filteredItems, page]);

  const pageStart = filteredItems.length === 0 ? 0 : (page - 1) * PAGE_SIZE + 1;
  const pageEnd = Math.min(page * PAGE_SIZE, filteredItems.length);

  const latestUpdate = useMemo(() => {
    if (!items.length) return "未設定";
    const latest = items.reduce((acc, item) => {
      if (!item.crawledAt) return acc;
      return !acc || item.crawledAt > acc ? item.crawledAt : acc;
    }, "");
    return formatDate(latest);
  }, [items]);

  const regionStats = useMemo(() => {
    const counts = REGION_ORDER.reduce((acc, key) => {
      acc[key] = 0;
      return acc;
    }, {});
    analysisItems.forEach((item) => {
      const mappedRegion = REGION_MAP[item.prefecture] || "その他";
      if (counts[mappedRegion] !== undefined) {
        counts[mappedRegion] += 1;
      }
    });
    const max = Math.max(1, ...Object.values(counts));
    return REGION_ORDER.map((regionKey) => ({
      region: regionKey,
      count: counts[regionKey],
      ratio: counts[regionKey] / max,
    }));
  }, [analysisItems]);

  return (
    <div className="page">
      <header className="hero">
        <div className="hero-copy">
          <p className="eyebrow">公的機関の研究設備を、地域から探す</p>
          <h1>
            Kikidoko
            <span>研究設備の横断検索</span>
          </h1>
          <p className="lead">
            国立研究機関・国立大学・私立大学・高専の共用設備を一箇所で検索。
            地域別の分布を俯瞰しながら、最適な設備へアクセスできます。
          </p>
          <div className="search-row">
            <input
              type="text"
              placeholder="機器名 / 機関名で検索"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
            />
            <button type="button">検索する</button>
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
        <aside className="filters">
          <div className="filters-head">
            <div>
              <p className="filters-title">検索条件</p>
              <p className="filters-sub">地域やカテゴリで絞り込み</p>
            </div>
            <button className="ghost" type="button" onClick={handleReset}>
              条件をリセット
            </button>
          </div>
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
          <div className="filter filter-inline">
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
        </aside>
      </header>

      <section className="results">
        <div className="results-head">
          <div>
            <h2>検索結果</h2>
            <p>
              {filteredItems.length} 件の設備が見つかりました{" "}
              {filteredItems.length > 0 && `(${pageStart}-${pageEnd}件を表示)`}
            </p>
          </div>
        </div>
        {loading ? (
          <p className="results-status">データを読み込んでいます...</p>
        ) : loadError ? (
          <p className="results-status error">{loadError}</p>
        ) : filteredItems.length === 0 ? (
          <p className="results-status">該当する設備が見つかりませんでした。</p>
        ) : (
          <div className="card-grid">
            {pagedItems.map((item, index) => (
              <article
                key={item.id}
                className="card"
                style={{ animationDelay: `${index * 80}ms` }}
              >
                <div className="card-header">
                  <p className="category">{item.categoryGeneral}</p>
                  <span className={badgeClass(item.externalUse)}>
                    {externalLabel(item.externalUse)}
                  </span>
                </div>
                <h3>{item.name}</h3>
                <p className="org">{item.orgName}</p>
                <div className="meta">
                  <span>{item.prefecture}</span>
                  <span>{item.feeBand}</span>
                </div>
                <p className="address">{item.address}</p>
                <div className="card-footer">
                  <span>{item.orgType}</span>
                  {item.sourceUrl ? (
                    <a href={item.sourceUrl} target="_blank" rel="noreferrer">
                      機器紹介・問い合わせへ
                    </a>
                  ) : (
                    <span className="link-disabled">情報元なし</span>
                  )}
                </div>
              </article>
            ))}
          </div>
        )}
        {!loading && !loadError && filteredItems.length > PAGE_SIZE && (
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
      </section>

      <section className="analysis">
        <div className="section-title">
          <h2>地域別の分布</h2>
          <p>検索条件に応じた設備件数の傾向を表示します。</p>
        </div>
        <div className="region-bars">
          {regionStats.map((stat) => (
            <div className="region-bar" key={stat.region}>
              <span>{stat.region}</span>
              <div className="bar-track">
                <div
                  className="bar-fill"
                  style={{ width: `${Math.round(stat.ratio * 100)}%` }}
                />
              </div>
              <strong>{stat.count}</strong>
            </div>
          ))}
        </div>
      </section>

      <footer className="footer">
        <p>データは公的機関が公開する情報をもとに収集・更新します。</p>
        <p>問い合わせは各設備の提供元ページから行ってください。</p>
      </footer>
    </div>
  );
}
