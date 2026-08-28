import React, { useMemo } from 'react';
import { Download, Activity, AlertTriangle, FileText, BarChart2 } from 'lucide-react';
import { PieChart, Pie, Cell, Tooltip, Legend, ResponsiveContainer, BarChart, Bar, XAxis, YAxis, CartesianGrid } from 'recharts';

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000/api';

export default function ReportsPanel({ hotspots = [], source, onClose }) {
  const handleDownload = () => {
    window.open(`${API_URL}/reports/download?source=${source}`, '_blank');
  };

  // Calculate stats dynamically
  const classCounts = {};
  const sevCounts = { High: 0, Medium: 0, Low: 0 };
  
  hotspots.forEach(h => {
    const cls = h.properties.classification;
    const sev = h.properties.severity;
    classCounts[cls] = (classCounts[cls] || 0) + 1;
    if (sevCounts[sev] !== undefined) sevCounts[sev]++;
  });

  // Prepare chart data
  const classData = Object.keys(classCounts).map(key => ({ name: key, value: classCounts[key] })).sort((a,b) => b.value - a.value);
  
  // Combine smaller classes if too many
  let finalClassData = classData;
  if (classData.length > 4) {
    const top = classData.slice(0, 3);
    const others = classData.slice(3).reduce((sum, item) => sum + item.value, 0);
    finalClassData = [...top, { name: 'Other', value: others }];
  }

  const sevData = [
    { name: 'High', value: sevCounts.High, color: '#ef4444' },
    { name: 'Medium', value: sevCounts.Medium, color: '#f97316' },
    { name: 'Low', value: sevCounts.Low, color: '#22c55e' }
  ].filter(d => d.value > 0);

  const COLORS = ['#3b82f6', '#8b5cf6', '#10b981', '#f59e0b', '#ec4899'];

  const topEvents = useMemo(() => {
    return [...hotspots]
      .sort((a, b) => b.properties.risk_score - a.properties.risk_score)
      .slice(0, 5)
      .map(h => ({
        id: h.properties.id,
        classification: h.properties.classification.length > 15 ? h.properties.classification.substring(0,15)+'...' : h.properties.classification,
        risk: h.properties.risk_score,
        frp: h.properties.frp,
        facility: h.properties.nearest_facility_name ? h.properties.nearest_facility_name.substring(0, 15)+'...' : 'None'
      }));
  }, [hotspots]);

  return (
    <div className="absolute inset-0 bg-slate-900/95 backdrop-blur-md z-[2000] flex flex-col p-6 overflow-y-auto custom-scrollbar animate-fade-in">
      
      {/* Header */}
      <div className="flex justify-between items-center mb-6 border-b border-slate-700 pb-4">
        <div>
          <h2 className="text-2xl font-bold text-white flex items-center gap-2">
            <FileText className="w-6 h-6 text-blue-400" />
            Insights & Reports
          </h2>
          <p className="text-slate-400 text-sm mt-1">
            Analyzing {hotspots.length} thermal anomalies from the {source.toUpperCase()} dataset
          </p>
        </div>
        
        <div className="flex gap-4">
          <button 
            onClick={handleDownload}
            className="flex items-center gap-2 bg-blue-600 hover:bg-blue-500 text-white px-4 py-2 rounded-lg font-semibold shadow-lg shadow-blue-900/50 transition-all"
          >
            <Download className="w-4 h-4" />
            Download PDF Report
          </button>
          <button 
            onClick={onClose}
            className="bg-slate-700 hover:bg-slate-600 text-white px-4 py-2 rounded-lg font-medium transition-colors"
          >
            Close Panel
          </button>
        </div>
      </div>

      {/* Charts Row */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-6">
        
        {/* Classification Pie Chart */}
        <div className="bg-slate-800/50 border border-slate-700 rounded-xl p-4 flex flex-col">
          <h3 className="text-white font-semibold mb-4 text-center">Classification Distribution</h3>
          <div className="flex-1 min-h-[250px]">
            {finalClassData.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={finalClassData}
                    cx="50%"
                    cy="50%"
                    outerRadius={80}
                    dataKey="value"
                    label={({ name, percent }) => `${name} ${(percent * 100).toFixed(0)}%`}
                    labelLine={false}
                  >
                    {finalClassData.map((entry, index) => (
                      <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                    ))}
                  </Pie>
                  <Tooltip contentStyle={{ backgroundColor: '#1e293b', borderColor: '#475569', color: '#f8fafc' }} />
                </PieChart>
              </ResponsiveContainer>
            ) : (
              <div className="h-full flex items-center justify-center text-slate-500">No Data</div>
            )}
          </div>
        </div>

        {/* Severity Donut Chart */}
        <div className="bg-slate-800/50 border border-slate-700 rounded-xl p-4 flex flex-col">
          <h3 className="text-white font-semibold mb-4 text-center">Severity Breakdown</h3>
          <div className="flex-1 min-h-[250px]">
            {sevData.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={sevData}
                    cx="50%"
                    cy="50%"
                    innerRadius={50}
                    outerRadius={80}
                    dataKey="value"
                    label={({ name, percent }) => `${name} ${(percent * 100).toFixed(0)}%`}
                    labelLine={false}
                  >
                    {sevData.map((entry, index) => (
                      <Cell key={`cell-${index}`} fill={entry.color} />
                    ))}
                  </Pie>
                  <Tooltip contentStyle={{ backgroundColor: '#1e293b', borderColor: '#475569', color: '#f8fafc' }} />
                  <Legend verticalAlign="bottom" height={36}/>
                </PieChart>
              </ResponsiveContainer>
            ) : (
              <div className="h-full flex items-center justify-center text-slate-500">No Data</div>
            )}
          </div>
        </div>

      </div>

      {/* Top 5 Risk Events Bar Chart & Table */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        
        {/* Bar Chart */}
        <div className="bg-slate-800/50 border border-slate-700 rounded-xl p-4 flex flex-col">
          <h3 className="text-white font-semibold mb-4 text-center">Top 5 Highest-Risk Events</h3>
          <div className="flex-1 min-h-[250px]">
             {topEvents.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={topEvents} layout="vertical" margin={{ top: 5, right: 30, left: 40, bottom: 5 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#334155" horizontal={false} />
                  <XAxis type="number" stroke="#94a3b8" />
                  <YAxis dataKey="classification" type="category" stroke="#94a3b8" width={80} tick={{fontSize: 10}} />
                  <Tooltip contentStyle={{ backgroundColor: '#1e293b', borderColor: '#475569', color: '#f8fafc' }} />
                  <Bar dataKey="risk" fill="#ef4444" radius={[0, 4, 4, 0]} barSize={20} />
                </BarChart>
              </ResponsiveContainer>
             ) : (
              <div className="h-full flex items-center justify-center text-slate-500">No Data</div>
             )}
          </div>
        </div>

        {/* Table */}
        <div className="bg-slate-800/50 border border-slate-700 rounded-xl p-4 overflow-hidden flex flex-col">
          <h3 className="text-white font-semibold mb-4">Event Details</h3>
          <div className="overflow-x-auto flex-1">
            <table className="w-full text-sm text-left">
              <thead className="text-xs text-slate-400 bg-slate-900/50 uppercase">
                <tr>
                  <th className="px-4 py-3 rounded-tl-lg">Class</th>
                  <th className="px-4 py-3">Risk</th>
                  <th className="px-4 py-3">FRP</th>
                  <th className="px-4 py-3 rounded-tr-lg">Facility</th>
                </tr>
              </thead>
              <tbody>
                {topEvents.length > 0 ? topEvents.map((ev, i) => (
                  <tr key={ev.id} className="border-b border-slate-700/50 hover:bg-slate-700/30">
                    <td className="px-4 py-3 font-medium text-slate-200">{ev.classification}</td>
                    <td className="px-4 py-3 text-red-400 font-bold">{ev.risk}</td>
                    <td className="px-4 py-3 text-orange-400">{ev.frp}</td>
                    <td className="px-4 py-3 text-slate-400 truncate max-w-[120px]" title={ev.facility}>{ev.facility}</td>
                  </tr>
                )) : (
                  <tr><td colSpan="4" className="px-4 py-8 text-center text-slate-500">No events found</td></tr>
                )}
              </tbody>
            </table>
          </div>
        </div>

      </div>

    </div>
  );
}
