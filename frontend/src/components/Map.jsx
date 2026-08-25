import React, { useEffect, useRef } from 'react';
import { MapContainer, TileLayer, CircleMarker, Marker, Popup, useMap } from 'react-leaflet';
import L from 'leaflet';
import 'leaflet.heat';
import { Flame, Factory } from 'lucide-react';

// Custom icons for facilities
const facilityIcon = new L.DivIcon({
  html: `<div style="background:rgba(59,130,246,0.25);padding:3px;border:1.5px solid #60a5fa;border-radius:50%;display:flex;align-items:center;justify-content:center;">
           <div style="width:6px;height:6px;background:#60a5fa;border-radius:50%;"></div>
         </div>`,
  className: 'custom-facility-icon',
  iconSize: [20, 20],
  iconAnchor: [10, 10],
});

const getHotspotColor = (classification) => {
  switch (classification) {
    case 'Industrial Fire': return '#ef4444';
    case 'Gas Flare': return '#f97316';
    case 'Mining Thermal Activity': return '#eab308';
    case 'Agricultural Burn': return '#22c55e';
    case 'Wildfire': return '#b91c1c';
    default: return '#94a3b8';
  }
};

// ── Heatmap Layer Component ──────────────────────────────────────────────────
function HeatmapLayer({ hotspots }) {
  const map = useMap();
  const heatLayerRef = useRef(null);

  useEffect(() => {
    if (!map || hotspots.length === 0) return;

    // Build heatmap points: [lat, lng, intensity]
    const heatData = hotspots.map(h => {
      const lat = h.geometry.coordinates[1];
      const lng = h.geometry.coordinates[0];
      const frp = h.properties.frp || 10;
      // Normalize intensity: higher FRP = brighter glow
      const intensity = Math.min(1.0, frp / 150);
      return [lat, lng, intensity];
    });

    // Remove previous layer if exists
    if (heatLayerRef.current) {
      map.removeLayer(heatLayerRef.current);
    }

    heatLayerRef.current = L.heatLayer(heatData, {
      radius: 25,
      blur: 18,
      maxZoom: 10,
      max: 1.0,
      minOpacity: 0.35,
      gradient: {
        0.0: '#000004',
        0.2: '#420a68',
        0.4: '#932667',
        0.5: '#dd513a',
        0.7: '#f98e09',
        0.85: '#fca50a',
        1.0: '#fcffa4',
      },
    }).addTo(map);

    return () => {
      if (heatLayerRef.current) {
        map.removeLayer(heatLayerRef.current);
      }
    };
  }, [map, hotspots]);

  return null;
}

// ── Map Controller (auto-pan) ────────────────────────────────────────────────
function MapController({ center, selectedId }) {
  const map = useMap();
  useEffect(() => {
    if (center && selectedId) {
      map.flyTo(center, 13, { duration: 1.5 });
    }
  }, [center, selectedId, map]);
  return null;
}

// ── Legend Component ─────────────────────────────────────────────────────────
function Legend() {
  const categories = [
    { label: 'Industrial Fire', color: '#ef4444' },
    { label: 'Gas Flare', color: '#f97316' },
    { label: 'Mining Activity', color: '#eab308' },
    { label: 'Agricultural Burn', color: '#22c55e' },
    { label: 'Wildfire', color: '#b91c1c' },
    { label: 'Unclassified', color: '#94a3b8' },
  ];

  return (
    <div className="absolute bottom-6 left-4 z-[1000] glass-panel rounded-xl px-4 py-3 shadow-2xl">
      <div className="text-[11px] font-bold text-slate-300 uppercase tracking-wider mb-2">Classification</div>
      <div className="space-y-1.5">
        {categories.map(c => (
          <div key={c.label} className="flex items-center gap-2 text-xs text-slate-300">
            <span className="w-3 h-3 rounded-full shrink-0 shadow-sm" style={{ backgroundColor: c.color }} />
            <span>{c.label}</span>
          </div>
        ))}
      </div>
      <div className="mt-3 pt-2 border-t border-slate-600/50">
        <div className="text-[11px] font-bold text-slate-300 uppercase tracking-wider mb-1.5">Intensity</div>
        <div className="h-3 w-full rounded-sm" style={{
          background: 'linear-gradient(to right, #000004, #420a68, #932667, #dd513a, #f98e09, #fcffa4)',
        }} />
        <div className="flex justify-between text-[10px] text-slate-400 mt-0.5">
          <span>Low</span>
          <span>High</span>
        </div>
      </div>
    </div>
  );
}

// ── Main Map Component ───────────────────────────────────────────────────────
export default function Map({ hotspots = [], facilities = [], selectedHotspot, setSelectedHotspot }) {
  const defaultCenter = [22.0, 79.0];

  return (
    <div className="h-full w-full bg-slate-900 relative">
      <MapContainer 
        center={defaultCenter} 
        zoom={5} 
        className="h-full w-full z-0"
        zoomControl={false}
      >
        <TileLayer
          url="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
          attribution='Tiles &copy; Esri'
        />

        {/* Heatmap overlay */}
        <HeatmapLayer hotspots={hotspots} />

        {/* Render Facilities */}
        {facilities.map((fac, i) => (
          <Marker 
            key={`fac-${i}`} 
            position={[fac.geometry.coordinates[1], fac.geometry.coordinates[0]]}
            icon={facilityIcon}
          >
            <Popup className="custom-popup">
              <div className="p-2 text-slate-800">
                <h3 className="font-bold text-sm mb-1">{fac.properties.name}</h3>
                <p className="text-xs text-slate-500">{fac.properties.facility_type}</p>
              </div>
            </Popup>
          </Marker>
        ))}

        {/* Render Hotspots as markers */}
        {hotspots.map((hotspot) => {
          const { properties, geometry } = hotspot;
          const color = getHotspotColor(properties.classification);
          const isSelected = selectedHotspot?.properties?.id === properties.id;
          const isPersistent = properties.is_persistent;
          const radius = isSelected ? 8 : (properties.frp > 100 ? 6 : 4);
          
          return (
            <CircleMarker
              key={`hs-${properties.id}`}
              center={[geometry.coordinates[1], geometry.coordinates[0]]}
              radius={radius}
              pathOptions={{
                color: isSelected ? '#fff' : color,
                weight: isSelected ? 2.5 : 1.5,
                fillColor: color,
                fillOpacity: 0.85,
                className: isPersistent ? 'pulse-marker' : ''
              }}
              eventHandlers={{
                click: () => setSelectedHotspot(hotspot),
              }}
            >
              <Popup className="custom-popup bg-slate-800 text-white rounded-lg border border-slate-700">
                <div className="p-1 min-w-[220px]">
                  <div className="flex items-center gap-2 mb-2 pb-2 border-b border-slate-700">
                    <Flame className="w-4 h-4" style={{ color }} />
                    <span className="font-bold text-sm text-slate-200">{properties.classification}</span>
                  </div>
                  
                  <div className="space-y-1.5 text-xs text-slate-300">
                    <div className="flex justify-between">
                      <span className="text-slate-400">Confidence:</span>
                      <span className="font-medium text-white">{properties.confidence_score}%</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-slate-400">FRP:</span>
                      <span className="font-medium text-white">{properties.frp} MW</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-slate-400">Risk Score:</span>
                      <span className={`font-medium ${
                        properties.severity === 'High' ? 'text-red-400' :
                        properties.severity === 'Medium' ? 'text-orange-400' : 'text-green-400'
                      }`}>{properties.risk_score} ({properties.severity})</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-slate-400">Date/Time:</span>
                      <span className="font-medium text-white">{properties.acq_date} {properties.acq_time}</span>
                    </div>
                    
                    {properties.nearest_facility_name !== 'N/A' && (
                      <div className="mt-2 pt-2 border-t border-slate-700">
                        <div className="text-slate-400 mb-1">Nearest Facility:</div>
                        <div className="flex items-start gap-1">
                          <Factory className="w-3 h-3 mt-0.5 text-blue-400" />
                          <div>
                            <div className="text-white font-medium">{properties.nearest_facility_name}</div>
                            <div className="text-[10px] text-slate-400">{properties.nearest_facility_dist_km} km away</div>
                          </div>
                        </div>
                      </div>
                    )}

                    {properties.is_persistent && (
                      <div className="mt-2 text-[10px] bg-red-500/20 text-red-300 px-2 py-1 rounded border border-red-500/30 font-medium text-center uppercase tracking-wider">
                        Persistent Source Detected
                      </div>
                    )}
                  </div>
                </div>
              </Popup>
            </CircleMarker>
          );
        })}

        {/* Auto-pan to selected hotspot */}
        {selectedHotspot && (
          <MapController 
            center={[selectedHotspot.geometry.coordinates[1], selectedHotspot.geometry.coordinates[0]]} 
            selectedId={selectedHotspot.properties.id} 
          />
        )}
      </MapContainer>

      {/* Map Legend */}
      <Legend />
    </div>
  );
}
