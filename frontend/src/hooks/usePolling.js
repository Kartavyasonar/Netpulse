import { useState, useEffect, useCallback } from 'react'

/**
 * Polls a fetch function on an interval.
 * Returns { data, loading, error, refetch }
 */
export function usePolling(fetchFn, interval = 30000, deps = []) {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const refetch = useCallback(async () => {
    try {
      setError(null)
      const result = await fetchFn()
      setData(result)
    } catch (e) {
      setError(e.message || 'Fetch failed')
    } finally {
      setLoading(false)
    }
  }, deps) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    refetch()
    const id = setInterval(refetch, interval)
    return () => clearInterval(id)
  }, [refetch, interval])

  return { data, loading, error, refetch }
}
