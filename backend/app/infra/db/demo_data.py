"""Deterministic synthetic arcade dataset used by the keyless demo runtime."""

from __future__ import annotations

from typing import Any


_REGIONS = (
    ("上海市", "310000000000", "上海市", "310100000000", "浦东新区", "310115000000", 121.5444, 31.2215),
    ("北京市", "110000000000", "北京市", "110100000000", "朝阳区", "110105000000", 116.4431, 39.9215),
    ("广东省", "440000000000", "广州市", "440100000000", "天河区", "440106000000", 113.3620, 23.1246),
    ("四川省", "510000000000", "成都市", "510100000000", "锦江区", "510104000000", 104.0830, 30.6570),
    ("浙江省", "330000000000", "杭州市", "330100000000", "西湖区", "330106000000", 120.1302, 30.2593),
    ("江苏省", "320000000000", "南京市", "320100000000", "玄武区", "320102000000", 118.7977, 32.0603),
    ("湖北省", "420000000000", "武汉市", "420100000000", "洪山区", "420111000000", 114.3430, 30.5000),
    ("陕西省", "610000000000", "西安市", "610100000000", "雁塔区", "610113000000", 108.9480, 34.2220),
    ("重庆市", "500000000000", "重庆市", "500100000000", "渝中区", "500103000000", 106.5740, 29.5530),
    ("福建省", "350000000000", "厦门市", "350200000000", "思明区", "350203000000", 118.0894, 24.4798),
)
_NAMES = ("星际游乐城", "音律空间", "像素工场", "节拍站", "街机研究所", "电玩城")
_TITLES = ("maimai", "CHUNITHM", "SDVX", "IIDX", "太鼓达人", "舞立方")


def build_demo_arcades(count: int = 60) -> list[dict[str, Any]]:
    """Build stable, nationwide-looking records without network or disk access."""
    rows: list[dict[str, Any]] = []
    for index in range(count):
        province, pcode, city, ccode, county, county_code, lng, lat = _REGIONS[index % len(_REGIONS)]
        local_index = index // len(_REGIONS) + 1
        source_id = 900001 + index
        titles = [
            {"title_name": _TITLES[index % len(_TITLES)], "quantity": index % 4 + 1},
            {"title_name": _TITLES[(index + 2) % len(_TITLES)], "quantity": index % 2 + 1},
        ]
        rows.append({
            "source": "arcadegent-demo",
            "source_id": source_id,
            "source_url": f"https://demo.arcadegent.local/arcades/{source_id}",
            "name": f"{_NAMES[index % len(_NAMES)]}·{county}{local_index}店",
            "address": f"{province}{city}{county}演示路 {18 + index} 号",
            "transport": f"地铁演示线 {local_index} 号口步行约 {3 + index % 8} 分钟",
            "comment": "合成演示数据，不代表真实门店。",
            "province_code": pcode, "province_name": province,
            "city_code": ccode, "city_name": city,
            "county_code": county_code, "county_name": county,
            "updated_at": f"2026-07-{(index % 12) + 1:02d}T08:00:00Z",
            "longitude_gcj02": round(lng + (local_index - 3) * 0.006, 6),
            "latitude_gcj02": round(lat + (local_index - 3) * 0.004, 6),
            "arcades": titles,
        })
    return rows
