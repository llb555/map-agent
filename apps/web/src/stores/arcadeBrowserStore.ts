import { create } from "zustand";
import { loadCachedClientLocation } from "../lib/clientLocation";
import type { AmapRuntime } from "../components/map/AmapMapCanvas";
import type {
  ArcadeDetail,
  ArcadeSortBy,
  ArcadeSummary,
  GeoPoint,
  KnowledgeArcadeCandidate,
  KnowledgeLookupHit,
  PagedArcades,
  RegionItem,
  SortOrder
} from "../types";

export type ArcadeMapStatus = {
  state: "idle" | "loading" | "ready" | "disabled" | "error";
  message: string;
};

export type SelectedRegionPoint = {
  sourceId: number;
  query: string;
  label: string;
  point: GeoPoint;
};

export type SearchFallbackState = {
  query: string;
  mapPoint: GeoPoint | null;
  mapLabel: string;
  message: string;
  knowledgeHits: KnowledgeLookupHit[];
  knowledgeArcadeCandidates: KnowledgeArcadeCandidate[];
  candidates: SearchFallbackCandidate[];
  selectedCandidateId: string | null;
  page: number;
  pageSize: number;
};

export type SearchFallbackCandidate = {
  id: string;
  name: string;
  address: string;
  regionText: string;
  level?: string | null;
  point: GeoPoint;
  source: "knowledge" | "geocode";
  transport?: string | null;
  sourceUri?: string | null;
};

export const EMPTY_PAGED_ARCADES: PagedArcades = {
  items: [],
  page: 1,
  page_size: 20,
  total: 0,
  total_pages: 0
};

type ArcadeBrowserStore = {
  provinces: RegionItem[];
  cities: RegionItem[];
  counties: RegionItem[];
  shopName: string;
  titleName: string;
  provinceCode: string;
  cityCode: string;
  countyCode: string;
  hasArcadesOnly: boolean;
  sortBy: ArcadeSortBy;
  sortOrder: SortOrder;
  loading: boolean;
  error: string;
  detail: ArcadeDetail | null;
  detailLoading: boolean;
  detailError: string;
  selectedSourceId: number | null;
  paged: PagedArcades;
  mapRuntime: AmapRuntime | null;
  mapStatus: ArcadeMapStatus;
  clientOriginGcj: GeoPoint | null;
  clientLocation: ReturnType<typeof loadCachedClientLocation>;
  selectedRegionPoint: SelectedRegionPoint | null;
  searchFallback: SearchFallbackState | null;
  setProvinces: (provinces: RegionItem[]) => void;
  setCities: (cities: RegionItem[]) => void;
  setCounties: (counties: RegionItem[]) => void;
  setShopName: (shopName: string) => void;
  setTitleName: (titleName: string) => void;
  setProvinceCode: (provinceCode: string) => void;
  setCityCode: (cityCode: string) => void;
  setCountyCode: (countyCode: string) => void;
  setHasArcadesOnly: (hasArcadesOnly: boolean) => void;
  setSortBy: (sortBy: ArcadeSortBy) => void;
  setSortOrder: (sortOrder: SortOrder) => void;
  setLoading: (loading: boolean) => void;
  setError: (error: string) => void;
  setDetail: (detail: ArcadeDetail | null) => void;
  setDetailLoading: (detailLoading: boolean) => void;
  setDetailError: (detailError: string) => void;
  setSelectedSourceId: (selectedSourceId: number | null) => void;
  setPaged: (paged: PagedArcades) => void;
  setMapRuntime: (mapRuntime: AmapRuntime | null) => void;
  setMapStatus: (state: ArcadeMapStatus["state"], message?: string) => void;
  setClientOriginGcj: (clientOriginGcj: GeoPoint | null) => void;
  setClientLocation: (clientLocation: ReturnType<typeof loadCachedClientLocation>) => void;
  setSelectedRegionPoint: (selectedRegionPoint: SelectedRegionPoint | null) => void;
  setSearchFallback: (searchFallback: SearchFallbackState | null) => void;
  setSelectedFallbackCandidate: (candidateId: string) => void;
  setFallbackPage: (page: number) => void;
};

export const useArcadeBrowserStore = create<ArcadeBrowserStore>((set) => ({
  provinces: [],
  cities: [],
  counties: [],
  shopName: "",
  titleName: "",
  provinceCode: "",
  cityCode: "",
  countyCode: "",
  hasArcadesOnly: true,
  sortBy: "default",
  sortOrder: "desc",
  loading: false,
  error: "",
  detail: null,
  detailLoading: false,
  detailError: "",
  selectedSourceId: null,
  paged: EMPTY_PAGED_ARCADES,
  mapRuntime: null,
  mapStatus: { state: "idle", message: "" },
  clientOriginGcj: null,
  clientLocation: loadCachedClientLocation(),
  selectedRegionPoint: null,
  searchFallback: null,
  setProvinces: (provinces) => set({ provinces }),
  setCities: (cities) => set({ cities }),
  setCounties: (counties) => set({ counties }),
  setShopName: (shopName) => set({ shopName }),
  setTitleName: (titleName) => set({ titleName }),
  setProvinceCode: (provinceCode) => set({
    provinceCode,
    cityCode: "",
    countyCode: "",
    cities: [],
    counties: []
  }),
  setCityCode: (cityCode) => set({
    cityCode,
    countyCode: "",
    counties: []
  }),
  setCountyCode: (countyCode) => set({ countyCode }),
  setHasArcadesOnly: (hasArcadesOnly) => set({ hasArcadesOnly }),
  setSortBy: (sortBy) => set((state) => ({
    sortBy,
    sortOrder: sortBy === "distance" ? "asc" : state.sortOrder
  })),
  setSortOrder: (sortOrder) => set({ sortOrder }),
  setLoading: (loading) => set({ loading }),
  setError: (error) => set({ error }),
  setDetail: (detail) => set({ detail }),
  setDetailLoading: (detailLoading) => set({ detailLoading }),
  setDetailError: (detailError) => set({ detailError }),
  setSelectedSourceId: (selectedSourceId) => set({ selectedSourceId }),
  setPaged: (paged) => set({ paged }),
  setMapRuntime: (mapRuntime) => set({ mapRuntime }),
  setMapStatus: (state, message = "") => set({ mapStatus: { state, message } }),
  setClientOriginGcj: (clientOriginGcj) => set({ clientOriginGcj }),
  setClientLocation: (clientLocation) => set({ clientLocation }),
  setSelectedRegionPoint: (selectedRegionPoint) => set({ selectedRegionPoint }),
  setSearchFallback: (searchFallback) => set({ searchFallback }),
  setSelectedFallbackCandidate: (candidateId) =>
    set((state) => {
      if (!state.searchFallback) {
        return state;
      }
      const selectedCandidate = state.searchFallback.candidates.find((item) => item.id === candidateId) ?? null;
      return {
        searchFallback: {
          ...state.searchFallback,
          selectedCandidateId: selectedCandidate?.id ?? state.searchFallback.selectedCandidateId,
          mapPoint: selectedCandidate?.point ?? state.searchFallback.mapPoint,
          mapLabel: selectedCandidate?.name ?? state.searchFallback.mapLabel
        }
      };
    }),
  setFallbackPage: (page) =>
    set((state) => {
      if (!state.searchFallback) {
        return state;
      }
      const totalPages = Math.max(1, Math.ceil(state.searchFallback.candidates.length / state.searchFallback.pageSize));
      return {
        searchFallback: {
          ...state.searchFallback,
          page: Math.min(Math.max(page, 1), totalPages)
        }
      };
    })
}));
