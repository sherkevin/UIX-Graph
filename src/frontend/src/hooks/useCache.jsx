// Custom Hook for Data Caching
import { useState, useEffect, useCallback } from 'react';
import config from '../config';

const useCache = (key, fetchFunction, options = {}) => {
  const {
    ttl = config.cache.ttl,
    enabled = config.cache.enabled,
    dependencies = [],
  } = options;

  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  // Get cached data
  const getCachedData = useCallback((cacheKey) => {
    if (!enabled) return null;

    try {
      const cached = localStorage.getItem(cacheKey);
      if (cached) {
        const { data, timestamp } = JSON.parse(cached);
        const now = Date.now();

        // Check if cache is still valid
        if (now - timestamp < ttl) {
          return data;
        } else {
          // Remove expired cache
          localStorage.removeItem(cacheKey);
        }
      }
    } catch (err) {
      console.error('Cache read error:', err);
    }

    return null;
  }, [enabled, ttl]);

  // Set cached data
  const setCachedData = useCallback((cacheKey, value) => {
    if (!enabled) return;

    try {
      const cacheData = {
        data: value,
        timestamp: Date.now(),
      };
      localStorage.setItem(cacheKey, JSON.stringify(cacheData));
    } catch (err) {
      console.error('Cache write error:', err);
    }
  }, [enabled]);

  // Invalidate cache
  const invalidateCache = useCallback((cacheKey) => {
    if (cacheKey) {
      localStorage.removeItem(cacheKey);
    } else {
      // Clear all cache if no key provided
      const keys = Object.keys(localStorage);
      keys.forEach((key) => {
        if (key.startsWith('cache_')) {
          localStorage.removeItem(key);
        }
      });
    }
  }, []);

  // Fetch data with cache support
  const fetchData = useCallback(async (useCache = true) => {
    const cacheKey = `cache_${key}`;

    // Try to get cached data first
    if (useCache) {
      const cached = getCachedData(cacheKey);
      if (cached) {
        setData(cached);
        return cached;
      }
    }

    setLoading(true);
    setError(null);

    try {
      const result = await fetchFunction();
      setData(result);

      // Cache the result
      setCachedData(cacheKey, result);

      return result;
    } catch (err) {
      setError(err);
      throw err;
    } finally {
      setLoading(false);
    }
  }, [key, fetchFunction, getCachedData, setCachedData]);

  // Auto-fetch on mount or when dependencies change
  useEffect(() => {
    fetchData();
  }, [fetchData, ...dependencies]);

  return {
    data,
    loading,
    error,
    refetch: () => fetchData(false), // Force refetch without cache
    invalidate: () => invalidateCache(`cache_${key}`),
    invalidateAll: invalidateCache,
    isLoading: loading,
    isError: error !== null,
    isSuccess: data !== null && error === null,
  };
};

export default useCache;
