import React, { useState, useEffect } from 'react';
import { Flame, Factory, Database, RefreshCw, BarChart2 } from 'lucide-react';

const API_URL = 'http://localhost:8000/api';

export default function StatsBar({ source, setSource, onRefresh }) {
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(false);
  const [ingestStatus, setIngestStatus] = useState('idle');

  const fetchStats = async () => {
    try {
      const res = await fetch(`${API_URL}/stats?source=${source}`);
      if (res.ok) {
        const data = await res.json();
        setStats(data);
      }
    } catch (e) {
      console.error("Failed to fetch stats", e);
    }
  };

  useEffect(() => {
    fetchStats();
    const interval = setInterval(fetchStats, 60000);
    return () => clearInterval(interval);
  }, [source]);

  const handleRefresh = async () => {
    setLoading(true);
    await onRefresh();
    await fetchStats();
    setLoading(false);
  };

  const triggerIngest = async () => {
    setIngestStatus('ingesting');
    try {
      const endpoint = source === 'demo' ? '/ingest/demo' : '/ingest';
      const res = await fetch(`${API_URL}${endpoint}`, { method: 'POST' });
      const json = await res.json();

      if (source === 'demo' || json.status === 'demo_ingestion_complete') {
        // Demo ingest is synchronous — data is ready immediately
        await handleRefresh();
        setIngestStatus('success');
      } else {
        // Live ingest runs in background thread — poll until new data appears
        let attempts = 0;
        const poll = async () => {
          attempts++;
          await handleRefresh();
          const statsRes = await fetch(`${API_URL}/stats?source=${source}`);
          const stats = await statsRes.json();
          if (stats.total_hotspots > 0 || attempts >= 6) {
            setIngestStatus('success');
          } else {
            setTimeout(poll, 5000); // retry every 5s up to 30s
          }
        };
        setTimeout(poll, 3000); // give background thread a 3s head start
      }
      setTimeout(() => setIngestStatus('idle'), 3000);
    } catch (e) {
      console.error('Ingest failed', e);
      setIngestStatus('error');
      setTimeout(() => setIngestStatus('idle'), 3000);
    }
  };


  return (
    <div className="flex items-center gap-6 h-full text-sm">
      
      {stats && (
        <div className="flex items-center gap-6 glass-panel px-4 py-1.5 rounded-full shadow-lg">
          <div className="flex items-center gap-2 transition-transform hover:scale-110 cursor-default" title="Total Hotspots">
            <Flame className="w-4 h-4 text-orange-500 animate-icon-pulse" />
            <span className="font-bold text-white">{stats.total_hotspots}</span>
          </div>
          
          <div className="flex items-center gap-2 transition-transform hover:scale-110 cursor-default" title="Industrial Fires">
            <Factory className="w-4 h-4 text-red-500" />
            <span className="font-bold text-white">{stats.industrial_fires}</span>
          </div>
          
          <div className="flex items-center gap-2 transition-transform hover:scale-110 cursor-default" title="Persistent Sources">
            <Database className="w-4 h-4 text-blue-400" />
            <span className="font-bold text-white">{stats.persistent_sources}</span>
          </div>
          
          <div className="flex items-center gap-2 border-l border-slate-600/50 pl-4 transition-transform hover:scale-110 cursor-default" title="False Alarm Reduction">
            <BarChart2 className="w-4 h-4 text-green-400" />
            <span className="font-bold text-green-400">{stats.false_alarm_reduction_pct}%</span>
            <span className="text-slate-400 text-xs hidden lg:inline">Reduction</span>
          </div>
        </div>
      )}

      <div className="flex items-center gap-3">
        <div className="flex glass-panel p-1 rounded-lg">
          <button
            className={`px-3 py-1 rounded-md text-xs font-medium transition-all duration-300 ${source === 'live' ? 'bg-blue-600/90 text-white shadow-[0_0_10px_rgba(37,99,235,0.5)]' : 'text-slate-400 hover:text-white hover:bg-slate-700/50'}`}
            onClick={() => setSource('live')}
          >
            Live Mode
          </button>
          <button
            className={`px-3 py-1 rounded-md text-xs font-medium transition-all duration-300 ${source === 'demo' ? 'bg-purple-600/90 text-white shadow-[0_0_10px_rgba(147,51,234,0.5)]' : 'text-slate-400 hover:text-white hover:bg-slate-700/50'}`}
            onClick={() => setSource('demo')}
          >
            Demo Mode
          </button>
        </div>

        <button 
          onClick={triggerIngest}
          disabled={ingestStatus !== 'idle'}
          className={`flex items-center gap-1 glass-panel px-3 py-1.5 rounded-lg transition-all duration-300 hover:-translate-y-0.5 disabled:opacity-80 disabled:hover:translate-y-0 ${
            ingestStatus === 'success' ? 'bg-green-600/50 border-green-400/50 text-green-300' :
            ingestStatus === 'error' ? 'bg-red-600/50 border-red-400/50 text-red-300' :
            'hover:bg-slate-700/80 hover:shadow-[0_0_15px_rgba(255,255,255,0.1)] text-slate-200'
          }`}
          title="Force data ingestion"
        >
          <Database className={`w-3.5 h-3.5 ${ingestStatus === 'idle' ? 'text-slate-300' : 'text-current'}`} />
          <span className="text-xs font-medium">
            {ingestStatus === 'ingesting' ? 'Ingesting...' : 
             ingestStatus === 'success' ? 'Updated!' :
             ingestStatus === 'error' ? 'Failed!' : 'Ingest Data'}
          </span>
        </button>

        <button 
          onClick={handleRefresh}
          disabled={loading}
          className="p-1.5 rounded-lg glass-panel hover:bg-slate-700/80 transition-all duration-300 hover:shadow-[0_0_15px_rgba(255,255,255,0.1)] hover:-translate-y-0.5 text-slate-400 hover:text-white disabled:opacity-50 disabled:hover:translate-y-0"
          title="Refresh view"
        >
          <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin text-blue-400' : ''}`} />
        </button>
      </div>

    </div>
  );
}
