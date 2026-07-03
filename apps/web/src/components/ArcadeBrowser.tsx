import { FormEvent, useCallback, useEffect, useMemo, useRef } from "react";
import { getArcadeDetail, listArcades, listCities, listCounties, listProvinces, lookupKnowledge } from "../api/client";
import { convertClientLocationToGcj02, geocodeAddressCandidatesToGcj02, geocodeAddressToGcj02, getArcadeGcjPoint } from "../lib/amapCoords";
import { buildAmapMarkerUri, buildAmapNavigationUri } from "../lib/amapUri";
import { warmupClientLocationCache } from "../lib/clientLocation";
import { useArcadeBrowserStore, type SearchFallbackCandidate } from "../stores/arcadeBrowserStore";
import type { ArcadeSummary, GeoPoint, KnowledgeArcadeCandidate } from "../types";
import { ArcadeDetailPanel, type ArcadeDetailViewModel } from "./arcade/ArcadeDetailPanel";
import { ArcadeSearchPanel } from "./arcade/ArcadeSearchPanel";
import {
  getArcadeFallbackRegionName,
  getArcadeRegionParts,
  getArcadeRegionZoom,
  getKnownRegionCenter,
  isArcadeDetail
} from "./arcade/arcadeBrowserUtils";
import type { MapAction } from "./map/MapActionBar";

const PAGE_SIZE = 20;

export function ArcadeBrowser() {
  const provinceCode = useArcadeBrowserStore((state) => state.provinceCode);
  const cityCode = useArcadeBrowserStore((state) => state.cityCode);
  const paged = useArcadeBrowserStore((state) => state.paged);
  const detail = useArcadeBrowserStore((state) => state.detail);
  const detailError = useArcadeBrowserStore((state) => state.detailError);
  const selectedSourceId = useArcadeBrowserStore((state) => state.selectedSourceId);
  const mapRuntime = useArcadeBrowserStore((state) => state.mapRuntime);
  const mapStatus = useArcadeBrowserStore((state) => state.mapStatus);
  const clientLocation = useArcadeBrowserStore((state) => state.clientLocation);
  const clientOriginGcj = useArcadeBrowserStore((state) => state.clientOriginGcj);
  const selectedRegionPoint = useArcadeBrowserStore((state) => state.selectedRegionPoint);
  const searchFallback = useArcadeBrowserStore((state) => state.searchFallback);
  const detailRequestIdRef = useRef(0);
  const setSelectedFallbackCandidate = useArcadeBrowserStore((state) => state.setSelectedFallbackCandidate);

  useEffect(() => {
    let cancelled = false;

    async function loadProvinces() {
      const rows = await listProvinces();
      if (!cancelled) {
        useArcadeBrowserStore.getState().setProvinces(rows);
      }
    }

    void loadProvinces();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!provinceCode) {
      const store = useArcadeBrowserStore.getState();
      store.setCities([]);
      store.setCounties([]);
      return;
    }

    let cancelled = false;
    async function loadCities() {
      const rows = await listCities(provinceCode);
      if (!cancelled) {
        useArcadeBrowserStore.getState().setCities(rows);
      }
    }

    void loadCities();
    return () => {
      cancelled = true;
    };
  }, [provinceCode]);

  useEffect(() => {
    if (!cityCode) {
      useArcadeBrowserStore.getState().setCounties([]);
      return;
    }

    let cancelled = false;
    async function loadCounties() {
      const rows = await listCounties(cityCode);
      if (!cancelled) {
        useArcadeBrowserStore.getState().setCounties(rows);
      }
    }

    void loadCounties();
    return () => {
      cancelled = true;
    };
  }, [cityCode]);

  useEffect(() => {
    let cancelled = false;

    async function refreshClientLocation() {
      const location = await warmupClientLocationCache();
      if (!cancelled && location) {
        useArcadeBrowserStore.getState().setClientLocation(location);
      }
    }

    void refreshClientLocation();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;

    async function resolveOrigin() {
      const store = useArcadeBrowserStore.getState();
      if (!clientLocation) {
        store.setClientOriginGcj(null);
        return;
      }
      const point = await convertClientLocationToGcj02(mapRuntime?.AMap, clientLocation);
      if (!cancelled) {
        store.setClientOriginGcj(point);
      }
    }

    void resolveOrigin();
    return () => {
      cancelled = true;
    };
  }, [clientLocation, mapRuntime]);

  const selectedSummary = useMemo(
    () => paged.items.find((item) => item.source_id === selectedSourceId) ?? null,
    [paged.items, selectedSourceId]
  );

  function buildMapLookupQuery(item: ArcadeSummary): string {
    const parts = [item.name, item.address, item.county_name, item.city_name, item.province_name]
      .map((value) => value?.trim())
      .filter(Boolean) as string[];
    return parts.join(" ");
  }

  function pickBestSearchMatch(items: ArcadeSummary[], shopName: string): ArcadeSummary | null {
    const keyword = shopName.trim().toLowerCase();
    if (!items.length) {
      return null;
    }
    if (!keyword) {
      return items[0] ?? null;
    }
    const exact = items.find((item) => item.name.trim().toLowerCase() === keyword);
    if (exact) {
      return exact;
    }
    const partial = items.find((item) => item.name.trim().toLowerCase().includes(keyword));
    return partial ?? items[0] ?? null;
  }

  function buildFallbackMessage(shopName: string, knowledgeHitCount: number, candidateCount: number): string {
    const trimmed = shopName.trim();
    const geocoded = candidateCount > 0;
    if (!trimmed) {
      return "这边暂时没有查到匹配的机厅结果，您可以换个机厅名称或补充城市后再试试。";
    }
    if (candidateCount > 1 && knowledgeHitCount > 0) {
      return `您好，这边暂时没有在数据库里检索到“${trimmed}”这家机厅，知识库里有相关提及。我先把同名高德结果列在下方，您可以点选查看位置，再决定是否前往高德。`;
    }
    if (candidateCount > 1) {
      return `您好，这边暂时没有在数据库里检索到“${trimmed}”这家机厅，不过我找到了多个同名高德结果，已经列在下方。您可以点选查看位置，再决定是否前往高德。`;
    }
    if (knowledgeHitCount > 0 && geocoded) {
      return `您好，这边暂时没有在数据库里检索到“${trimmed}”这家机厅，知识库里有相关提及，我先帮您把高德地图定位结果展示在右侧，您可以先核对一下位置。`;
    }
    if (knowledgeHitCount > 0) {
      return `您好，这边暂时没有在数据库里检索到“${trimmed}”这家机厅，不过知识库里有相关提及。当前还没拿到稳定地图坐标，建议您补充城市或更完整店名，我再继续帮您查。`;
    }
    if (geocoded) {
      return `您好，这边暂时没有在数据库和知识库里检索到“${trimmed}”这家机厅，不过我根据名称帮您做了高德地图检索，右侧先展示一个临时点位供您参考。`;
    }
    return `您好，这边暂时没有在数据库和知识库里检索到“${trimmed}”这家机厅，也还没有拿到可用地图点位。您可以补充城市、商场名或更完整店名，我再继续帮您查。`;
  }

  function knowledgeCandidateToFallbackCandidate(candidate: KnowledgeArcadeCandidate): SearchFallbackCandidate | null {
    const point = candidate.geo?.gcj02 ?? null;
    if (!point) {
      return null;
    }
    return {
      id: candidate.id,
      name: candidate.name,
      address: candidate.address || "",
      regionText: candidate.region_text || [candidate.province_name, candidate.city_name, candidate.county_name].filter(Boolean).join(" / "),
      level: candidate.source_type || "knowledge",
      point,
      source: "knowledge",
      transport: candidate.transport,
      sourceUri: candidate.source_uri || undefined
    };
  }

  async function resolveSearchFallback(shopName: string): Promise<void> {
    const trimmed = shopName.trim();
    const store = useArcadeBrowserStore.getState();
    if (!trimmed) {
      store.setSearchFallback(null);
      return;
    }

    let knowledgeHits: Awaited<ReturnType<typeof lookupKnowledge>>["hits"] = [];
    let knowledgeArcadeCandidates: Awaited<ReturnType<typeof lookupKnowledge>>["arcade_candidates"] = [];
    try {
      const knowledge = await lookupKnowledge(trimmed, 3);
      knowledgeHits = knowledge.hits ?? [];
      knowledgeArcadeCandidates = knowledge.arcade_candidates ?? [];
    } catch {
      knowledgeHits = [];
      knowledgeArcadeCandidates = [];
    }

    const structuredCandidates = knowledgeArcadeCandidates
      .map((item) => knowledgeCandidateToFallbackCandidate(item))
      .filter((item): item is SearchFallbackCandidate => Boolean(item));

    let candidates: SearchFallbackCandidate[] = [...structuredCandidates];
    if (mapRuntime?.AMap) {
      const geocodeCandidates = await geocodeAddressCandidatesToGcj02(mapRuntime.AMap, trimmed, clientLocation?.city || undefined);
      const mappedGeocodeCandidates = geocodeCandidates.map((item) => ({
        ...item,
        source: "geocode" as const
      }));
      const knownIds = new Set(candidates.map((item) => `${item.point.lng.toFixed(6)},${item.point.lat.toFixed(6)}`));
      for (const candidate of mappedGeocodeCandidates) {
        const key = `${candidate.point.lng.toFixed(6)},${candidate.point.lat.toFixed(6)}`;
        if (!knownIds.has(key)) {
          candidates.push(candidate);
          knownIds.add(key);
        }
      }
    }
    const point = candidates[0]?.point ?? null;

    store.setSearchFallback({
      query: trimmed,
      mapPoint: point,
      mapLabel: candidates[0]?.name || trimmed,
      message: buildFallbackMessage(trimmed, knowledgeHits.length, candidates.length),
      knowledgeHits,
      knowledgeArcadeCandidates,
      candidates,
      selectedCandidateId: candidates[0]?.id ?? null,
      page: 1,
      pageSize: 4
    });
  }

  const loadDetailForItem = useCallback(async (item: ArcadeSummary) => {
    const requestId = ++detailRequestIdRef.current;
    const store = useArcadeBrowserStore.getState();
    store.setDetailLoading(true);
    store.setDetailError("");
    try {
      const payload = await getArcadeDetail(item.source_id);
      if (requestId !== detailRequestIdRef.current) {
        return;
      }
      useArcadeBrowserStore.getState().setDetail(payload);
    } catch (err) {
      if (requestId !== detailRequestIdRef.current) {
        return;
      }
      const latestStore = useArcadeBrowserStore.getState();
      latestStore.setDetailError(err instanceof Error ? err.message : "加载机厅详情失败");
      latestStore.setDetail(null);
    } finally {
      if (requestId === detailRequestIdRef.current) {
        useArcadeBrowserStore.getState().setDetailLoading(false);
      }
    }
  }, []);

  const selectShop = useCallback(async (item: ArcadeSummary) => {
    useArcadeBrowserStore.getState().setSelectedSourceId(item.source_id);
    if (detail?.source_id === item.source_id && !detailError) {
      return;
    }
    await loadDetailForItem(item);
  }, [detail?.source_id, detailError, loadDetailForItem]);

  async function runSearch(page = 1): Promise<void> {
    const state = useArcadeBrowserStore.getState();
    state.setLoading(true);
    state.setError("");
    state.setSearchFallback(null);

    try {
      const legacyKeyword = [state.shopName, state.titleName].filter(Boolean).join(" ");
      const payload = await listArcades({
        keyword: legacyKeyword,
        shop_name: state.shopName,
        title_name: state.titleName || undefined,
        province_code: state.provinceCode || undefined,
        city_code: state.cityCode || undefined,
        county_code: state.countyCode || undefined,
        has_arcades: state.hasArcadesOnly ? true : undefined,
        sort_by: state.sortBy,
        sort_order: state.sortOrder,
        sort_title_name: state.sortBy === "title_quantity" ? state.titleName || undefined : undefined,
        origin_lng: state.sortBy === "distance" ? state.clientLocation?.lng : undefined,
        origin_lat: state.sortBy === "distance" ? state.clientLocation?.lat : undefined,
        origin_coord_system: state.sortBy === "distance" ? "wgs84" : undefined,
        page,
        page_size: PAGE_SIZE
      });
      const latestStore = useArcadeBrowserStore.getState();
      latestStore.setPaged(payload);

      const existing = payload.items.find((item) => item.source_id === latestStore.selectedSourceId) ?? null;
      if (!existing) {
        const bestMatch = pickBestSearchMatch(payload.items, state.shopName);
        if (bestMatch) {
          latestStore.setSelectedSourceId(bestMatch.source_id);
          latestStore.setMapStatus("idle");
          await loadDetailForItem(bestMatch);
          return;
        }
        detailRequestIdRef.current += 1;
        latestStore.setSelectedSourceId(null);
        latestStore.setDetail(null);
        latestStore.setDetailError("");
        latestStore.setDetailLoading(false);
        latestStore.setSelectedRegionPoint(null);
        latestStore.setMapStatus("idle");
        await resolveSearchFallback(state.shopName);
        return;
      }
      latestStore.setSelectedSourceId(existing.source_id);
      latestStore.setSearchFallback(null);
      if (latestStore.detail?.source_id !== existing.source_id || latestStore.detailError) {
        await loadDetailForItem(existing);
      }
    } catch (err) {
      useArcadeBrowserStore.getState().setError(err instanceof Error ? err.message : "检索机厅失败");
    } finally {
      useArcadeBrowserStore.getState().setLoading(false);
    }
  }

  useEffect(() => {
    void runSearch(1);
  }, []);

  async function onSubmit(event: FormEvent): Promise<void> {
    event.preventDefault();
    await runSearch(1);
  }

  const selectedArcade = detail?.source_id === selectedSourceId ? detail : selectedSummary;
  const selectedDetail = isArcadeDetail(selectedArcade) ? selectedArcade : null;
  const selectedCatalogPoint = getArcadeGcjPoint(selectedArcade);
  const selectedKnownRegionCenter = useMemo(() => getKnownRegionCenter(selectedArcade), [selectedArcade]);
  const selectedRegionParts = useMemo(() => getArcadeRegionParts(selectedArcade), [selectedArcade]);
  const selectedRegionQuery = selectedRegionParts.join("");
  const selectedRegionLabel = selectedRegionParts.join(" / ");
  const selectedFallbackRegionName = useMemo(() => getArcadeFallbackRegionName(selectedArcade), [selectedArcade]);

  useEffect(() => {
    let cancelled = false;

    async function resolveSelectedRegionPoint() {
      useArcadeBrowserStore.getState().setSelectedRegionPoint(null);
      if (selectedCatalogPoint || !selectedArcade || !mapRuntime?.AMap) {
        return;
      }
      const point = await geocodeAddressToGcj02(
        mapRuntime.AMap,
        buildMapLookupQuery(selectedArcade),
        selectedArcade.city_name
      );
      if (!cancelled && point) {
        useArcadeBrowserStore.getState().setSelectedRegionPoint({
          sourceId: selectedArcade.source_id,
          query: buildMapLookupQuery(selectedArcade),
          label: selectedArcade.name,
          point
        });
      }
    }

    void resolveSelectedRegionPoint();
    return () => {
      cancelled = true;
    };
  }, [
    mapRuntime,
    selectedArcade,
    selectedArcade?.city_name,
    selectedCatalogPoint,
    selectedRegionLabel,
    selectedRegionQuery
  ]);

  let selectedRegionCenterPoint: GeoPoint | null = null;
  if (
    selectedRegionPoint
    && selectedRegionPoint.sourceId === selectedArcade?.source_id
    && selectedRegionPoint.query === buildMapLookupQuery(selectedArcade)
  ) {
    selectedRegionCenterPoint = selectedRegionPoint.point;
  }

  const selectedPoint = selectedCatalogPoint;
  const fallbackMapPoint = searchFallback?.mapPoint ?? null;
  const mapCenter = selectedPoint ?? selectedRegionCenterPoint ?? fallbackMapPoint ?? selectedKnownRegionCenter;
  const mapZoom = selectedPoint || fallbackMapPoint ? 15 : getArcadeRegionZoom(selectedArcade);
  const handleMarkerSelect = useCallback((item: ArcadeSummary) => {
    void selectShop(item);
  }, [selectShop]);

  const pageHint = useMemo(() => {
    if (paged.total <= 0) {
      return "暂无结果";
    }
    const start = (paged.page - 1) * paged.page_size + 1;
    const end = Math.min(paged.total, paged.page * paged.page_size);
    return `${start}-${end} / ${paged.total}`;
  }, [paged]);

  const actions = useMemo<MapAction[]>(() => {
    if (!selectedArcade && fallbackMapPoint && searchFallback) {
      return [
        {
          key: "fallback-view",
          label: "查看当前候选",
          href: buildAmapMarkerUri({
            point: fallbackMapPoint,
            name: searchFallback.mapLabel
          }),
          emphasis: "secondary"
        },
        {
          key: "fallback-navigate",
          label: "前往高德",
          href: buildAmapNavigationUri({
            destination: fallbackMapPoint,
            destinationName: searchFallback.mapLabel,
            origin: clientOriginGcj,
            originName: clientLocation?.region_text || clientLocation?.formatted_address || "我的位置",
            mode: "walk"
          }),
          emphasis: "primary"
        }
      ];
    }
    if (!selectedPoint || !selectedArcade) {
      return [];
    }

    const markerHref = buildAmapMarkerUri({
      point: selectedPoint,
      name: selectedArcade.name
    });
    const navHref = buildAmapNavigationUri({
      destination: selectedPoint,
      destinationName: selectedArcade.name,
      origin: clientOriginGcj,
      originName: clientLocation?.region_text || clientLocation?.formatted_address || "我的位置",
      mode: "walk"
    });

    return [
      {
        key: "view",
        label: "在高德查看",
        href: markerHref,
        emphasis: "secondary"
      },
      {
        key: "navigate",
        label: "高德导航",
        href: navHref,
        emphasis: "primary"
      }
    ];
  }, [clientLocation, clientOriginGcj, fallbackMapPoint, searchFallback, selectedArcade, selectedPoint]);

  const mapStatusText = useMemo(() => {
    if (!selectedArcade && searchFallback?.message) {
      return searchFallback.message;
    }
    if (!selectedArcade) {
      return "选择一个机厅后加载地图";
    }
    if (mapStatus.state === "disabled") {
      return mapStatus.message || "未配置高德地图 Web JS Key；已保留列表和高德导航。";
    }
    if (mapStatus.state === "error") {
      return mapStatus.message || "地图加载失败；已保留列表和高德导航。";
    }
    if (mapStatus.state === "loading") {
      return "地图加载中...";
    }
    if (!selectedPoint && (mapCenter || selectedRegionLabel)) {
      return `该机厅暂无精确定位，地图已停在 ${selectedRegionPoint?.label || selectedRegionLabel}`;
    }
    if (!selectedPoint) {
      return "该机厅暂时没有可用地图定位";
    }
    return "";
  }, [mapCenter, mapStatus, searchFallback?.message, selectedArcade, selectedPoint, selectedRegionLabel, selectedRegionPoint?.label]);

  const detailView = useMemo<ArcadeDetailViewModel>(() => ({
    mapCenter,
    mapZoom,
    fallbackRegionName: selectedFallbackRegionName,
    selectedPoint,
    selectedRegionLabel,
    selectedRegionPoint,
    mapStatusText,
    actions,
    searchFallback
  }), [
    actions,
    mapCenter,
    mapStatusText,
    mapZoom,
    searchFallback,
    selectedFallbackRegionName,
    selectedPoint,
    selectedRegionLabel,
    selectedRegionPoint
  ]);

  return (
    <div className="browser-shell">
      <header className="browser-hero">
        <h2>机厅检索</h2>
        <p>筛选机厅、在地图上看点位，并直接跳转到高德查看或导航。</p>
      </header>

      <main className="browser-layout">
        <ArcadeSearchPanel
          pageHint={pageHint}
          onSubmit={onSubmit}
          onSelectShop={(item) => void selectShop(item)}
          onSearchPage={(page) => void runSearch(page)}
          onSelectFallbackCandidate={setSelectedFallbackCandidate}
        />
        <ArcadeDetailPanel
          selectedArcade={selectedArcade}
          selectedDetail={selectedDetail}
          view={detailView}
          onMarkerSelect={handleMarkerSelect}
        />
      </main>
    </div>
  );
}
