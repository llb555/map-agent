"""Region catalog service with AMap-backed nationwide administrative divisions."""

from __future__ import annotations

import json
from dataclasses import dataclass
from threading import Lock
from typing import Callable
from urllib import parse, request, error


def _non_empty_str(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text or None


def _normalize_region_item(item: object) -> dict[str, str] | None:
    if not isinstance(item, dict):
        return None
    code = _non_empty_str(item.get("code"))
    name = _non_empty_str(item.get("name"))
    if not code or not name:
        return None
    return {"code": code, "name": name}


def _normalize_adcode(value: object) -> str | None:
    code = _non_empty_str(value)
    if not code:
        return None
    digits = "".join(ch for ch in code if ch.isdigit())
    if len(digits) == 12:
        return digits
    if len(digits) == 6:
        return digits + "000000"
    return digits or None


@dataclass(frozen=True)
class AMapRegionCatalogConfig:
    api_key: str
    base_url: str
    timeout_seconds: float


class AMapRegionCatalog:
    """Fetch and cache province/city/county choices from AMap district API."""

    def __init__(self, config: AMapRegionCatalogConfig | None = None) -> None:
        self._config = config
        self._lock = Lock()
        self._provinces: list[dict[str, str]] | None = None
        self._cities_by_province: dict[str, list[dict[str, str]]] = {}
        self._counties_by_city: dict[str, list[dict[str, str]]] = {}

    def enabled(self) -> bool:
        return bool(self._config and self._config.api_key.strip())

    def list_provinces(self) -> list[dict[str, str]]:
        self._ensure_loaded()
        with self._lock:
            return list(self._provinces or [])

    def list_cities(self, province_code: str) -> list[dict[str, str]]:
        self._ensure_loaded()
        with self._lock:
            return list(self._cities_by_province.get(province_code, []))

    def list_counties(self, city_code: str) -> list[dict[str, str]]:
        self._ensure_loaded()
        with self._lock:
            return list(self._counties_by_city.get(city_code, []))

    def _ensure_loaded(self) -> None:
        with self._lock:
            if self._provinces is not None:
                return
        payload = self._fetch_country_tree()
        provinces, cities_by_province, counties_by_city = self._parse_country_tree(payload)
        with self._lock:
            self._provinces = provinces
            self._cities_by_province = cities_by_province
            self._counties_by_city = counties_by_city

    def _fetch_country_tree(self) -> dict[str, object]:
        if not self._config or not self._config.api_key.strip():
            raise RuntimeError("amap_region_catalog_not_configured")
        query = parse.urlencode(
            {
                "key": self._config.api_key,
                "keywords": "中国",
                "subdistrict": 3,
                "extensions": "base",
            }
        )
        url = self._config.base_url.rstrip("/") + "/v3/config/district?" + query
        req = request.Request(url, method="GET")
        try:
            with request.urlopen(req, timeout=self._config.timeout_seconds) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
        except (error.URLError, error.HTTPError, TimeoutError) as exc:
            raise RuntimeError(f"amap_region_catalog_request_failed:{exc}") from exc

        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise RuntimeError("amap_region_catalog_invalid_json") from exc
        if not isinstance(payload, dict) or str(payload.get("status") or "") != "1":
            infocode = _non_empty_str(payload.get("infocode") if isinstance(payload, dict) else None)
            info = _non_empty_str(payload.get("info") if isinstance(payload, dict) else None)
            raise RuntimeError(f"amap_region_catalog_failed:{infocode or 'unknown'}:{info or 'unknown'}")
        return payload

    def _parse_country_tree(
        self,
        payload: dict[str, object],
    ) -> tuple[list[dict[str, str]], dict[str, list[dict[str, str]]], dict[str, list[dict[str, str]]]]:
        districts = payload.get("districts")
        if not isinstance(districts, list) or not districts:
            raise RuntimeError("amap_region_catalog_missing_districts")
        root = districts[0]
        if not isinstance(root, dict):
            raise RuntimeError("amap_region_catalog_invalid_root")

        provinces: list[dict[str, str]] = []
        cities_by_province: dict[str, list[dict[str, str]]] = {}
        counties_by_city: dict[str, list[dict[str, str]]] = {}

        for province_raw in root.get("districts") or []:
            if not isinstance(province_raw, dict):
                continue
            province = _normalize_region_item(
                {
                    "code": _normalize_adcode(province_raw.get("adcode")),
                    "name": province_raw.get("name"),
                }
            )
            if province is None:
                continue
            provinces.append(province)

            city_rows: list[dict[str, str]] = []
            for city_raw in province_raw.get("districts") or []:
                if not isinstance(city_raw, dict):
                    continue
                city = _normalize_region_item(
                    {
                        "code": _normalize_adcode(city_raw.get("adcode")),
                        "name": city_raw.get("name"),
                    }
                )
                if city is None:
                    continue
                city_rows.append(city)

                county_rows: list[dict[str, str]] = []
                for county_raw in city_raw.get("districts") or []:
                    county = _normalize_region_item(
                        {
                            "code": _normalize_adcode(county_raw.get("adcode")) if isinstance(county_raw, dict) else None,
                            "name": county_raw.get("name") if isinstance(county_raw, dict) else None,
                        }
                    )
                    if county is None:
                        continue
                    county_rows.append(county)
                counties_by_city[city["code"]] = county_rows

            cities_by_province[province["code"]] = city_rows

        provinces.sort(key=lambda item: item["code"])
        for mapping in (cities_by_province, counties_by_city):
            for key, rows in list(mapping.items()):
                mapping[key] = sorted(rows, key=lambda item: item["code"])
        return provinces, cities_by_province, counties_by_city
