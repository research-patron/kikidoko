from __future__ import annotations

import hashlib
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

DATE_PATTERN = re.compile(r"(\d{4})[./年-](\d{1,2})[./月-](\d{1,2})")


def clean_text(value: str) -> str:
    if not value:
        return ""
    text = re.sub(r"\s+", " ", value)
    return text.strip()


def normalize_label(value: str) -> str:
    return clean_text(value).replace(":", "").replace("：", "")


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
