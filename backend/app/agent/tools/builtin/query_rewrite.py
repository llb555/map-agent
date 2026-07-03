"""Lightweight, controlled query rewrite helpers for search and RAG tools."""

from __future__ import annotations

import re
from dataclasses import asdict
from dataclasses import dataclass


_NOISE_PATTERNS = [
    r"我想问一下",
    r"我想问",
    r"想问一下",
    r"想问",
    r"请问一下",
    r"请问",
    r"问一下",
    r"帮我找一下",
    r"帮我找",
    r"帮忙找一下",
    r"帮忙找",
    r"给我找一下",
    r"给我找",
    r"有没有",
    r"有吗",
    r"吗",
    r"哪里有",
    r"这边有没有",
    r"附近有没有",
    r"可以去",
    r"推荐一下",
]

_SPACE_RE = re.compile(r"\s+")
_PUNCT_RE = re.compile(r"[，。；！？,.!?/\\|]+")

_TITLE_ALIASES: list[tuple[str, tuple[str, ...]]] = [
    ("maimai", ("maimai", "舞萌", "舞萌dx", "maimai dx")),
    ("chunithm", ("chunithm", "中二", "中二节奏", "中二病", "chuni")),
    ("sdvx", ("sdvx", "sound voltex", "soundvoltex", "sv")),
    ("jubeat", ("jubeat", "jb", "优比特")),
    ("taiko", ("太鼓", "taiko", "太鼓达人")),
    ("ddr", ("ddr", "dance dance revolution")),
    ("iidx", ("iidx", "弐寺", "二寺", "beatmania iidx")),
    ("popn", ("popn", "pop'n", "popn music")),
    ("gitadora", ("gitadora", "gita dora", "鼓棍", "吉他鼓")),
    ("ongeki", ("ongeki", "音击", "音擊")),
    ("wacca", ("wacca",)),
    ("pump it up", ("pump it up", "piu")),
    ("djmax technika", ("djmax technika", "technika")),
    ("nostalgia", ("nostalgia", "诺斯塔利亚")),
    ("reflec beat", ("reflec beat", "rb")),
    ("crossbeats", ("crossbeats", "cb")),
    ("groove coaster", ("groove coaster", "gc", "音炫轨道")),
]

_MUNICIPALITIES = ("北京", "上海", "天津", "重庆")

_CITY_ALIASES: list[tuple[str, str]] = [
    ("魔都", "上海"),
    ("申城", "上海"),
    ("帝都", "北京"),
    ("京城", "北京"),
    ("羊城", "广州"),
    ("鹏城", "深圳"),
    ("蓉城", "成都"),
    ("江城", "武汉"),
    ("杭城", "杭州"),
    ("金陵", "南京"),
]

_COUNTY_ALIASES: list[tuple[str, str]] = [
    ("浦东", "浦东新区"),
    ("徐汇", "徐汇区"),
    ("闵行", "闵行区"),
    ("静安", "静安区"),
    ("黄浦", "黄浦区"),
    ("杨浦", "杨浦区"),
    ("虹口", "虹口区"),
    ("普陀", "普陀区"),
    ("长宁", "长宁区"),
    ("宝山", "宝山区"),
    ("松江", "松江区"),
    ("嘉定", "嘉定区"),
    ("青浦", "青浦区"),
    ("奉贤", "奉贤区"),
    ("南汇", "浦东新区"),
    ("朝阳", "朝阳区"),
    ("海淀", "海淀区"),
    ("东城", "东城区"),
    ("西城", "西城区"),
    ("丰台", "丰台区"),
    ("石景山", "石景山区"),
    ("天河", "天河区"),
    ("越秀", "越秀区"),
    ("海珠", "海珠区"),
    ("白云", "白云区"),
    ("番禺", "番禺区"),
    ("黄浦江", "黄浦区"),
]

_PLACE_ALIASES: list[tuple[str, str]] = [
    ("人广", "人民广场"),
    ("虹足", "虹口足球场"),
    ("五道口地铁", "五道口"),
    ("五角场万达", "五角场万达广场"),
    ("正佳", "正佳广场"),
    ("天环", "天环广场"),
    ("徐家汇地铁站", "徐家汇"),
    ("五角场地铁站", "五角场"),
    ("中关村地铁站", "中关村"),
    ("国贸地铁站", "国贸"),
    ("南锣", "南锣鼓巷"),
    ("大悦城", "西单大悦城"),
    ("陆家嘴中心", "陆家嘴中心"),
    ("大学城", "大学城"),
    ("北大", "北京大学"),
    ("清华", "清华大学"),
    ("复旦", "复旦大学"),
    ("同济", "同济大学"),
    ("上交", "上海交通大学"),
    ("浙大", "浙江大学"),
    ("武大", "武汉大学"),
    ("华科", "华中科技大学"),
    ("中大", "中山大学"),
]

_SHOP_SUFFIX_HINTS = (
    "店",
    "广场",
    "商场",
    "商城",
    "天地",
    "天街",
    "中心",
    "广场店",
    "乐园",
    "传奇",
)

_PLACE_SUFFIX_HINTS = (
    "广场",
    "地铁站",
    "车站",
    "火车站",
    "高铁站",
    "机场",
    "公园",
    "大学",
    "学院",
    "校区",
    "万达",
    "万达广场",
    "天地",
    "天街",
    "商场",
    "商城",
    "中心",
)

_EXPLICIT_SHOP_MARKERS = (
    "店",
    "乐园",
    "传奇",
)


@dataclass(frozen=True)
class RewrittenQuery:
    """Controlled query rewrite result."""

    raw: str
    normalized_text: str
    keyword: str | None = None
    title_name: str | None = None
    shop_name: str | None = None
    province_name: str | None = None
    city_name: str | None = None
    county_name: str | None = None
    place_query: str | None = None
    knowledge_query: str | None = None

    def to_memory_payload(self) -> dict[str, str]:
        payload = {key: value for key, value in asdict(self).items() if isinstance(value, str) and value.strip()}
        return payload


def rewrite_query(text: str) -> RewrittenQuery:
    raw = text.strip()
    normalized = _normalize_text(raw)
    if not normalized:
        return RewrittenQuery(raw=raw, normalized_text="")

    province_name, city_name, county_name = _extract_region_hints(raw)
    title_name = _extract_title_name(normalized)
    shop_name = _extract_shop_name(normalized, title_name=title_name)
    keyword = _build_keyword(
        normalized,
        title_name=title_name,
        shop_name=shop_name,
        province_name=province_name,
        city_name=city_name,
        county_name=county_name,
    )
    place_query = _build_place_query(
        normalized,
        shop_name=shop_name,
        province_name=province_name,
        city_name=city_name,
        county_name=county_name,
    )
    knowledge_query = _build_knowledge_query(normalized, title_name=title_name)
    return RewrittenQuery(
        raw=raw,
        normalized_text=normalized,
        keyword=keyword,
        title_name=title_name,
        shop_name=shop_name,
        province_name=province_name,
        city_name=city_name,
        county_name=county_name,
        place_query=place_query,
        knowledge_query=knowledge_query,
    )


def load_or_rewrite(runtime_context: dict[str, object], *, fallback_message: str | None = None) -> RewrittenQuery:
    stored = runtime_context.get("query_rewrite")
    if isinstance(stored, dict):
        try:
            return RewrittenQuery(**stored)
        except TypeError:
            pass
    return rewrite_query(fallback_message or "")


def _normalize_text(text: str) -> str:
    normalized = text.strip().lower()
    normalized = _PUNCT_RE.sub(" ", normalized)
    normalized = normalized.replace("的", " ")
    for pattern in _NOISE_PATTERNS:
        normalized = re.sub(pattern, " ", normalized)
    normalized = _normalize_place_aliases(normalized)
    normalized = normalized.replace("附近", " ")
    normalized = normalized.replace("最近", " ")
    normalized = normalized.replace("机厅", " ").replace("街机厅", " ")
    normalized = normalized.replace("街机店", " ").replace("店铺", " ")
    normalized = _SPACE_RE.sub(" ", normalized).strip()
    return normalized


def _extract_title_name(text: str) -> str | None:
    collapsed = re.sub(r"[\s_\-./]+", "", text)
    for canonical, aliases in _TITLE_ALIASES:
        for alias in aliases:
            alias_norm = re.sub(r"[\s_\-./]+", "", alias.lower())
            if alias_norm and alias_norm in collapsed:
                return canonical
    return None


def _extract_shop_name(text: str, *, title_name: str | None) -> str | None:
    if not text:
        return None
    if title_name and text.strip() == title_name:
        return None
    compact = text.strip()
    if len(compact) < 2:
        return None
    best_end = -1
    for hint in _SHOP_SUFFIX_HINTS:
        start = 0
        while True:
            idx = compact.find(hint, start)
            if idx < 0:
                break
            end = idx + len(hint)
            if end > best_end:
                best_end = end
            start = idx + 1
    if best_end > 0:
        candidate = compact[:best_end].strip()
        if len(candidate) >= 2 and not _looks_like_place_only(candidate):
            return candidate
    return None


def _build_keyword(
    text: str,
    *,
    title_name: str | None,
    shop_name: str | None,
    province_name: str | None,
    city_name: str | None,
    county_name: str | None,
) -> str | None:
    sanitized = text
    if title_name:
        sanitized = _strip_title_aliases(sanitized, title_name)
    sanitized = _strip_region_text(sanitized, province_name=province_name, city_name=city_name, county_name=county_name)
    parts = [part for part in _SPACE_RE.split(sanitized) if part]
    if not parts:
        return None

    filtered: list[str] = []
    for part in parts:
        if title_name and _matches_title_alias(part, title_name):
            continue
        if shop_name and part in shop_name:
            continue
        if part in {"附近", "最近", "有没有", "哪里", "推荐", "可去", "有", "吗"}:
            continue
        filtered.append(part)

    deduped = list(dict.fromkeys(filtered))
    if not deduped:
        return None
    return " ".join(deduped)


def _build_knowledge_query(text: str, *, title_name: str | None) -> str | None:
    if not text:
        return None
    sanitized = text
    if title_name:
        sanitized = _strip_title_aliases(sanitized, title_name)
    parts = [part for part in _SPACE_RE.split(sanitized) if part]
    if not parts:
        return None

    rewritten: list[str] = [title_name] if title_name else []
    rewritten.extend(parts)

    deduped = list(dict.fromkeys(rewritten))
    return " ".join(deduped) if deduped else None


def _build_place_query(
    text: str,
    *,
    shop_name: str | None,
    province_name: str | None,
    city_name: str | None,
    county_name: str | None,
) -> str | None:
    if not text:
        return None
    sanitized = _strip_region_text(
        text,
        province_name=province_name,
        city_name=city_name,
        county_name=county_name,
    )
    parts = [part for part in _SPACE_RE.split(sanitized) if part]
    if not parts:
        return None

    filtered: list[str] = []
    for part in parts:
        if shop_name and part in shop_name:
            continue
        if part in {"附近", "最近", "有没有", "哪里", "推荐", "可去", "有", "吗"}:
            continue
        if _extract_title_name(part):
            continue
        filtered.append(part)

    deduped = list(dict.fromkeys(filtered))
    if not deduped:
        return None
    return " ".join(deduped)


def _normalize_place_aliases(text: str) -> str:
    updated = text
    for alias, canonical in _PLACE_ALIASES:
        updated = re.sub(re.escape(alias.lower()), canonical.lower(), updated)
    return _SPACE_RE.sub(" ", updated).strip()


def _looks_like_place_only(text: str) -> bool:
    compact = text.strip()
    if not compact:
        return False
    if any(marker in compact for marker in _EXPLICIT_SHOP_MARKERS):
        return False
    return any(compact.endswith(suffix) for suffix in _PLACE_SUFFIX_HINTS)


def _matches_title_alias(part: str, canonical: str) -> bool:
    compact = re.sub(r"[\s_\-./]+", "", part.lower())
    for candidate, aliases in _TITLE_ALIASES:
        if candidate != canonical:
            continue
        if compact == candidate:
            return True
        for alias in aliases:
            alias_norm = re.sub(r"[\s_\-./]+", "", alias.lower())
            if compact == alias_norm:
                return True
    return False


def _strip_title_aliases(text: str, canonical: str) -> str:
    updated = text
    for candidate, aliases in _TITLE_ALIASES:
        if candidate != canonical:
            continue
        for alias in aliases:
            updated = re.sub(re.escape(alias.lower()), " ", updated)
    return _SPACE_RE.sub(" ", updated).strip()


def _extract_region_hints(text: str) -> tuple[str | None, str | None, str | None]:
    compact = re.sub(r"\s+", "", text)
    province_name: str | None = None
    city_name: str | None = None
    county_name: str | None = None

    for alias, canonical in _CITY_ALIASES:
        if alias in compact:
            if canonical in _MUNICIPALITIES:
                province_name = canonical
                city_name = canonical
            else:
                city_name = canonical
            break

    for name in _MUNICIPALITIES:
        if name in compact or f"{name}市" in compact:
            province_name = name
            city_name = name
            break

    if province_name is None:
        province_match = re.search(r"([一-龥]{2,12}(?:省|自治区|特别行政区))", compact)
        if province_match:
            province_name = province_match.group(1)

    city_matches = re.findall(r"([一-龥]{2,12}(?:市|州|地区|盟))", compact)
    if city_matches:
        for match in city_matches:
            if match.endswith("省"):
                continue
            if province_name and match == f"{province_name}市":
                continue
            city_name = match
            break
    elif province_name in {"北京", "上海", "天津", "重庆"}:
        city_name = province_name

    for alias, canonical in _COUNTY_ALIASES:
        if alias in compact:
            county_name = canonical
            break

    county_match = re.search(r"([一-龥]{1,12}?(?:区|县|旗))", compact)
    if county_match:
        county_name = county_name or county_match.group(1)
        if city_name:
            city_compact = city_name.removesuffix("市")
            if county_name.startswith(city_compact):
                trimmed = county_name[len(city_compact) :].strip()
                if trimmed:
                    county_name = trimmed

    return province_name, city_name, county_name


def _strip_region_text(
    text: str,
    *,
    province_name: str | None,
    city_name: str | None,
    county_name: str | None,
) -> str:
    updated = text
    for alias, canonical in _CITY_ALIASES:
        if canonical in {province_name, city_name}:
            updated = updated.replace(alias.lower(), " ")
    for alias, canonical in _COUNTY_ALIASES:
        if canonical == county_name:
            updated = updated.replace(alias.lower(), " ")
    for value in (province_name, city_name, county_name):
        if not isinstance(value, str) or not value.strip():
            continue
        candidate = value.strip().lower()
        updated = updated.replace(candidate, " ")
        if candidate in {"北京", "上海", "天津", "重庆"}:
            updated = updated.replace(f"{candidate}市", " ")
    return _SPACE_RE.sub(" ", updated).strip()
