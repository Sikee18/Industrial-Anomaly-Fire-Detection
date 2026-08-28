import { useState, useEffect } from 'react';

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000/api';

export function useFacilities() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    const fetchFacilities = async () => {
      try {
        const response = await fetch(`${API_URL}/facilities`);
        if (!response.ok) throw new Error('Failed to fetch facilities');
        const result = await response.json();
        setData(result);
        setError(null);
      } catch (err) {
        console.error(err);
        setError(err.message);
      } finally {
        setLoading(false);
      }
    };

    fetchFacilities();
  }, []);

  return { data, loading, error };
}
