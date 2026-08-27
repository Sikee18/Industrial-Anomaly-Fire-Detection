import React, { useState } from 'react';
import { useHotspots } from './hooks/useHotspots';
import { useFacilities } from './hooks/useFacilities';
import Map from './components/Map';
import Sidebar from './components/Sidebar';
import StatsBar from './components/StatsBar';
import ReportsPanel from './components/ReportsPanel';
import PyroChat from './components/PyroChat';
import { Activity, BarChart2 } from 'lucide-react';

function App() {
  const [source, setSource] = useState('live'); // 'live' or 'demo'
  const [selectedHotspot, setSelectedHotspot] = useState(null);
  const [mapMode, setMapMode] = useState('heatmap'); // 'heatmap' or 'satellite'
  const [showReports, setShowReports] = useState(false);
  
  const { data: hotspotsData, loading: hotspotsLoading, error: hotspotsError, refetch } = useHotspots(source);
  const { data: facilitiesData } = useFacilities();

  // Handle mode switch — preserve map state, don't clear selection automatically
  const handleModeSwitch = (mode) => {
    if (mapMode === mode) return;
    setMapMode(mode);
  };
  
  return (
    <div className="h-screen w-screen flex flex-col bg-slate-900 text-slate-100 overflow-hidden font-sans">
      
      {/* Header / Stats Bar */}
      <header className="glass-panel h-16 flex items-center justify-between px-4 z-10 shrink-0 border-b border-slate-700/50 shadow-md">
        <div className="flex items-center gap-3">
          <div className="bg-red-500/20 p-2 rounded-lg">
            <Activity className="w-6 h-6 text-red-500 animate-icon-pulse" />
          </div>
          <h1 className="text-xl font-bold bg-gradient-to-r from-red-400 to-orange-400 bg-clip-text text-transparent drop-shadow-md hidden sm:block">
            Industrial Fire Monitor
          </h1>
        </div>

        <div className="flex items-center gap-3">
          <StatsBar source={source} setSource={setSource} onRefresh={refetch} />
          <button
            onClick={() => setShowReports(v => !v)}
            className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm font-medium border transition-all duration-200 ${
              showReports
                ? 'bg-blue-600 border-blue-500 text-white shadow-[0_0_12px_rgba(37,99,235,0.4)]'
                : 'bg-slate-800 border-slate-600 text-slate-300 hover:text-white hover:border-slate-500'
            }`}
            title="Insights & Reports"
          >
            <BarChart2 className="w-4 h-4" />
            <span className="hidden md:inline">Reports</span>
          </button>
        </div>
      </header>

      {/* Main Content */}
      <main className="flex-1 flex overflow-hidden relative">
        
        {/* Map Area */}
        <section className="flex-1 relative z-0 flex flex-col">
          
          {/* Top-Left Map Mode Tabs */}
          <div className="absolute top-4 left-4 z-[1000] flex bg-slate-800/90 p-1 rounded-lg border border-slate-600/60 shadow-xl backdrop-blur-md">
            <button
              onClick={() => handleModeSwitch('heatmap')}
              className={`flex items-center gap-1.5 px-4 py-1.5 rounded-md text-xs font-bold transition-all duration-300 ${
                mapMode === 'heatmap' 
                  ? 'bg-blue-600 text-white shadow-[0_0_10px_rgba(37,99,235,0.4)]' 
                  : 'text-slate-400 hover:text-slate-200 hover:bg-slate-700/50'
              }`}
            >
              <span>🌡️</span> Heatmap
            </button>
            <button
              onClick={() => handleModeSwitch('satellite')}
              className={`flex items-center gap-1.5 px-4 py-1.5 rounded-md text-xs font-bold transition-all duration-300 ${
                mapMode === 'satellite' 
                  ? 'bg-blue-600 text-white shadow-[0_0_10px_rgba(37,99,235,0.4)]' 
                  : 'text-slate-400 hover:text-slate-200 hover:bg-slate-700/50'
              }`}
            >
              <span>🛰️</span> Satellite
            </button>
          </div>

          <Map 
            hotspots={hotspotsData?.features || []}
            facilities={facilitiesData?.features || []}
            selectedHotspot={selectedHotspot}
            setSelectedHotspot={setSelectedHotspot}
            mapMode={mapMode}
          />

          {/* Reports Panel — Overlay on map section */}
          {showReports && (
            <ReportsPanel
              hotspots={hotspotsData?.features || []}
              source={source}
              onClose={() => setShowReports(false)}
            />
          )}
        </section>

        {/* Sidebar */}
        <aside className="glass-panel w-96 flex flex-col z-10 shadow-2xl">
          <Sidebar 
            hotspots={hotspotsData?.features || []} 
            loading={hotspotsLoading}
            error={hotspotsError}
            onSelect={setSelectedHotspot}
            selectedId={selectedHotspot?.properties?.id}
          />
        </aside>

      </main>

      {/* Pyro Floating Chatbot — global, outside main flow */}
      <PyroChat source={source} />
    </div>
  );
}

export default App;
