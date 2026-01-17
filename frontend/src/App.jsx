import { useMemo, useState } from "react";
import "./App.css";

const EQUIPMENT = [
  {
    id: "eq-001",
    name: "透過型電子顕微鏡 JEM-2100",
    categoryGeneral: "顕微鏡",
    categoryDetail: "電子顕微鏡",
    orgName: "東北大学 金属材料研究所",
    orgType: "国立大学",
    prefecture: "宮城県",
    externalUse: "可",
    feeBand: "有料",
    address: "宮城県仙台市青葉区片平",
    sourceUrl: "https://www.tohoku.ac.jp/ja/research/equipment/",
  },
  {
    id: "eq-002",
    name: "固体NMR 600MHz",
    categoryGeneral: "分析装置",
    categoryDetail: "NMR",
    orgName: "東京大学 物性研究所",
    orgType: "国立大学",
    prefecture: "東京都",
    externalUse: "要相談",
    feeBand: "有料",
    address: "東京都文京区本郷",
    sourceUrl: "https://www.u-tokyo.ac.jp/ja/research/equipment/",
  },
  {
    id: "eq-003",
    name: "X線回折装置 SmartLab",
    categoryGeneral: "分析装置",
    categoryDetail: "XRD",
    orgName: "新潟大学 自然科学研究科",
    orgType: "国立大学",
    prefecture: "新潟県",
    externalUse: "可",
    feeBand: "有料",
    address: "新潟県新潟市西区五十嵐",
    sourceUrl: "https://www.niigata-u.ac.jp/ja/research/equipment/",
  },
  {
    id: "eq-004",
    name: "走査電子顕微鏡 SU5000",
    categoryGeneral: "顕微鏡",
    categoryDetail: "走査電子顕微鏡",
    orgName: "産総研 つくばセンター",
    orgType: "公的研究機関",
    prefecture: "茨城県",
    externalUse: "可",
    feeBand: "有料",
    address: "茨城県つくば市梅園",
    sourceUrl: "https://www.aist.go.jp/aist_j/rd/equipment/",
  },
  {
    id: "eq-005",
    name: "材料強度試験機 100kN",
    categoryGeneral: "評価装置",
    categoryDetail: "機械試験",
    orgName: "NIMS 構造材料研究センター",
    orgType: "公的研究機関",
    prefecture: "茨城県",
    externalUse: "要相談",
    feeBand: "有料",
    address: "茨城県つくば市千現",
    sourceUrl: "https://www.nims.go.jp/eng/facility/",
  },
  {
    id: "eq-006",
    name: "超電導マグネット 11T",
    categoryGeneral: "低温・磁場",
    categoryDetail: "超電導磁石",
    orgName: "早稲田大学 理工学術院",
    orgType: "私立大学",
    prefecture: "東京都",
    externalUse: "不可",
    feeBand: "不明",
    address: "東京都新宿区大久保",
    sourceUrl: "https://www.waseda.jp/top/contact/",
  },
  {
    id: "eq-007",
    name: "レーザードップラー振動計",
    categoryGeneral: "計測装置",
    categoryDetail: "振動解析",
    orgName: "長岡工業高専 機械工学科",
    orgType: "高等専門学校",
    prefecture: "新潟県",
    externalUse: "可",
    feeBand: "無料",
    address: "新潟県長岡市西片貝町",
    sourceUrl: "https://www.nagaoka-ct.ac.jp/contact/",
  },
  {
    id: "eq-008",
    name: "クリーンルーム顕微鏡",
    categoryGeneral: "顕微鏡",
    categoryDetail: "光学顕微鏡",
    orgName: "慶應義塾大学 理工学部",
    orgType: "私立大学",
    prefecture: "神奈川県",
    externalUse: "可",
    feeBand: "有料",
    address: "神奈川県横浜市港北区日吉",
    sourceUrl: "https://www.keio.ac.jp/ja/contacts/",
  },
  {
    id: "eq-009",
    name: "薄膜成膜装置 RFスパッタ",
    categoryGeneral: "プロセス装置",
    categoryDetail: "薄膜形成",
    orgName: "仙台高専 材料システム工学科",
    orgType: "高等専門学校",
    prefecture: "宮城県",
    externalUse: "要相談",
    feeBand: "有料",
    address: "宮城県名取市愛島塩手",
    sourceUrl: "https://www.sendai-nct.ac.jp/contact/",
  },
];

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

const CATEGORY_OPTIONS = Array.from(
  new Set(EQUIPMENT.map((item) => item.categoryGeneral)),
).sort();

const REGION_OPTIONS = REGION_ORDER;

const badgeClass = (value) => {
  if (value === "可") return "badge badge-ok";
  if (value === "要相談") return "badge badge-warn";
  return "badge badge-muted";
};

export default function App() {
  const [query, setQuery] = useState("");
  const [region, setRegion] = useState("all");
  const [category, setCategory] = useState("all");
  const [externalOnly, setExternalOnly] = useState(false);
  const [freeOnly, setFreeOnly] = useState(false);

  const handleReset = () => {
    setQuery("");
    setRegion("all");
    setCategory("all");
    setExternalOnly(false);
    setFreeOnly(false);
  };

  const analysisItems = useMemo(() => {
    const normalized = query.trim();
    return EQUIPMENT.filter((item) => {
      const matchesQuery =
        normalized.length === 0 ||
        item.name.includes(normalized) ||
        item.orgName.includes(normalized);
      const matchesCategory = category === "all" || item.categoryGeneral === category;
      const matchesExternal = !externalOnly || item.externalUse === "可";
      const matchesFree = !freeOnly || item.feeBand === "無料";
      return matchesQuery && matchesCategory && matchesExternal && matchesFree;
    });
  }, [query, category, externalOnly, freeOnly]);

  const filteredItems = useMemo(() => {
    return analysisItems.filter((item) => {
      const mappedRegion = REGION_MAP[item.prefecture] || "その他";
      return region === "all" || mappedRegion === region;
    });
  }, [analysisItems, region]);

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
              <strong>2025.01 (サンプル)</strong>
            </div>
            <div>
              <span>登録設備</span>
              <strong>{EQUIPMENT.length} 件</strong>
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
              {REGION_OPTIONS.map((item) => (
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
              {CATEGORY_OPTIONS.map((item) => (
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
            <p>{filteredItems.length} 件の設備が見つかりました</p>
          </div>
        </div>
        <div className="card-grid">
          {filteredItems.map((item, index) => (
            <article
              key={item.id}
              className="card"
              style={{ animationDelay: `${index * 80}ms` }}
            >
              <div className="card-header">
                <p className="category">{item.categoryGeneral}</p>
                <span className={badgeClass(item.externalUse)}>{item.externalUse}</span>
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
                <a href={item.sourceUrl} target="_blank" rel="noreferrer">
                  機器紹介・問い合わせへ
                </a>
              </div>
            </article>
          ))}
        </div>
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
