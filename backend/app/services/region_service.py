"""Region service that combines nationwide catalog data with store fallback."""

from __future__ import annotations

from typing import Callable
from dataclasses import dataclass

from app.infra.db.repository import ArcadeRepository
from app.services.region_catalog import AMapRegionCatalog


@dataclass
class RegionService:
    store: ArcadeRepository
    catalog: AMapRegionCatalog

    def list_provinces(self) -> list[dict[str, str]]:
        return self._safe_catalog_call(self.catalog.list_provinces, fallback=self.store.list_provinces)

    def list_cities(self, province_code: str) -> list[dict[str, str]]:
        return self._safe_catalog_call(
            lambda: self.catalog.list_cities(province_code),
            fallback=lambda: self.store.list_cities(province_code),
        )

    def list_counties(self, city_code: str) -> list[dict[str, str]]:
        return self._safe_catalog_call(
            lambda: self.catalog.list_counties(city_code),
            fallback=lambda: self.store.list_counties(city_code),
        )

    @staticmethod
    def _safe_catalog_call(
        primary: Callable[[], list[dict[str, str]]],
        *,
        fallback: Callable[[], list[dict[str, str]]],
    ) -> list[dict[str, str]]:
        try:
            rows = primary()
        except Exception:
            return fallback()
        return rows or fallback()
