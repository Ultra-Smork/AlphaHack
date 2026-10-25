import { cn } from '@/lib/utils'
import { formatStatus } from '@/lib/formatters'
import type { ApplicationStatus } from '@/lib/types'

const statusStyles: Record<ApplicationStatus, string> = {
  DRAFT: 'bg-gray-100 text-gray-800',
  CANCELLED: 'bg-gray-100 text-gray-800',
  WITHDRAWN: 'bg-gray-100 text-gray-800',
  SUBMITTED: 'bg-blue-100 text-blue-800',
  INTAKE_CHECK: 'bg-blue-100 text-blue-800',
  ENRICHMENT: 'bg-blue-100 text-blue-800',
  SCORING: 'bg-blue-100 text-blue-800',
  NEEDS_INFO: 'bg-yellow-100 text-yellow-800',
  OFFER_MADE: 'bg-indigo-100 text-indigo-800',
  OFFER_ACCEPTED: 'bg-indigo-100 text-indigo-800',
  REJECTED: 'bg-red-100 text-red-800',
  OFFER_DECLINED: 'bg-red-100 text-red-800',
  OFFER_EXPIRED: 'bg-red-100 text-red-800',
}

export function StatusBadge({
  status,
  className,
}: {
  status: ApplicationStatus
  className?: string
}) {
  return (
    <span
      className={cn(
        'inline-flex rounded-full px-2 py-0.5 text-xs font-medium',
        statusStyles[status],
        className,
      )}
    >
      {formatStatus(status)}
    </span>
  )
}
