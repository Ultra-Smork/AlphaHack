import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Briefcase, FileText, RefreshCw, Wrench } from 'lucide-react'

import { StatusBadge } from '@/components/StatusBadge'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { toast } from '@/hooks/use-toast'
import { api, getApiErrorMessage } from '@/lib/api'
import { formatDate, formatMoney, formatProduct } from '@/lib/formatters'
import type { ApplicationStatus, ApplicationSummary } from '@/lib/types'

type Filter = 'all' | 'processing' | 'completed'

const PROCESSING_STATUSES = new Set<ApplicationStatus>([
  'SUBMITTED',
  'INTAKE_CHECK',
  'ENRICHMENT',
  'SCORING',
  'NEEDS_INFO',
  'OFFER_MADE',
])

const COMPLETED_STATUSES = new Set<ApplicationStatus>([
  'OFFER_ACCEPTED',
  'REJECTED',
  'OFFER_DECLINED',
  'OFFER_EXPIRED',
  'WITHDRAWN',
  'CANCELLED',
])

const filters: Array<{ value: Filter; label: string }> = [
  { value: 'all', label: 'Все' },
  { value: 'processing', label: 'В обработке' },
  { value: 'completed', label: 'Завершённые' },
]

function matchesFilter(status: ApplicationStatus, filter: Filter) {
  if (filter === 'processing') {
    return PROCESSING_STATUSES.has(status)
  }
  if (filter === 'completed') {
    return COMPLETED_STATUSES.has(status)
  }
  return true
}

export function ApplicationsListPage() {
  const [applications, setApplications] = useState<ApplicationSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [filter, setFilter] = useState<Filter>('all')
  const [reloadKey, setReloadKey] = useState(0)

  useEffect(() => {
    let cancelled = false

    async function load() {
      setLoading(true)
      setError(null)
      try {
        const response = await api.get<ApplicationSummary[]>('/api/applications')
        if (!cancelled) {
          setApplications(response.data)
        }
      } catch (cause) {
        if (!cancelled) {
          const message = getApiErrorMessage(
            cause,
            'Не удалось загрузить заявки',
          )
          setError(message)
          toast.error(message)
        }
      } finally {
        if (!cancelled) {
          setLoading(false)
        }
      }
    }

    void load()
    return () => {
      cancelled = true
    }
  }, [reloadKey])

  const total = applications.length
  const processing = applications.filter((application) =>
    PROCESSING_STATUSES.has(application.status),
  ).length
  const approved = applications.filter(
    (application) =>
      application.status === 'OFFER_MADE' ||
      application.status === 'OFFER_ACCEPTED',
  ).length
  const visibleApplications = applications.filter((application) =>
    matchesFilter(application.status, filter),
  )

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Мои заявки</h1>
        <p className="mt-1 text-sm text-gray-600">
          Заявки на кредитные продукты для вашего бизнеса
        </p>
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <div className="rounded-lg border border-gray-200 bg-white p-6">
          <p className="text-sm text-gray-500">Всего заявок</p>
          <p className="mt-2 text-3xl font-bold text-gray-900">{total}</p>
        </div>
        <div className="rounded-lg border border-gray-200 bg-white p-6">
          <p className="text-sm text-gray-500">В обработке</p>
          <p className="mt-2 text-3xl font-bold text-gray-900">{processing}</p>
        </div>
        <div className="rounded-lg border border-gray-200 bg-white p-6">
          <p className="text-sm text-gray-500">Одобрено</p>
          <p className="mt-2 text-3xl font-bold text-gray-900">{approved}</p>
        </div>
      </div>

      <div className="flex flex-wrap gap-2">
        {filters.map((item) => (
          <button
            key={item.value}
            type="button"
            onClick={() => setFilter(item.value)}
            aria-pressed={filter === item.value}
            className={
              filter === item.value
                ? 'rounded-md bg-indigo-600 px-3 py-2 text-sm font-medium text-white transition-colors duration-150'
                : 'rounded-md border border-gray-200 bg-white px-3 py-2 text-sm font-medium text-gray-700 transition-colors duration-150 hover:bg-gray-50'
            }
          >
            {item.label}
          </button>
        ))}
      </div>

      {loading ? (
        <div className="space-y-4">
          {[0, 1, 2].map((item) => (
            <Skeleton
              key={item}
              className="h-24 rounded-lg bg-gray-100"
            />
          ))}
        </div>
      ) : error ? (
        <div className="rounded-lg border border-red-200 bg-red-50 p-5">
          <p className="text-sm text-red-700">{error}</p>
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="mt-3"
            onClick={() => setReloadKey((value) => value + 1)}
          >
            <RefreshCw />
            Повторить
          </Button>
        </div>
      ) : applications.length === 0 ? (
        <div className="flex flex-col items-center justify-center rounded-lg border border-gray-200 bg-white px-6 py-14 text-center">
          <FileText className="h-12 w-12 text-gray-400" />
          <h2 className="mt-4 text-lg font-semibold text-gray-900">
            У вас пока нет заявок
          </h2>
          <p className="mt-1 max-w-md text-sm text-gray-600">
            Нажмите «Создать заявку» в верхней панели, чтобы узнать вероятность
            одобрения
          </p>
        </div>
      ) : visibleApplications.length === 0 ? (
        <div className="rounded-lg border border-gray-200 bg-white p-8 text-center">
          <p className="text-sm text-gray-600">
            В этой категории пока нет заявок.
          </p>
        </div>
      ) : (
        <div className="space-y-4">
          {visibleApplications.map((application) => {
            const revisionData = application.current_revision?.data
            const amount = revisionData?.amount ?? null
            const term = revisionData?.term_months ?? null
            const ProductIcon =
              application.product_id === 1 ? Briefcase : Wrench

            return (
              <Link
                key={application.id}
                to={`/applications/${application.id}`}
                className="block"
              >
                <Card className="cursor-pointer transition-shadow duration-150 hover:shadow-md">
                  <CardContent className="flex flex-col gap-4 p-6 sm:flex-row sm:items-center sm:justify-between">
                    <div className="flex items-center gap-4">
                      <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-full bg-indigo-50 text-indigo-600">
                        <ProductIcon className="h-6 w-6" />
                      </div>
                      <div>
                        <p className="font-semibold text-gray-900">
                          {formatProduct(application.product_id)}
                        </p>
                        <p className="mt-1 text-sm text-gray-500">
                          {formatMoney(amount)}
                          {term !== null ? ` · ${term} мес.` : ''}
                        </p>
                      </div>
                    </div>

                    <div className="flex items-center justify-between gap-3 sm:flex-col sm:items-end">
                      <StatusBadge status={application.status} />
                      <span className="text-xs text-gray-500">
                        {formatDate(application.created_at)}
                      </span>
                    </div>
                  </CardContent>
                </Card>
              </Link>
            )
          })}
        </div>
      )}
    </div>
  )
}
