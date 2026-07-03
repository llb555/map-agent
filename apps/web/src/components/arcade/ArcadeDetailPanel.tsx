import type { ArcadeDetail, ArcadeSummary, GeoPoint } from "../../types";
import { useArcadeBrowserStore, type SearchFallbackState, type SelectedRegionPoint } from "../../stores/arcadeBrowserStore";
import { AmapMapCanvas } from "../map/AmapMapCanvas";
import { AmapRouteOverlay } from "../map/AmapRouteOverlay";
import { AmapShopMarkers } from "../map/AmapShopMarkers";
import { MapActionBar, type MapAction } from "../map/MapActionBar";

export type ArcadeDetailViewModel = {
  mapCenter: GeoPoint | null;
  mapZoom: number;
  fallbackRegionName: string;
  selectedPoint: GeoPoint | null;
  selectedRegionLabel: string;
  selectedRegionPoint: SelectedRegionPoint | null;
  mapStatusText: string;
  actions: MapAction[];
  searchFallback: SearchFallbackState | null;
};

type ArcadeDetailPanelProps = {
  selectedArcade: ArcadeSummary | ArcadeDetail | null;
  selectedDetail: ArcadeDetail | null;
  view: ArcadeDetailViewModel;
  onMarkerSelect: (item: ArcadeSummary) => void;
};

export function ArcadeDetailPanel({
  selectedArcade,
  selectedDetail,
  view,
  onMarkerSelect
}: ArcadeDetailPanelProps) {
  const detailLoading = useArcadeBrowserStore((state) => state.detailLoading);
  const detailError = useArcadeBrowserStore((state) => state.detailError);
  const mapRuntime = useArcadeBrowserStore((state) => state.mapRuntime);
  const selectedSourceId = useArcadeBrowserStore((state) => state.selectedSourceId);
  const setMapRuntime = useArcadeBrowserStore((state) => state.setMapRuntime);
  const setMapStatus = useArcadeBrowserStore((state) => state.setMapStatus);
  const shouldLoadMap = Boolean(selectedArcade || view.searchFallback?.mapPoint);
  const selectedFallbackCandidate = view.searchFallback?.candidates.find(
    (item) => item.id === view.searchFallback?.selectedCandidateId
  ) ?? null;
  const regionLabel = [selectedArcade?.province_name, selectedArcade?.city_name, selectedArcade?.county_name]
    .filter(Boolean)
    .join(" / ");
  const locationStatusLabel = view.selectedPoint
    ? "精确定位"
    : view.searchFallback?.mapPoint
      ? "候选定位"
      : view.mapCenter || view.selectedRegionLabel
        ? "区域定位"
        : "等待定位";
  const positionHint = view.selectedPoint
    ? `地图坐标：${view.selectedPoint.lng.toFixed(6)}, ${view.selectedPoint.lat.toFixed(6)}`
    : selectedFallbackCandidate?.point
      ? `临时地图坐标：${selectedFallbackCandidate.point.lng.toFixed(6)}, ${selectedFallbackCandidate.point.lat.toFixed(6)}`
    : view.searchFallback?.mapPoint
      ? `临时地图坐标：${view.searchFallback.mapPoint.lng.toFixed(6)}, ${view.searchFallback.mapPoint.lat.toFixed(6)}`
      : view.mapCenter || view.selectedRegionLabel
      ? `该机厅暂时没有精确地图坐标，地图已停在 ${view.selectedRegionPoint?.label || view.selectedRegionLabel}`
      : "该机厅暂时没有可用地图坐标";

  return (
    <aside className="browser-card browser-detail">
      <div className="browser-detail-head">
        <div className="browser-detail-head-copy">
          <small>Map · Detail · Action</small>
          <strong>地图与详情</strong>
        </div>
        <span className={`browser-detail-status${view.selectedPoint ? " is-precise" : ""}`}>{locationStatusLabel}</span>
      </div>

      <div className="browser-map-panel">
        {shouldLoadMap ? (
          <>
            <AmapMapCanvas
              center={view.mapCenter}
              zoom={view.mapZoom}
              fallbackRegionName={view.fallbackRegionName}
              emptyMessage="等待地图就绪"
              onRuntimeChange={setMapRuntime}
              onStatusChange={setMapStatus}
            />
            <AmapShopMarkers
              runtime={mapRuntime}
              shop={selectedArcade}
              point={view.selectedPoint}
              fallbackLabel={selectedFallbackCandidate?.name || view.searchFallback?.mapLabel}
              selectedSourceId={selectedSourceId}
              onSelectShop={onMarkerSelect}
            />
            <AmapRouteOverlay runtime={mapRuntime} route={null} />
          </>
        ) : (
          <div className="amap-canvas-shell browser-map-placeholder" data-testid="arcade-map-placeholder">
            <div className="amap-empty-copy">选择一个机厅后加载地图</div>
          </div>
        )}
        {view.mapStatusText ? <div className="browser-map-state">{view.mapStatusText}</div> : null}
      </div>

      {shouldLoadMap ? (
        <div className="browser-map-meta">
          <span>{positionHint}</span>
          <span>{selectedArcade ? regionLabel || "区域信息待补充" : selectedFallbackCandidate?.regionText || "候选区域待补充"}</span>
        </div>
      ) : null}

      {detailLoading ? (
        <div className="browser-detail-skeleton" aria-hidden="true">
          <span />
          <span />
          <span />
        </div>
      ) : null}
      {!detailLoading && !selectedArcade && !view.searchFallback ? (
        <div className="browser-detail-empty">
          <strong>先从左侧选一个机厅</strong>
          <p>这里会同步显示地图、基础信息、机台概览和跳转动作。</p>
        </div>
      ) : null}
      {detailError ? <p className="browser-error">{detailError}</p> : null}
      {selectedArcade ? (
        <div className="browser-detail-content browser-detail-sheet">
          <div className="browser-detail-summary">
            <p className="browser-detail-kicker">机厅档案</p>
            <h3 data-testid="browser-detail-title">{selectedArcade.name}</h3>
            <p className="browser-detail-lead">{selectedArcade.address || "暂无地址"}</p>
            <div className="browser-detail-pills">
              {regionLabel ? <span>{regionLabel}</span> : null}
              <span>{selectedArcade.arcade_count} 个机种</span>
              <span>{view.selectedPoint ? "已落在门店点位" : "当前为近似地图位置"}</span>
            </div>
          </div>

          <div className="browser-detail-info-grid">
            <div className="browser-detail-info-card">
              <strong>到店说明</strong>
              <p>{selectedArcade.transport || "暂无交通信息，建议结合商场名或周边地标确认入口。"}</p>
            </div>
            <div className="browser-detail-info-card is-muted">
              <strong>地图备注</strong>
              <p className="browser-map-hint">{positionHint}</p>
            </div>
          </div>

          <div className="browser-detail-action-block">
            <div className="browser-detail-action-copy">
              <strong>地图动作</strong>
              <small>可直接在高德查看当前位置，或从当前位置发起导航。</small>
            </div>
            <MapActionBar actions={view.actions} />
          </div>

          {selectedDetail ? (
            <div className="browser-comment-card">
              <strong>补充备注</strong>
              <p className="browser-comment">{selectedDetail.comment || "当前没有额外备注信息。"}</p>
            </div>
          ) : null}
          {selectedDetail ? (
            <section className="browser-title-section">
              <div className="browser-title-section-head">
                <div>
                  <h4>机台信息</h4>
                  <small>{selectedDetail.arcades.length} 条记录，按机种与版本展示</small>
                </div>
                <span className="browser-title-section-pill">{selectedDetail.arcades.length} 条</span>
              </div>
              <ul className="browser-title-list">
                {selectedDetail.arcades.map((item, idx) => (
                  <li key={`${item.title_id}-${idx}`}>
                    <b>{item.title_name || "未知机种"}</b>
                    <span>数量：{item.quantity ?? "-"}</span>
                    <span>版本：{item.version || "-"}</span>
                  </li>
                ))}
              </ul>
            </section>
          ) : (
            <div className="browser-inline-state">正在加载详细机台信息...</div>
          )}
        </div>
      ) : null}
      {!selectedArcade && view.searchFallback ? (
        <div className="browser-detail-content browser-detail-sheet is-fallback">
          <p className="browser-detail-kicker">高德候选</p>
          <h3 data-testid="browser-fallback-title">{selectedFallbackCandidate?.name || view.searchFallback.mapLabel}</h3>
          <p className="browser-detail-lead">{selectedFallbackCandidate?.address || "地址待补充"}</p>
          <div className="browser-detail-pills">
            <span>{selectedFallbackCandidate?.regionText || "区域信息待补充"}</span>
            <span>{view.searchFallback.candidates.length} 个同名候选</span>
          </div>

          <div className="browser-detail-action-block">
            <div className="browser-detail-action-copy">
              <strong>地图动作</strong>
              <small>先核对候选位置，再决定是否前往高德查看或导航。</small>
            </div>
            <MapActionBar actions={view.actions} />
          </div>
        </div>
      ) : null}
    </aside>
  );
}
