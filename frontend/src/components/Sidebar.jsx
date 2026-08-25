import React, { useState, useEffect } from 'react';
import { AlertTriangle, Clock, Activity, Flame, ShieldAlert } from 'lucide-react';

export default function Sidebar({ hotspots = [], loading, error, onSelect, selectedId }) {
  const [activeTab, setActiveTab] = useState('alerts'); // alerts, all

  const highSeverity = hotspots.filter(h => h.properties.severity === 'High');
  const mediumSeverity = hotspots.filter(h => h.properties.severity === 'Medium');
  
  // Combine high and some medium for alerts tab
  const alertList = [...highSeverity, ...mediumSeverity].sort((a, b) => b.properties.risk_score - a.properties.risk_score);
  
  const displayList = activeTab === 'alerts' ? alertList : hotspots;

  if (loading) {
    return (
      <div className="flex-1 flex items-center justify-center p-8">
        <div className="animate-pulse flex flex-col items-center">
          <Activity className="w-8 h-8 text-slate-500 mb-2 animate-spin" />
          <span className="text-slate-400">Loading data...</span>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center p-8 text-center">
        <ShieldAlert className="w-10 h-10 text-red-500 mb-2" />
        <h3 className="text-white font-bold mb-1">Error Loading Data</h3>
        <p className="text-slate-400 text-sm">{error}</p>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full overflow-hidden text-slate-200">
      <div className="p-4 border-b border-slate-600/50 shrink-0 bg-slate-900/40">
        <h2 className="text-lg font-bold text-white flex items-center gap-2">
          <AlertTriangle className="w-5 h-5 text-amber-500" />
          Live Event Feed
        </h2>
        <div className="flex gap-2 mt-3 bg-slate-900 p-1 rounded-lg">
          <button 
            onClick={() => setActiveTab('alerts')}
            className={`flex-1 py-1.5 text-sm font-medium rounded-md transition-colors ${activeTab === 'alerts' ? 'bg-slate-700 text-white shadow' : 'text-slate-400 hover:text-slate-300'}`}
          >
            High Risk ({highSeverity.length})
          </button>
          <button 
            onClick={() => setActiveTab('all')}
            className={`flex-1 py-1.5 text-sm font-medium rounded-md transition-colors ${activeTab === 'all' ? 'bg-slate-700 text-white shadow' : 'text-slate-400 hover:text-slate-300'}`}
          >
            All Events ({hotspots.length})
          </button>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-2 space-y-2 custom-scrollbar">
        {displayList.length === 0 ? (
          <div className="text-center py-8 text-slate-500 text-sm">
            No events to display
          </div>
        ) : (
          displayList.map((hotspot, index) => {
            const { properties } = hotspot;
            const isSelected = selectedId === properties.id;
            const isHigh = properties.severity === 'High';
            
            return (
              <div 
                key={properties.id}
                onClick={() => onSelect(hotspot)}
                className={`animate-slide-in p-3 rounded-lg border cursor-pointer transition-all duration-300 hover:scale-[1.02] ${
                  isSelected 
                    ? 'bg-slate-700/80 border-blue-400 shadow-[0_0_15px_rgba(59,130,246,0.5)]' 
                    : 'bg-slate-900/60 border-slate-600/50 hover:bg-slate-800/80 hover:border-slate-500 hover:shadow-lg'
                }`}
                style={{ animationDelay: `${Math.min(index * 0.05, 0.5)}s` }}
              >
                <div className="flex justify-between items-start mb-2">
                  <div className="flex items-center gap-2">
                    <div className={`w-2 h-2 rounded-full ${isHigh ? 'bg-red-500' : (properties.severity === 'Medium' ? 'bg-orange-500' : 'bg-green-500')}`} />
                    <span className="font-semibold text-sm text-white truncate max-w-[180px]" title={properties.classification}>
                      {properties.classification}
                    </span>
                  </div>
                  <div className={`text-xs px-2 py-0.5 rounded font-medium ${
                    isHigh ? 'bg-red-500/20 text-red-400 border border-red-500/30' : 'bg-slate-700 text-slate-300 border border-slate-600'
                  }`}>
                    Risk: {properties.risk_score}
                  </div>
                </div>
                
                <div className="grid grid-cols-2 gap-2 text-xs text-slate-400 mt-2">
                  <div className="flex items-center gap-1" title="Fire Radiative Power">
                    <Flame className="w-3 h-3 text-orange-400" />
                    <span>{properties.frp} MW</span>
                  </div>
                  <div className="flex items-center gap-1" title="Confidence Score">
                    <ShieldAlert className="w-3 h-3 text-blue-400" />
                    <span>Conf: {properties.confidence_score}%</span>
                  </div>
                  <div className="flex items-center gap-1" title="Acquisition Time">
                    <Clock className="w-3 h-3 text-slate-500" />
                    <span>{properties.acq_time}z</span>
                  </div>
                </div>
                
                {properties.is_persistent && (
                  <div className="mt-2 pt-2 border-t border-slate-700/50">
                    <span className="text-[10px] text-red-400 font-medium flex items-center gap-1">
                      <span className="w-1.5 h-1.5 rounded-full bg-red-500 animate-pulse"></span>
                      Persistent Source
                    </span>
                  </div>
                )}
              </div>
            )
          })
        )}
      </div>
    </div>
  );
}
