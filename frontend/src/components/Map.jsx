import React, { useEffect, useRef, useState, useCallback } from 'react';
import { MapContainer, TileLayer, Marker, Popup, useMap } from 'react-leaflet';
import L from 'leaflet';
import 'leaflet.heat';
import { Flame, Factory } from 'lucide-react';

// ── Constants ─────────────────────────────────────────────────────────────────
const INDIA_CENTER  = [22.5, 82.5];
const INDIA_ZOOM    = 5;
const INDIA_BOUNDS  = [[6.5, 68.0], [37.5, 97.5]];
const MARKER_MIN_ZOOM = 7; // markers only appear when zoomed in this far

// ── Tile layers ───────────────────────────────────────────────────────────────
// Heatmap basemap: CartoDB Positron NO-labels (ultra-clean, no competing text)
const HEATMAP_TILES   = 'https://{s}.basemaps.cartocdn.com/light_nolabels/{z}/{x}/{y}{r}.png';
// City/border labels only — placed above heatmap so cities are still readable
const LABEL_TILES     = 'https://{s}.basemaps.cartocdn.com/light_only_labels/{z}/{x}/{y}{r}.png';
// Satellite basemap
const SATELLITE_TILES = 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}';

// ── Marker helpers ────────────────────────────────────────────────────────────
const CATEGORY_MAP = {
  'Industrial Fire':         { cls: 'marker-industrial', emoji: '🏭', size: 16 },
  'Gas Flare':               { cls: 'marker-gasflare',   emoji: '🔥', size: 14 },
  'Mining Thermal Activity': { cls: 'marker-mining',     emoji: '⛏️', size: 13 },
  'Agricultural Burn':       { cls: 'marker-agri',       emoji: '🌾', size: 12 },
  'Wildfire':                { cls: 'marker-wildfire',   emoji: '🌲', size: 14 },
};
const getCategory = (c) => CATEGORY_MAP[c] || { cls: 'marker-unknown', emoji: '❓', size: 11 };

const getHotspotColor = (c) => ({
  'Industrial Fire': '#ef4444', 'Gas Flare': '#f97316',
  'Mining Thermal Activity': '#eab308', 'Agricultural Burn': '#22c55e',
  'Wildfire': '#b91c1c',
}[c] || '#94a3b8');

function makeDivIcon(classification, isSelected, isPersistent, frp) {
  const { cls, emoji, size } = getCategory(classification);
  const s = Math.min(size + Math.floor((frp || 0) / 60), size + 6);
  return new L.DivIcon({
    html: `<div class="fire-marker ${cls}${isPersistent ? ' persistent' : ''}${isSelected ? ' selected' : ''}"
               style="width:${s}px;height:${s}px;font-size:${Math.round(s * 0.65)}px;">${emoji}</div>`,
    className: '',
    iconSize: [s, s],
    iconAnchor: [s / 2, s / 2],
    popupAnchor: [0, -(s / 2 + 4)],
  });
}

const facilityDivIcon = new L.DivIcon({
  html: `<div class="facility-marker"></div>`,
  className: '',
  iconSize: [14, 14],
  iconAnchor: [7, 7],
  popupAnchor: [0, -10],
});

// ── Heatmap Layer ─────────────────────────────────────────────────────────────
function HeatmapLayer({ hotspots, isVisible }) {
  const map = useMap();
  const heatRef = useRef(null);

  useEffect(() => {
    if (!map) return;

    const points = hotspots.map(h => {
      const frp = h.properties.frp || 0;
      const intensity = frp < 5 ? 0.05 : Math.min(1.0, frp / 120);
      return [h.geometry.coordinates[1], h.geometry.coordinates[0], intensity];
    });

    if (!heatRef.current) {
      // First initialization — do NOT add to map yet, let visibility logic below handle that
      heatRef.current = L.heatLayer(points, {
        radius:     18,
        blur:       12,
        maxZoom:    12,
        max:        1.0,
        minOpacity: 0.25,
        gradient: {
          0.00: '#0d0221', 0.15: '#3d0b71', 0.32: '#8b1a8f',
          0.52: '#d64045', 0.70: '#f7821b', 0.87: '#fbbf24', 1.00: '#fefce8',
        },
      });
    } else {
      // CRITICAL: only call setLatLngs when the layer is attached to the map.
      // Calling it while detached triggers redraw() -> this._map._animating -> crash.
      if (map.hasLayer(heatRef.current)) {
        try {
          heatRef.current.setLatLngs(points);
        } catch (e) {
          console.warn('[HeatmapLayer] setLatLngs failed, recreating layer:', e);
          map.removeLayer(heatRef.current);
          heatRef.current = null;
          heatRef.current = L.heatLayer(points, {
            radius: 18, blur: 12, maxZoom: 12, max: 1.0, minOpacity: 0.25,
            gradient: { 0.00: '#0d0221', 0.15: '#3d0b71', 0.32: '#8b1a8f', 0.52: '#d64045', 0.70: '#f7821b', 0.87: '#fbbf24', 1.00: '#fefce8' },
          });
        }
      } else {
        // Layer not on map — recreate with fresh points so when it's added it's current
        heatRef.current = L.heatLayer(points, {
          radius: 18, blur: 12, maxZoom: 12, max: 1.0, minOpacity: 0.25,
          gradient: { 0.00: '#0d0221', 0.15: '#3d0b71', 0.32: '#8b1a8f', 0.52: '#d64045', 0.70: '#f7821b', 0.87: '#fbbf24', 1.00: '#fefce8' },
        });
      }
    }

    // Handle visibility by adding/removing from map directly
    if (isVisible) {
      if (!map.hasLayer(heatRef.current)) {
        heatRef.current.addTo(map);
      }
    } else {
      if (map.hasLayer(heatRef.current)) {
        map.removeLayer(heatRef.current);
      }
    }
  }, [map, hotspots, isVisible]);

  // Clean up layer fully if component unmounts entirely
  useEffect(() => {
    return () => {
      if (heatRef.current && map) {
        try { map.removeLayer(heatRef.current); } catch (_) {}
      }
    };
  }, [map]);

  return null;
}

// ViewResetController removed: map state is now fully preserved between mode switches.

// ── Zoom to India Button ──────────────────────────────────────────────────────
function ZoomResetButton() {
  const map = useMap();
  return (
    <button 
      onClick={() => map.fitBounds(INDIA_BOUNDS, { animate: true, duration: 0.8 })}
      className="absolute top-4 right-4 z-[1000] glass-panel px-3 py-2 rounded-lg text-xs font-semibold text-slate-200 hover:text-white hover:bg-slate-700/80 shadow-lg flex items-center gap-2 transition-all hover:scale-105"
      title="Reset view to full India"
    >
      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 8V4m0 0h4M4 4l5 5m11-1V4m0 0h-4m4 0l-5 5M4 16v4m0 0h4m-4 0l5-5m11 5l-5-5m5 5v-4m0 4h-4" /></svg>
      Zoom to India
    </button>
  );
}

// ── Auto-pan to selected hotspot ──────────────────────────────────────────────
function MapController({ center, selectedId }) {
  const map = useMap();
  useEffect(() => {
    if (center && selectedId) map.flyTo(center, 13, { duration: 1.5 });
    // We intentionally omit `center` from dependencies because passing it as an inline array 
    // from the parent causes the effect to re-run on every zoom tick, fighting the user.
    // Reacting only to `selectedId` is correct because we only want to fly when a NEW hotspot is selected.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedId, map]);
  return null;
}

// ── Zoom-aware marker visibility ──────────────────────────────────────────────
// Subscribes to zoom events and tells parent whether markers should show
function ZoomWatcher({ onZoomChange }) {
  const map = useMap();
  useEffect(() => {
    const handler = () => onZoomChange(map.getZoom());
    map.on('zoomend', handler);
    onZoomChange(map.getZoom()); // initial
    return () => map.off('zoomend', handler);
  }, [map, onZoomChange]);
  return null;
}

// ── Legend ────────────────────────────────────────────────────────────────────
function Legend({ mode }) {
  const cats = [
    { label: 'Industrial Fire',   emoji: '🏭', color: '#ef4444' },
    { label: 'Gas Flare',         emoji: '🔥', color: '#f97316' },
    { label: 'Mining Activity',   emoji: '⛏️', color: '#eab308' },
    { label: 'Agricultural Burn', emoji: '🌾', color: '#22c55e' },
    { label: 'Wildfire',          emoji: '🌲', color: '#b91c1c' },
    { label: 'Unclassified',      emoji: '❓', color: '#94a3b8' },
  ];
  return (
    <div className="absolute bottom-6 left-4 z-[1000] glass-panel rounded-xl px-4 py-3 shadow-2xl text-slate-200">
      <div className="text-[10px] font-bold uppercase tracking-wider text-slate-400 mb-2">
        {mode === 'heatmap' ? 'Thermal Intensity (FRP)' : 'Classification'}
      </div>
      {mode === 'heatmap' ? (
        <>
          <div className="h-3.5 w-40 rounded" style={{
            background: 'linear-gradient(to right, #0d0221,#3d0b71,#8b1a8f,#d64045,#f7821b,#fbbf24,#fefce8)',
          }} />
          <div className="flex justify-between text-[10px] text-slate-400 mt-1">
            <span>Low</span><span>High</span>
          </div>
          <div className="mt-2 text-[10px] text-slate-500">Zoom in (≥ {MARKER_MIN_ZOOM}) to see<br/>individual hotspot markers.</div>
        </>
      ) : (
        <div className="space-y-1.5">
          {cats.map(c => (
            <div key={c.label} className="flex items-center gap-2 text-xs">
              <span className="text-sm leading-none">{c.emoji}</span>
              <span className="w-2 h-2 rounded-full shrink-0"
                    style={{ backgroundColor: c.color, boxShadow: `0 0 5px ${c.color}` }} />
              <span>{c.label}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// Removed ModeToggle as it is now in App.jsx

// ── Main Map ──────────────────────────────────────────────────────────────────
export default function Map({ hotspots = [], facilities = [], selectedHotspot, setSelectedHotspot, mapMode = 'heatmap' }) {
  const [currentZoom, setCurrentZoom] = useState(INDIA_ZOOM);

  // Show markers: always in satellite mode; in heatmap mode only when zoomed in
  const showMarkers = mapMode === 'satellite' || currentZoom >= MARKER_MIN_ZOOM;

  return (
    <div className="h-full w-full bg-slate-900 relative">
      <MapContainer
        center={INDIA_CENTER}
        zoom={INDIA_ZOOM}
        bounds={INDIA_BOUNDS}
        className="h-full w-full z-0"
        zoomControl={false}
      >
        {/* ── Basemap ── */}
        {mapMode === 'heatmap' ? (
          <>
            {/* No-label base: only geography, zero competing text */}
            <TileLayer url={HEATMAP_TILES} attribution="&copy; CARTO" />
            {/* Labels layer rendered above heat so city names stay legible */}
            <TileLayer url={LABEL_TILES}   attribution="" pane="overlayPane" />
          </>
        ) : (
          <TileLayer url={SATELLITE_TILES} attribution="Tiles &copy; Esri" />
        )}

        {/* ── Heatmap visibility toggled smoothly via add/removeLayer ── */}
        <HeatmapLayer hotspots={hotspots} isVisible={mapMode === 'heatmap'} />

        {/* ── Zoom to India Button ── */}
        <ZoomResetButton />

        {/* ── Track zoom for marker visibility ── */}
        <ZoomWatcher onZoomChange={setCurrentZoom} />

        {/* ── Facilities — satellite mode only ── */}
        {mapMode === 'satellite' && facilities.map((fac, i) => (
          <Marker
            key={`fac-${i}`}
            position={[fac.geometry.coordinates[1], fac.geometry.coordinates[0]]}
            icon={facilityDivIcon}
          >
            <Popup>
              <div className="p-2 min-w-[160px]">
                <div className="font-bold text-sm mb-0.5">{fac.properties.name}</div>
                <div className="text-xs text-slate-500">{fac.properties.facility_type}</div>
              </div>
            </Popup>
          </Marker>
        ))}

        {/* ── Hotspot markers — zoom-gated in heatmap mode ── */}
        {showMarkers && hotspots.map((hotspot) => {
          const { properties, geometry } = hotspot;
          const isSelected = selectedHotspot?.properties?.id === properties.id;
          const color = getHotspotColor(properties.classification);
          return (
            <Marker
              key={`hs-${properties.id}`}
              position={[geometry.coordinates[1], geometry.coordinates[0]]}
              icon={makeDivIcon(properties.classification, isSelected, properties.is_persistent, properties.frp)}
              eventHandlers={{ click: () => setSelectedHotspot(hotspot) }}
              zIndexOffset={isSelected ? 1000 : 0}
            >
              <Popup>
                <div className="p-1 min-w-[220px]">
                  <div className="flex items-center gap-2 mb-2 pb-2 border-b border-slate-200">
                    <Flame className="w-4 h-4 shrink-0" style={{ color }} />
                    <span className="font-bold text-sm">{properties.classification}</span>
                  </div>
                  <div className="space-y-1 text-xs text-slate-600">
                    <div className="flex justify-between">
                      <span>Confidence:</span>
                      <span className="font-semibold text-slate-800">{properties.confidence_score}%</span>
                    </div>
                    <div className="flex justify-between">
                      <span>FRP:</span>
                      <span className="font-semibold text-slate-800">{properties.frp} MW</span>
                    </div>
                    <div className="flex justify-between">
                      <span>Risk Score:</span>
                      <span className={`font-semibold ${
                        properties.severity === 'High'   ? 'text-red-600'    :
                        properties.severity === 'Medium' ? 'text-orange-500' : 'text-green-600'
                      }`}>{properties.risk_score} ({properties.severity})</span>
                    </div>
                    <div className="flex justify-between">
                      <span>Detected:</span>
                      <span className="font-semibold text-slate-800">{properties.acq_date} {properties.acq_time}</span>
                    </div>
                    {properties.land_cover && properties.land_cover !== "Unknown" && (
                      <div className="flex justify-between">
                        <span>Land Cover:</span>
                        <span className="font-semibold text-slate-800">{properties.land_cover}</span>
                      </div>
                    )}
                    {properties.wind_speed !== undefined && (
                      <div className="flex justify-between">
                        <span>Wind Speed:</span>
                        <span className="font-semibold text-slate-800">{properties.wind_speed} m/s</span>
                      </div>
                    )}
                    {properties.nearest_facility_name && properties.nearest_facility_name !== 'N/A' && (
                      <div className="mt-2 pt-2 border-t border-slate-200">
                        <div className="text-slate-500 mb-1">Nearest Facility:</div>
                        <div className="flex items-start gap-1">
                          <Factory className="w-3 h-3 mt-0.5 text-blue-500 shrink-0" />
                          <div>
                            <div className="font-semibold text-slate-800">{properties.nearest_facility_name}</div>
                            <div className="text-[10px] text-slate-400">{properties.nearest_facility_dist_km} km away</div>
                          </div>
                        </div>
                      </div>
                    )}
                    {properties.is_persistent && (
                      <div className="mt-2 text-[10px] bg-red-50 text-red-700 px-2 py-1 rounded border border-red-200 font-semibold text-center uppercase tracking-wider">
                        ⚠ Persistent Source
                      </div>
                    )}
                  </div>
                </div>
              </Popup>
            </Marker>
          );
        })}

        {/* ── Auto-pan to clicked hotspot ── */}
        {selectedHotspot && (
          <MapController
            center={[selectedHotspot.geometry.coordinates[1], selectedHotspot.geometry.coordinates[0]]}
            selectedId={selectedHotspot.properties.id}
          />
        )}
      </MapContainer>

      <Legend mode={mapMode} />
    </div>
  );
}
