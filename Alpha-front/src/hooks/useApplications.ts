import { useEffect, useState } from 'react'

import type { ApplicationSummary } from '@/lib/types'

export function useApplications() {
  const [applications] = useState<ApplicationSummary[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [refreshIndex, setRefreshIndex] = useState(0)

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setLoading(false)
    setError(null)
  }, [refreshIndex])

  function refetch() {
    setRefreshIndex((index) => index + 1)
  }

  return {
    applications,
    loading,
    error,
    refetch,
  }
}
