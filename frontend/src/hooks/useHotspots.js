import { useState, useEffect, useCallback } from 'react';

const _base = (import.meta.env.VITE_API_URL || 'http://localhost:8000').replace(/\/$/, '');
const API_URL = `${_base}/api`;

export function useHotspots(source = 'live') {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const fetchHotspots = useCallback(async () => {
    setLoading(true);
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 10000); // 10s timeout
    try {
      const response = await fetch(
        `${API_URL}/hotspots?source=${source}&limit=2000`,
        { signal: controller.signal }
      );
      if (!response.ok) throw new Error('Failed to fetch hotspots');
      const result = await response.json();
      setData(result);
      setError(null);
    } catch (err) {
      if (err.name === 'AbortError') {
        console.warn('Hotspot fetch timed out — backend may be busy ingesting. Retrying in 15s...');
        setError('Backend busy — retrying...');
        // Retry once after 15s automatically
        setTimeout(fetchHotspots, 15000);
      } else {
        console.error(err);
        setError(err.message);
      }
    } finally {
      clearTimeout(timer);
      setLoading(false);
    }
  }, [source]);

  useEffect(() => {
    fetchHotspots();
    // Auto-refresh every 60s
    const interval = setInterval(fetchHotspots, 60000);
    return () => clearInterval(interval);
  }, [fetchHotspots]);

  return { data, loading, error, refetch: fetchHotspots };
}
