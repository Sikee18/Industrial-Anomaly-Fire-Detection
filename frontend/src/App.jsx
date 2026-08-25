import React, { useState } from 'react';
import { useHotspots } from './hooks/useHotspots';
import { useFacilities } from './hooks/useFacilities';
import Map from './components/Map';
import Sidebar from './components/Sidebar';
import StatsBar from './components/StatsBar';
import { Activity } from 'lucide-react';

function App() {
  const [source, setSource] = useState('live'); // 'live' or 'demo'
  const [selectedHotspot, setSelectedHotspot] = useState(null);
  
  const { data: hotspotsData, loading: hotspotsLoading, error: hotspotsError, refetch } = useHotspots(source);
  const { data: facilitiesData } = useFacilities();

  // Basic stats
  const totalHotspots = hotspotsData?.count || 0;
  
  return (
    <div className="h-screen w-screen flex flex-col bg-slate-900 text-slate-100 overflow-hidden font-sans">
      
      {/* Header / Stats Bar */}
      <header className="glass-panel h-16 flex items-center justify-between px-4 z-10 shrink-0">
        <div className="flex items-center gap-3">
          <div className="bg-red-500/20 p-2 rounded-lg">
            <Activity className="w-6 h-6 text-red-500 animate-icon-pulse" />
          </div>
          <h1 className="text-xl font-bold bg-gradient-to-r from-red-400 to-orange-400 bg-clip-text text-transparent drop-shadow-md">
            Industrial Fire Monitor
          </h1>
        </div>
        
        <StatsBar source={source} setSource={setSource} onRefresh={refetch} />
      </header>

      {/* Main Content */}
      <main className="flex-1 flex overflow-hidden">
        
        {/* Map Area */}
        <section className="flex-1 relative z-0">
          <Map 
            hotspots={hotspotsData?.features || []}
            facilities={facilitiesData?.features || []}
            selectedHotspot={selectedHotspot}
            setSelectedHotspot={setSelectedHotspot}
          />
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
    </div>
  );
}

export default App;
