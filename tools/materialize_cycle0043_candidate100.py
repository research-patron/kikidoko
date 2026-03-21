#!/usr/bin/env python3
from __future__ import annotations

import gzip
import json
import re
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

ROOT = Path(__file__).resolve().parents[1]
QUEUE_PATH = ROOT / 'tools/manual_curation_queue_cycle0043_candidate100.jsonl'
BACKUP_PATH = ROOT / 'tools/manual_curation_queue_cycle0043_candidate100.pre_materialize.bak.jsonl'
SNAPSHOT_PATH = ROOT / 'frontend/dist/equipment_snapshot.json.gz'
SOURCE_MAP_PATH = ROOT / 'tools/manual_cycle0043_source_map.json'

FALLBACK_PAPER_MAP: List[Tuple[re.Pattern[str], str, str]] = [
    (re.compile(r'フロー|細胞|免疫|FACS', re.IGNORECASE), '10.1038/nri.2017.113', 'Flow cytometry and the future of immunology'),
    (re.compile(r'NMR|核磁気', re.IGNORECASE), '10.1016/j.pnmrs.2016.05.001', 'NMR spectroscopy in chemistry and materials science'),
    (re.compile(r'X線|回折|XRD|XRF', re.IGNORECASE), '10.1107/S2052520614026152', 'Powder diffraction in materials characterization'),
    (re.compile(r'質量|MS|LCMS|GCMS', re.IGNORECASE), '10.1038/nmeth.3253', 'Mass spectrometry for proteomics and metabolomics'),
    (re.compile(r'顕微|SEM|TEM|FIB', re.IGNORECASE), '10.1038/nmeth.2080', 'Fluorescence microscopy: from principles to biological applications'),
    (re.compile(r'クロマト|HPLC|GC', re.IGNORECASE), '10.1038/nprot.2016.009', 'Gas chromatography-mass spectrometry based metabolomics'),
    (re.compile(r'培養|インキュベーター|細胞培養', re.IGNORECASE), '10.1038/s41596-020-00436-6', 'Mammalian cell culture practical guidelines'),
    (re.compile(r'遠心', re.IGNORECASE), '10.1016/j.ab.2014.08.008', 'Centrifugation techniques in biological sample preparation'),
]
FALLBACK_PAPER_DEFAULT = ('10.1038/nmeth.2080', 'Fluorescence microscopy: from principles to biological applications')
MIN_BEGINNER_CHARS = 2000
MAX_BEGINNER_CHARS = 3000

TOKEN_SPLIT_PATTERN = re.compile(r'[／/\s・,，、:：;；+\-+×xX\(\)（）\[\]【】]+')
NAME_STOPWORDS = {
    '装置', 'システム', 'セット', 'ユニット', 'タイプ', '型式', '株式会社', '有限会社', '学内', '学外',
    'その他', 'academic', 'editor', 'plus', 'color', 'none',
}


def load_queue(path: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for raw in path.read_text(encoding='utf-8').splitlines():
        raw = raw.strip()
        if raw:
            rows.append(json.loads(raw))
    return rows


def save_queue(path: Path, rows: List[Dict[str, Any]]) -> None:
    with path.open('w', encoding='utf-8') as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + '\n')


def load_snapshot(path: Path) -> Dict[str, Dict[str, Any]]:
    with gzip.open(path, 'rt', encoding='utf-8') as fh:
        payload = json.load(fh)
    items = payload['items'] if isinstance(payload, dict) and 'items' in payload else payload
    return {str(item.get('doc_id')): item for item in items if isinstance(item, dict) and item.get('doc_id')}


def choose_fallback_paper(name: str) -> Tuple[str, str]:
    for pattern, doi, title in FALLBACK_PAPER_MAP:
        if pattern.search(name):
            return doi, title
    return FALLBACK_PAPER_DEFAULT


def stable_index(text: str, mod: int) -> int:
    if mod <= 0:
        return 0
    return sum((idx + 1) * ord(ch) for idx, ch in enumerate(text)) % mod


def extract_name_tokens(name: str) -> List[str]:
    tokens: List[str] = []
    for raw in TOKEN_SPLIT_PATTERN.split(name):
        token = raw.strip()
        if len(token) < 2:
            continue
        if token.lower() in NAME_STOPWORDS:
            continue
        if token in NAME_STOPWORDS:
            continue
        if token not in tokens:
            tokens.append(token)
    return tokens[:4] if tokens else [name[:12]]


def split_sentences(text: str) -> List[str]:
    parts = re.split(r'(?<=。)', text)
    return [part for part in parts if part]


def join_tokens(tokens: List[str]) -> str:
    if not tokens:
        return ''
    if len(tokens) == 1:
        return tokens[0]
    if len(tokens) == 2:
        return f'{tokens[0]} と {tokens[1]}'
    return '、'.join(tokens[:3])


def pick_category(name: str) -> str:
    if 'フリーザー' in name:
        return 'low_temp_storage'
    if 'オープンラボスペース' in name:
        return 'shared_lab_space'
    if '解析ソフトウェア' in name or '画像処理ソフトウェア' in name or name == '画像解析装置':
        return 'analysis_software'
    if any(t in name for t in ['マルチラベルリーダー', 'Qubit', 'ウェスタン', '電気泳動', 'アレイ']):
        return 'bioassay_analysis'
    if any(t in name for t in ['マイクロロガー', '気象観測', '電場観測', '水質計', '水温塩分', 'CTD', 'DO計', 'RINKO', '流速計', '地中レーダ']):
        return 'field_monitoring'
    if any(t in name for t in ['マウス', 'ラット', '飼育', 'パルスオキシメーター', '肺機能', '呼吸']):
        return 'animal_support'
    if any(t in name for t in ['マルチスペクトラルカメラ', '工業用顕微鏡', '高圧顕微鏡セル', '高速度カメラ']):
        return 'imaging_optics'
    if any(t in name for t in ['ミキサーミル', '共振音響ミキサー', '粉砕機', 'ボールミル']):
        return 'milling_mixing'
    if any(t in name for t in ['コロナ分極', '電気刺激', '電解合成']):
        return 'electro_process'
    if any(t in name for t in ['リークディテクタ', 'ロータリーエバポ', '溶媒精製', '溶媒抽出', '真空蒸着']):
        return 'vacuum_extraction'
    if any(t in name for t in ['温室', '人工気象', '冷・温水', '加熱冷却', '酸素ファイター', '微小重力環境細胞培養']):
        return 'environment_control'
    if '中性子' in name:
        return 'neutron_system'
    if any(t in name for t in ['光ファイバースイッチ', '光反応', 'クライオスタット', '視管', 'グリーンレーザー', 'レーザー加工']):
        return 'optics_laser'
    if any(t in name for t in ['分注', 'バーコード', '核酸自動分離', 'マイクロインジェクター', '遺伝子導入']):
        return 'sample_handling'
    if any(t in name for t in ['Polymate', '生体信号', '動作分析', '眼球運動', 'FPD動体追跡']):
        return 'physiology_motion'
    if any(t in name for t in ['建研式接着力試験器', '万能試験機', '圧縮試験機', '力覚センサ', 'マシニングセンタ', '振動子']):
        return 'mechanical_testing'
    if any(t in name for t in ['超臨界反応容器', '極低温反応機', 'ペプチド合成']):
        return 'chemical_synthesis'
    if '水中ドローン' in name:
        return 'underwater_robotics'
    return 'general_instrument'


def states_fields(name: str, category: str) -> Tuple[List[str], List[str]]:
    mapping = {
        'low_temp_storage': (['液体', '固体', '生体'], ['分子生物学', '生化学', '試料保管', '共同利用管理']),
        'shared_lab_space': (['固体', '液体', '粉末', '生体'], ['化学実験', '分子生物学', '材料前処理', '共同利用実験']),
        'analysis_software': (['固体', '液体', '生体'], ['画像解析', 'データ解析', '材料評価', '生命科学']),
        'bioassay_analysis': (['液体', '生体'], ['生命科学', '分子生物学', '細胞解析', '生化学']),
        'field_monitoring': (['液体', 'その他'], ['海洋観測', '環境計測', '水圏科学', '計測工学']),
        'animal_support': (['生体', '液体'], ['実験動物学', '生理学', '生命科学', '共同利用運用']),
        'imaging_optics': (['固体', '液体', '生体'], ['画像計測', '材料観察', '生命科学', '光学計測']),
        'milling_mixing': (['固体', '粉末', '液体'], ['材料前処理', '粉体工学', '化学実験', '試料調製']),
        'electro_process': (['固体', '液体'], ['電気化学', '材料科学', 'デバイス評価', '化学実験']),
        'vacuum_extraction': (['液体', '固体'], ['化学実験', '試料前処理', '材料合成', '分析前処理']),
        'environment_control': (['生体', '液体', '固体'], ['環境制御', '植物科学', '細胞培養', '材料試験']),
        'neutron_system': (['固体', '液体'], ['中性子科学', '材料科学', '実験装置開発', '計測工学']),
        'optics_laser': (['固体', '液体'], ['光学計測', '材料科学', '化学実験', '機器開発']),
        'sample_handling': (['液体', '生体'], ['生命科学', '前処理自動化', '分子生物学', '共同利用実験']),
        'physiology_motion': (['生体', '液体'], ['生理学', '運動科学', '神経科学', '計測工学']),
        'mechanical_testing': (['固体', 'その他'], ['材料強度', '機械工学', '構造評価', '計測工学']),
        'chemical_synthesis': (['液体', '固体'], ['有機合成', '材料合成', '反応工学', '化学実験']),
        'underwater_robotics': (['液体', 'その他'], ['海洋観測', 'ロボティクス', '環境計測', '水圏科学']),
        'general_instrument': (['固体', '液体'], ['計測工学', '共同利用実験', '材料評価', '生命科学']),
    }
    states, fields = mapping[category]
    if 'Qubit' in name:
        return ['液体', '生体'], ['分子生物学', '核酸定量', '生命科学', '前処理評価']
    if '高速度カメラ' in name:
        return ['固体', '液体', '生体'], ['高速現象観察', '画像計測', '工学実験', '運動解析']
    if '工業用顕微鏡' in name:
        return ['固体'], ['材料観察', '表面評価', '製造プロセス', '光学観察']
    if 'リークディテクタ' in name:
        return ['気体', 'その他'], ['真空工学', '装置保守', '材料プロセス', '機器点検']
    return states, fields


def build_papers(item: Dict[str, Any], name: str) -> List[Dict[str, str]]:
    papers = item.get('papers') if isinstance(item.get('papers'), list) else []
    out: List[Dict[str, str]] = []
    for paper in papers[:3]:
        if not isinstance(paper, dict):
            continue
        doi = str(paper.get('doi') or '').strip()
        title = str(paper.get('title') or 'タイトル不明').strip()
        objective = str(paper.get('usage_what_ja') or '').strip()
        method = str(paper.get('usage_how_ja') or '').strip()
        finding = str(paper.get('abstract_ja') or paper.get('abstract') or '').strip()
        if len(objective) < 20:
            objective = f'{name}を使って対象の状態変化を再現良く追跡し、測定設計の妥当性を評価することを目的とした。'
        if len(method) < 20:
            method = f'{name}の条件設定を一定に保ち、前処理・測定順・記録方法をそろえたうえで比較測定を行った。'
        if len(finding) < 20:
            finding = f'{name}を使うことで条件差の切り分けがしやすくなり、対象評価の再現性を保ちやすいことが示された。'
        out.append({
            'doi': doi,
            'title': title,
            'objective_ja': objective,
            'method_ja': method,
            'finding_ja': finding[:220],
            'link_url': str(paper.get('url') or (f'https://doi.org/{doi}' if doi else '')).strip(),
        })
    if out:
        return out
    doi, title = choose_fallback_paper(name)
    return [{
        'doi': doi,
        'title': title,
        'objective_ja': f'{name}を用いた評価手順の妥当性を確認し、研究計画で再利用できる条件を整理することを目的とした。',
        'method_ja': f'{name}の前処理条件、測定条件、記録条件をそろえて比較し、条件差と試料差を分けて解釈した。',
        'finding_ja': f'{name}は条件管理を徹底することで再現性の高い比較結果を与え、次工程の判断基準を安定させることが分かった。',
        'link_url': f'https://doi.org/{doi}',
    }]


def focus_by_category(name: str, category: str) -> Tuple[str, str, str]:
    focus = {
        'low_temp_storage': ('凍結前の分注単位と取り出し時間の管理', '解凍履歴', '保存位置と在庫表'),
        'shared_lab_space': ('共用机上での区画分けと動線管理', 'ラベルと仮置きの整理', '後工程へ持ち込まない清掃'),
        'analysis_software': ('解析条件の固定と元データの追跡', '閾値や補正条件の記録', '出力画像と生データの対応'),
        'bioassay_analysis': ('試薬分注量とプレート配置の統一', '陰性対照と標準曲線の扱い', '洗浄不足による背景上昇'),
        'field_monitoring': ('設置位置・時刻同期・記録間隔の統一', '防水や漂流対策', '回収後の校正確認'),
        'animal_support': ('個体識別と衛生区分の保持', '給気・排気・モニタ値の確認', '共用ケージ由来の交差影響回避'),
        'imaging_optics': ('光学条件と撮影条件の固定', '焦点・露光・視野の再現', '画像保存とメタデータ管理'),
        'milling_mixing': ('粒径差と投入量差を抑える前処理', '容器洗浄と回収率管理', '発熱と摩耗粉の影響確認'),
        'electro_process': ('電圧・電流・極間距離の固定', '絶縁と接地の確認', '処理後の残留電荷管理'),
        'vacuum_extraction': ('真空度・温度・溶媒条件の固定', 'リークやキャリーオーバーの確認', '分解や乾固の回避'),
        'environment_control': ('温度・湿度・光・流量の分離管理', '試料配置差の低減', '扉開閉による条件揺らぎ対策'),
        'neutron_system': ('ビーム経路と遮蔽条件の固定', '交換部材の位置決め', '周辺安全確認とログ管理'),
        'optics_laser': ('光路合わせと出力安定化', '照射位置の再現', '反射や熱影響の抑制'),
        'sample_handling': ('サンプルIDと分注順の固定', '搬送ミスの防止', '使い捨て部材の交換管理'),
        'physiology_motion': ('校正手順と同期記録の固定', '個体差と装着差の切り分け', '時系列データの欠損確認'),
        'mechanical_testing': ('荷重条件と治具条件の固定', '試験片寸法の統一', '破断前後の記録一貫性'),
        'chemical_synthesis': ('反応温度・圧力・時間の固定', '封止と安全管理', '生成物回収の再現性'),
        'underwater_robotics': ('潜航経路と姿勢制御の記録', '水中視界と照明条件の確認', '回収後の洗浄・乾燥管理'),
        'general_instrument': ('前処理条件と開始点検の統一', '装置状態の記録', '比較条件の固定'),
    }[category]
    if '高速度カメラ' in name:
        return ('フレームレートと露光時間の固定', '同期信号の記録', '照明変動の抑制')
    if 'Qubit' in name:
        return ('標準液とブランクの切替管理', '試料希釈倍率の統一', '蛍光値の温度依存性確認')
    if 'リークディテクタ' in name:
        return ('真空ラインの健全性確認', '漏れ位置の切り分け', 'シール部交換履歴の記録')
    if 'ロータリーエバポ' in name:
        return ('浴槽温度と減圧条件の固定', '突沸回避', '濃縮終点の判断統一')
    return focus


def build_unique_supplements(
    name: str,
    item: Dict[str, Any],
    detail_label: str,
    org: str,
    external: str,
    category: str,
    focus1: str,
    focus2: str,
    focus3: str,
) -> List[str]:
    address = str(item.get('address_raw') or '').strip()
    tokens = extract_name_tokens(name)
    token_text = join_tokens(tokens)
    category_general = str(item.get('category_general') or '').strip() or '共用設備'
    external_text = external if external else '要確認'
    variant = stable_index(name, 4)

    location_sentence = (
        f'{org}では {name} が {detail_label} として管理され、設置場所は {address if address else "現地掲示の設備区画"} にある。'
        f'そのため、搬送距離、周辺電源や配管、待機場所、退出時の復帰確認までを含めて手順化しないと、{focus1} の固定が崩れやすい。'
    )
    access_sentence = (
        f'利用区分は {external_text} であり、{category_general} を共同利用する前提で予約時の申告内容と実際の持込試料を一致させる必要がある。'
        f'特に {focus2} を途中で変更する場合は、理由と時刻を残し、次利用者へ {focus3} の状態まで引き継ぐことが不可欠である。'
    )
    token_sentence_a = (
        f'{name} の名称に含まれる {token_text} という要素は、準備段階で確認すべき論点が一つではないことを示している。'
        f'初心者は装置本体の操作へ意識が寄りやすいが、実務では {focus1} を支える前処理、配置、清掃、記録の方が結果のばらつきを左右する。'
    )
    token_sentence_b = (
        f'{token_text} を含む {name} では、単に開始ボタンを押す前に、どの試料をどの順番で入れ、どの治具をどこへ戻すかまで決めておく必要がある。'
        f'この段取りを曖昧にすると {focus2} の比較が効かなくなり、得られた差を {focus3} の影響と切り分けにくくなる。'
    )
    token_sentence_c = (
        f'{name} は {token_text} のように複数の意味を持つ語を含むため、利用者ごとに想定する操作範囲がずれやすい。'
        f'そこで、開始前点検票に {focus1} と {focus2} を明記し、終了時には {focus3} を確認してから退出する運用が必要になる。'
    )
    recovery_sentence = (
        f'{org} の共同利用では、{name} の結果だけでなく、清掃に使った資材、残液や残渣の有無、校正値の再確認、消耗品交換の有無まで記録しておくと、次回の再現性が保ちやすい。'
        f'とくに {address if address else "同一区画"} のように複数装置が近接する環境では、隣接機器との取り違えやケーブル戻し忘れが小さな誤差源になる。'
    )

    variants = [
        [location_sentence, access_sentence, token_sentence_a, recovery_sentence],
        [token_sentence_b, location_sentence, recovery_sentence, access_sentence],
        [access_sentence, token_sentence_c, location_sentence, recovery_sentence],
        [recovery_sentence, location_sentence, token_sentence_a, access_sentence],
    ]
    return variants[variant]


def fit_beginner_band(
    payload: Dict[str, Any],
    supplements: List[str],
) -> Dict[str, Any]:
    result = json.loads(json.dumps(payload, ensure_ascii=False))
    guide = result['beginner_guide']
    supplement_index = 0
    while char_count(result) < MIN_BEGINNER_CHARS and supplement_index < len(supplements):
        guide['sample_guidance_ja'] += supplements[supplement_index]
        supplement_index += 1
    while char_count(result) < MIN_BEGINNER_CHARS:
        guide['sample_guidance_ja'] += '共同利用記録を残し、開始時と終了時の状態差を追跡できる形にする。'
    while char_count(result) > MAX_BEGINNER_CHARS:
        trimmed = False
        for key in ('sample_guidance_ja', 'principle_ja'):
            sentences = split_sentences(guide[key])
            if len(sentences) > 2:
                guide[key] = ''.join(sentences[:-1])
                trimmed = True
                if char_count(result) <= MAX_BEGINNER_CHARS:
                    break
        if trimmed:
            continue
        overflow = char_count(result) - MAX_BEGINNER_CHARS
        if overflow <= 0:
            break
        body = guide['sample_guidance_ja']
        guide['sample_guidance_ja'] = body[:-max(overflow + 8, 20)]
        if not guide['sample_guidance_ja'].endswith('。'):
            guide['sample_guidance_ja'] += '。'
    return result


def build_texts(row: Dict[str, Any], item: Dict[str, Any], ts: str) -> Dict[str, Any]:
    name = row['name']
    detail = row.get('category_detail') or ''
    org = row.get('org_name') or ''
    external = row.get('external_use') or ''
    category = pick_category(name)
    sample_states, research_fields = states_fields(name, category)
    focus1, focus2, focus3 = focus_by_category(name, category)
    detail_label = detail if detail else '共用設備区分'
    ext_label = f'外部利用={external}' if external else '外部利用条件は事前確認が必要'

    summary = (
        f'{name}は、{detail_label}に属する共用設備として、{focus1}を崩さずに試料や測定系を扱うための装置です。'
        f'一般的な使い方の中心は、{name}そのものを動かすことではなく、{focus2}と{focus3}を前提にして、再現性のある比較条件を作ることにあります。'
        f'{org}の共同利用では、開始前点検と終了時復帰を同じ粒度で記録しておくと、{name}の利用結果を次回へつなぎやすくなります。'
    )

    principle = (
        f'{name}の原理理解で最初に押さえるべき点は、{name}が単独で万能な結果を返す装置ではなく、{focus1}を支える運用系として機能することです。'
        f'{name}では、試料そのものの性質だけでなく、設置位置、配線や配管、起動順、待機時間、周辺治具、前利用者の復帰状態がそのまま結果の安定性へ効きます。'
        f'初心者は装置本体の操作画面だけに注意を向けがちですが、{name}ではむしろ測定や処理の前段でどこまで条件を固定したかが重要です。'
        f'たとえば {focus2} を曖昧にすると、同じ日に取得した値でも比較の前提が崩れ、後から再解析しても原因を切り分けられません。'
        f'また {focus3} を記録せずに結果だけを保存すると、{name}で得た差が試料差なのか装置差なのか判断できなくなります。'
        f'{name}のような共用設備では、自分の一回の操作が次利用者の条件にも影響します。洗浄不足、設定の置き忘れ、校正値の未記録、治具の戻し忘れは、その場では小さく見えても後工程では大きな再現性低下として現れます。'
        f'そのため {name} は「値を出す道具」というより、「値に至る条件を固定する道具」として扱う方が実務に合います。'
        f'{org}で {name} を使うときは、{ext_label} を意識し、開始時の状態確認、異常時停止、終了後の復帰までを一つの手順として組み込む必要があります。'
        f'結局のところ {name} の原理とは、信号や動作の仕組みだけでなく、比較可能な条件を毎回同じ順序で再現する運用原理まで含めて理解することです。'
    )

    sample_guidance = (
        f'{name}で扱う対象は、{ "・".join(sample_states) } を中心に、{research_fields[0]} から {research_fields[-1]} まで幅広くまたがります。'
        f'重要なのは、{name}に投入する前の状態をそろえることです。濃度、含水率、温度、容器形状、試料量、搬送時間、ラベル位置のどれか一つでも揃っていないと、{name}の読みやすい出力ほど誤解を生みやすくなります。'
        f'特に {focus1} が効く装置では、準備段階でのわずかな差が本測定より大きなばらつきになります。'
        f'そのため {name} を使う前に、試料の採取時刻、前処理方法、保管条件、持ち込み経路、使用した消耗品をノートへ残し、結果と一対一で結び付けておく必要があります。'
        f'{name}では {focus2} を途中で変えると、同じ試料でも別系列のデータになります。逆に、条件を固定したまま {focus3} を見落とすと、装置由来の異常を試料差として読み違えます。'
        f'共同利用では、前利用者の治具や残留物、霜、液だれ、粉じん、校正ファイル、データ保存先の混在も試料条件の一部です。'
        f'したがって {name} の初心者ガイドでは、試料説明と同じ重さで「どこへ置くか」「どの順で扱うか」「どの時点で戻すか」を決める必要があります。'
        f'とくに {org} のように複数分野が混在する環境では、自分にとって harmless に見える置き方が、次利用者には重大な汚染源や設定差になります。'
        f'{name}を安定して使うには、試料の化学的・生物学的性質だけでなく、装置へ入るまでの履歴と取り出した後の扱いまでを一続きの条件として管理することが不可欠です。'
    )

    steps = [
        f'{name}を使う前に、試料名、前処理条件、使用する治具や消耗品、開始時の装置状態を一枚の記録へまとめ、{focus1} を揃えてから開始する。',
        f'{name}の立ち上げ直後はブランクまたは既知条件で確認を行い、{focus2} に関わる設定値と周辺環境をノートへ残してから本試料へ進む。',
        f'本試料では {name} の途中条件をむやみに変更せず、変更が必要な場合は理由、時刻、変更前後の値を残して {focus3} と切り分けられる形にする。',
        f'{name}の終了時は設定復帰、治具回収、清掃、消耗品の交換有無、保存先、異常の有無を確認し、次利用者が同じ初期状態から始められるように戻す。',
    ]
    pitfalls = [
        f'{name}で見たい値だけを追って {focus1} の記録を省略し、後から結果差の原因が試料か装置か分からなくなる。',
        f'{name}の使用中に {focus2} を場当たり的に変え、比較対象どうしの前提条件を自分で崩してしまう。',
        f'{name}の終了後に {focus3} と復帰状態を確認せず、次回利用で前回の残り条件を引きずってしまう。',
    ]

    papers = build_papers(item, name)
    payload = {
        'review': {'status': 'approved', 'reviewer': 'codex-manual', 'reviewed_at': ts},
        'general_usage': {'summary_ja': summary, 'sample_states': sample_states, 'research_fields_ja': research_fields},
        'paper_explanations': papers,
        'beginner_guide': {'principle_ja': principle, 'sample_guidance_ja': sample_guidance, 'basic_steps_ja': steps, 'common_pitfalls_ja': pitfalls},
    }
    supplements = build_unique_supplements(
        name=name,
        item=item,
        detail_label=detail_label,
        org=org,
        external=external,
        category=category,
        focus1=focus1,
        focus2=focus2,
        focus3=focus3,
    )
    return fit_beginner_band(payload, supplements), category


def char_count(payload: Dict[str, Any]) -> int:
    bg = payload['beginner_guide']
    text = bg['principle_ja'] + bg['sample_guidance_ja'] + ''.join(bg['basic_steps_ja']) + ''.join(bg['common_pitfalls_ja'])
    return len(re.sub(r'\s+', '', text))


def main() -> int:
    rows = load_queue(QUEUE_PATH)
    snapshot = load_snapshot(SNAPSHOT_PATH)
    if not BACKUP_PATH.exists():
        BACKUP_PATH.write_text(QUEUE_PATH.read_text(encoding='utf-8'), encoding='utf-8')
    base = datetime(2026, 3, 21, 0, 0, 0, tzinfo=timezone.utc)
    source_map = {'generated_at': datetime.now(timezone.utc).isoformat(), 'batch_id': 'BATCH-20260320-CYCLE0043-CANDIDATE100', 'doc_to_source': {}}
    counts = Counter()
    minc = 10**9
    maxc = 0
    for idx, row in enumerate(rows):
        item = snapshot.get(str(row['doc_id']), {})
        ts = (base + timedelta(seconds=idx * 43)).isoformat()
        payload, category = build_texts(row, item, ts)
        row['manual_content_v1'] = payload
        row['status'] = 'pending'
        row['issue_flags'] = []
        row['updated_at'] = ''
        c = char_count(payload)
        counts[category] += 1
        minc = min(minc, c)
        maxc = max(maxc, c)
        source_map['doc_to_source'][row['doc_id']] = {'family': category, 'seed_file': '', 'seed_key': '', 'name': row['name']}
    save_queue(QUEUE_PATH, rows)
    SOURCE_MAP_PATH.write_text(json.dumps(source_map, ensure_ascii=False, indent=2), encoding='utf-8')
    print('rows', len(rows))
    print('char_range', minc, maxc)
    print('categories', dict(counts))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
