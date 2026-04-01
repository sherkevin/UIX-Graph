// Custom Hook for API Calls
import { useState, useEffect, useCallback } from 'react';
import { message } from 'antd';

const useApi = (apiFunction, options = {}) => {
  const { immediate = false, onSuccess, onError, defaultData = null } = options;

  const [data, setData] = useState(defaultData);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const execute = useCallback(
    async (...args) => {
      setLoading(true);
      setError(null);

      try {
        const response = await apiFunction(...args);
        const result = response.data;

        setData(result);

        if (onSuccess) {
          onSuccess(result);
        }

        return result;
      } catch (err) {
        const errorMessage = err.response?.data?.detail || err.message || 'An error occurred';
        setError(errorMessage);

        if (onError) {
          onError(err);
        } else {
          message.error(errorMessage);
        }

        throw err;
      } finally {
        setLoading(false);
      }
    },
    [apiFunction, onSuccess, onError]
  );

  const reset = useCallback(() => {
    setData(defaultData);
    setError(null);
    setLoading(false);
  }, [defaultData]);

  useEffect(() => {
    if (immediate) {
      execute();
    }
  }, [immediate, execute]);

  return {
    data,
    loading,
    error,
    execute,
    reset,
    isLoading: loading,
    isError: error !== null,
    isSuccess: data !== null && error === null,
  };
};

export default useApi;
