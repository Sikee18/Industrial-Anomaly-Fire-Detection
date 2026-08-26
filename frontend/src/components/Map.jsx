import React, { useEffect, useRef, useState } from 'react';
import { MapContainer, TileLayer, Marker, Popup, useMap } from 'react-leaflet';
import L from 'leaflet';
import 'leaflet.heat';
import { Flame, Factory, Layers } from 'lucide-react';

// ── Tile layer configs ───────────────────────────────────────────────────────
const BASEMAPS = {
  heatmap: {
    url: 'https://{s}.basemaps.cartocdn.com/light_nolabels/{z}/{x}/{y}{r}.png',
    labels: 'https://{s}.basemaps.cartocdn.com/light_only_labels/{z}/{x}/{y}{r}.png',
    attribution: '&copy; OpenStreetMap &copy; CARTO',
  },
  satellite: {
    url: 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
    labels: null,
    attribution: 'Tiles &copy; Esri',
  },
};

// ── Helpers ──────────────────────────────────────────────────────────────────
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
function HeatmapLayer({ hotspots }) {
  const map = useMap();
  const heatRef = useRef(null);

  useEffect(() => {
    if (!map || hotspots.length === 0) return;
    const points = hotspots.map(h => [
      h.geometry.coordinates[1],
      h.geometry.coordinates[0],
      Math.min(1.0, (h.properties.frp || 10) / 100),
    ]);
    if (heatRef.current) map.removeLayer(heatRef.current);
    heatRef.current = L.heatLayer(points, {
      radius: 30, blur: 22, maxZoom: 11, max: 1.0, minOpacity: 0.35,
      gradient: {
        0.0: '#0d0221', 0.15: '#3d0b71', 0.3: '#8b1a8f',
        0.5: '#d64045', 0.7: '#f7821b', 0.85: '#fbbf24', 1.0: '#fefce8',
      },
    }).addTo(map);
    return () => { if (heatRef.current) map.removeLayer(heatRef.current); };
  }, [map, hotspots]);

  return null;
}

// ── Basemap switcher ─────────────────────────────────────────────────────────
function BasemapLayer({ mode }) {
  const cfg = BASEMAPS[mode];
  return (
    <>
      <TileLayer url={cfg.url} attribution={cfg.attribution} />
      {cfg.labels && (
        <TileLayer url={cfg.labels} attribution="" pane="overlayPane" zIndex={500} />
      )}
    </>
  );
}

// ── Map pan controller ────────────────────────────────────────────────────────
function MapController({ center, selectedId }) {
  const map = useMap();
  useEffect(() => {
    if (center && selectedId) map.flyTo(center, 13, { duration: 1.5 });
  }, [center, selectedId, map]);
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
        {mode === 'heatmap' ? 'Thermal Intensity' : 'Classification'}
      </div>

      {mode === 'heatmap' ? (
        <>
          <div className="h-4 w-40 rounded" style={{
            background: 'linear-gradient(to right, #0d0221, #3d0b71, #8b1a8f, #d64045, #f7821b, #fbbf24, #fefce8)',
          }} />
          <div className="flex justify-between text-[10px] text-slate-400 mt-1">
            <span>Low FRP</span><span>High FRP</span>
          </div>
        </>
      ) : (
        <div className="space-y-1.5">
          {cats.map(c => (
            <div key={c.label} className="flex items-center gap-2 text-xs">
              <span className="text-sm leading-none">{c.emoji}</span>
              <span className="w-2 h-2 rounded-full shrink-0" style={{ backgroundColor: c.color, boxShadow: `0 0 5px ${c.color}` }} />
              <span>{c.label}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ── Mode Toggle Button ────────────────────────────────────────────────────────
function ModeToggle({ mode, setMode }) {
  return (
    <div className="absolute top-4 right-4 z-[1000] glass-panel rounded-xl p-1 shadow-2xl flex gap-1">
      {[
        { id: 'heatmap',   label: 'Heatmap',   icon: '🌡️' },
        { id: 'satellite', label: 'Satellite',  icon: '🛰️' },
      ].map(m => (
        <button
          key={m.id}
          onClick={() => setMode(m.id)}
          className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-all duration-200 ${
            mode === m.id
              ? 'bg-blue-600/80 text-white shadow-[0_0_12px_rgba(37,99,235,0.5)]'
              : 'text-slate-400 hover:text-white hover:bg-slate-700/60'
          }`}
        >
          <span>{m.icon}</span>
          <span>{m.label}</span>
        </button>
      ))}
    </div>
  );
}

// ── Main Map ──────────────────────────────────────────────────────────────────
export default function Map({ hotspots = [], facilities = [], selectedHotspot, setSelectedHotspot }) {
  const [mapMode, setMapMode] = useState('heatmap'); // default to heatmap for WOW opening
  const defaultCenter = [22.5, 82.5]; // center of India

  return (
    <div className="h-full w-full bg-slate-900 relative">
      <MapContainer center={defaultCenter} zoom={5} className="h-full w-full z-0" zoomControl={false}>

        <BasemapLayer mode={mapMode} />
        <HeatmapLayer hotspots={hotspots} />

        {/* In satellite mode, show individual markers */}
        {mapMode === 'satellite' && facilities.map((fac, i) => (
          <Marker key={`fac-${i}`}
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

        {/* Always show interactive hotspot markers */}
        {hotspots.map((hotspot) => {
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
                        properties.severity === 'High' ? 'text-red-600' :
                        properties.severity === 'Medium' ? 'text-orange-500' : 'text-green-600'
                      }`}>{properties.risk_score} ({properties.severity})</span>
                    </div>
                    <div className="flex justify-between">
                      <span>Detected:</span>
                      <span className="font-semibold text-slate-800">{properties.acq_date} {properties.acq_time}</span>
                    </div>
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

        {selectedHotspot && (
          <MapController
            center={[selectedHotspot.geometry.coordinates[1], selectedHotspot.geometry.coordinates[0]]}
            selectedId={selectedHotspot.properties.id}
          />
        )}
      </MapContainer>

      <ModeToggle mode={mapMode} setMode={setMapMode} />
      <Legend mode={mapMode} />
    </div>
  );
}
