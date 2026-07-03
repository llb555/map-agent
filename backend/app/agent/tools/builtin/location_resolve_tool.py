"""Builtin location resolver backed by the existing AMap geocoding service."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.protocol.messages import ArcadeGeoDto
from app.services.arcade_geo_resolver import ArcadeGeoResolver


def _compact(value: str | None) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text or None


def _join_unique(parts: list[str | None]) -> str | None:
    ordered: list[str] = []
    seen: set[str] = set()
    for part in parts:
        text = _compact(part)
        if not text or text in seen:
            continue
        ordered.append(text)
        seen.add(text)
    if not ordered:
        return None
    return " ".join(ordered)


@dataclass(frozen=True)
class ResolvedLocation:
    name: str
    lng: float
    lat: float
    coord_system: str = "gcj02"
    source: str = "geocode"
    precision: str = "approx"
    province_name: str | None = None
    city_name: str | None = None
    county_name: str | None = None

    def as_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "name": self.name,
            "lng": self.lng,
            "lat": self.lat,
            "coord_system": self.coord_system,
            "source": self.source,
            "precision": self.precision,
        }
        if self.province_name:
            payload["province_name"] = self.province_name
        if self.city_name:
            payload["city_name"] = self.city_name
        if self.county_name:
            payload["county_name"] = self.county_name
        return payload


class LocationResolveTool:
    """Resolve a named place into one GCJ-02 coordinate using the local AMap REST wrapper."""

    def __init__(self, arcade_geo_resolver: ArcadeGeoResolver) -> None:
        self._resolver = arcade_geo_resolver

    def resolve(
        self,
        *,
        query: str,
        province_name: str | None = None,
        city_name: str | None = None,
        county_name: str | None = None,
    ) -> list[dict[str, Any]]:
        normalized_query = _compact(query)
        if normalized_query is None:
            return []

        geo = self._resolver.geocode_one(
            {
                "name": normalized_query,
                "address": _join_unique([county_name, city_name, province_name]),
                "city_name": _compact(city_name),
            }
        )
        if not isinstance(geo, ArcadeGeoDto) or geo.gcj02 is None:
            return []

        return [
            ResolvedLocation(
                name=normalized_query,
                lng=geo.gcj02.lng,
                lat=geo.gcj02.lat,
                coord_system=geo.gcj02.coord_system,
                source=geo.gcj02.source,
                precision=geo.gcj02.precision,
                province_name=_compact(province_name),
                city_name=_compact(city_name),
                county_name=_compact(county_name),
            ).as_payload()
        ]
