from __future__ import annotations

import hashlib
import html
import re
from datetime import datetime

PREFECTURES = [
    "北海道",
    "青森県",
    "岩手県",
    "宮城県",
    "秋田県",
    "山形県",
    "福島県",
    "茨城県",
    "栃木県",
    "群馬県",
    "埼玉県",
    "千葉県",
    "東京都",
    "神奈川県",
    "新潟県",
    "富山県",
    "石川県",
    "福井県",
    "山梨県",
    "長野県",
    "岐阜県",
    "静岡県",
    "愛知県",
    "三重県",
    "滋賀県",
    "京都府",
    "大阪府",
    "兵庫県",
    "奈良県",
    "和歌山県",
    "鳥取県",
    "島根県",
    "岡山県",
    "広島県",
    "山口県",
    "徳島県",
    "香川県",
    "愛媛県",
    "高知県",
    "福岡県",
    "佐賀県",
    "長崎県",
    "熊本県",
    "大分県",
    "宮崎県",
    "鹿児島県",
    "沖縄県",
]

REGION_MAP = {
    "北海道": "北海道",
    "青森県": "東北",
    "岩手県": "東北",
    "宮城県": "東北",
    "秋田県": "東北",
    "山形県": "東北",
    "福島県": "東北",
    "茨城県": "関東",
    "栃木県": "関東",
    "群馬県": "関東",
    "埼玉県": "関東",
    "千葉県": "関東",
    "東京都": "関東",
    "神奈川県": "関東",
    "新潟県": "中部",
    "富山県": "中部",
    "石川県": "中部",
    "福井県": "中部",
    "山梨県": "中部",
    "長野県": "中部",
    "岐阜県": "中部",
    "静岡県": "中部",
    "愛知県": "中部",
    "三重県": "中部",
    "滋賀県": "関西",
    "京都府": "関西",
    "大阪府": "関西",
    "兵庫県": "関西",
    "奈良県": "関西",
    "和歌山県": "関西",
    "鳥取県": "中国",
    "島根県": "中国",
    "岡山県": "中国",
    "広島県": "中国",
    "山口県": "中国",
    "徳島県": "四国",
    "香川県": "四国",
    "愛媛県": "四国",
    "高知県": "四国",
    "福岡県": "九州",
    "佐賀県": "九州",
    "長崎県": "九州",
    "熊本県": "九州",
    "大分県": "九州",
    "宮崎県": "九州",
    "鹿児島県": "九州",
    "沖縄県": "沖縄",
}

DATE_PATTERN = re.compile(r"(\d{4})[./年-](\d{1,2})[./月-](\d{1,2})")
TOKEN_PATTERN = re.compile(r"[A-Za-z0-9]+|[ぁ-んァ-ン一-龥々ー]+")
KEYWORD_NORMALIZE_PATTERN = re.compile(r"[^A-Za-z0-9ぁ-んァ-ン一-龥々ー]+")

NORMALIZED_KEYWORDS = {
    "xrd": [
        "xrd",
        "x線回折",
        "x線回折装置",
        "x線回折測定",
        "x-ray diffraction",
        "xray diffraction",
        "x-ray diffractometer",
        "xray diffractometer",
    ],
    "sem": ["sem", "走査型電子顕微鏡", "走査電子顕微鏡"],
    "tem": ["tem", "透過型電子顕微鏡", "透過電子顕微鏡"],
    "xps": ["xps", "x線光電子分光", "x線光電子分光法"],
    "nmr": ["nmr", "核磁気共鳴", "核磁気共鳴装置"],
    "ftir": ["ftir", "フーリエ変換赤外分光", "フーリエ変換赤外分光法"],
    "afm": ["afm", "原子間力顕微鏡"],
    "lcms": ["lcms", "液体クロマトグラフ質量分析", "液クロ質量分析"],
    "gcms": ["gcms", "ガスクロマトグラフ質量分析", "ガスクロ質量分析"],
}


def clean_text(value: str) -> str:
    if not value:
        return ""
    text = html.unescape(value)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def normalize_keyword_text(value: str) -> str:
    text = clean_text(value).lower()
    if not text:
        return ""
    return KEYWORD_NORMALIZE_PATTERN.sub("", text)


def normalize_label(value: str) -> str:
    text = clean_text(value)
    for char in (":", "：", " ", "　"):
        text = text.replace(char, "")
    return text


def guess_prefecture(text: str) -> str:
    if not text:
        return ""
    for pref in PREFECTURES:
        if pref in text:
            return pref
    return ""


def classify_external_use(value: str) -> str:
    text = value or ""
    if "不可" in text or "利用不可" in text:
        return "不可"
    if "要相談" in text or "お問い合わせ" in text or "問合せ" in text:
        return "要相談"
    if "可" in text or "可能" in text or "利用可" in text:
        return "可"
    return "不明"


def classify_fee_band(value: str) -> str:
    text = value or ""
    if "無料" in text:
        return "無料"
    if "有料" in text or "円" in text or "¥" in text or "￥" in text:
        return "有料"
    return "不明"


def parse_date(value: str) -> str:
    if not value:
        return ""
    match = DATE_PATTERN.search(value)
    if not match:
        return ""
    year, month, day = (int(match.group(1)), int(match.group(2)), int(match.group(3)))
    try:
        return datetime(year, month, day).date().isoformat()
    except ValueError:
        return ""


def compute_dedupe_key(*parts: str) -> str:
    base = "|".join([clean_text(part) for part in parts if part])
    if not base:
        return ""
    return hashlib.sha1(base.encode("utf-8")).hexdigest()


def resolve_region(prefecture: str) -> str:
    if not prefecture:
        return ""
    return REGION_MAP.get(prefecture, "")


def build_search_tokens(*values: str) -> list[str]:
    tokens: list[str] = []
    seen = set()

    def add_token(value: str) -> None:
        if not value or value in seen:
            return
        seen.add(value)
        tokens.append(value)

    for value in values:
        text = clean_text(value).lower()
        if not text:
            continue
        for match in TOKEN_PATTERN.findall(text):
            add_token(match)
            if re.search(r"[ぁ-んァ-ン一-龥々ー]", match):
                compact = match.replace(" ", "")
                for size in (2, 3):
                    for index in range(0, len(compact) - size + 1):
                        add_token(compact[index : index + size])
        if len(tokens) > 80:
            break

    return tokens


def build_search_aliases(*values: str) -> list[str]:
    base_text = " ".join([value for value in values if value])
    base = normalize_keyword_text(base_text)
    if not base:
        return []

    tokens = set()
    for value in values:
        text = clean_text(value).lower()
        if not text:
            continue
        for match in TOKEN_PATTERN.findall(text):
            normalized = normalize_keyword_text(match)
            if normalized:
                tokens.add(normalized)

    aliases: list[str] = []
    seen = set()
    for key, terms in NORMALIZED_KEYWORDS.items():
        candidates = [key, *terms]
        for term in candidates:
            normalized = normalize_keyword_text(term)
            if not normalized or len(normalized) <= 1:
                continue
            if len(normalized) <= 3:
                if normalized not in tokens:
                    continue
            elif normalized not in base:
                continue
            if key not in seen:
                aliases.append(key)
                seen.add(key)
            break
    return aliases
