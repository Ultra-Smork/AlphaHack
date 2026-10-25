import type { ApplicationStatus } from '@/lib/types'

type ProductId = 1 | 2

const statusLabels: Record<ApplicationStatus, string> = {
  DRAFT: 'Черновик',
  SUBMITTED: 'Подана',
  INTAKE_CHECK: 'Проверка',
  NEEDS_INFO: 'Нужны данные',
  ENRICHMENT: 'Обогащение',
  SCORING: 'Скоринг',
  OFFER_MADE: 'Предложение',
  OFFER_ACCEPTED: 'Принята',
  REJECTED: 'Отказ',
  CANCELLED: 'Отменена',
  WITHDRAWN: 'Отозвана',
  OFFER_DECLINED: 'Отклонена',
  OFFER_EXPIRED: 'Истекла',
}

const productLabels: Record<ProductId, string> = {
  1: 'Оборотные средства',
  2: 'Оборудование',
}

const moneyFormatter = new Intl.NumberFormat('ru-RU', {
  maximumFractionDigits: 0,
})

const moneyWithCentsFormatter = new Intl.NumberFormat('ru-RU', {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
})

const dateFormatter = new Intl.DateTimeFormat('ru-RU', {
  dateStyle: 'short',
  timeStyle: 'short',
})

export function formatMoney(
  value: number | null | undefined,
  options: { cents?: boolean } = {},
) {
  if (value === null || value === undefined || !Number.isFinite(value)) {
    return '—'
  }
  const formatter = options.cents ? moneyWithCentsFormatter : moneyFormatter
  return `${formatter.format(value)} ₽`
}

export function formatDate(value: string | null | undefined) {
  if (!value) {
    return '—'
  }
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) {
    return '—'
  }
  return dateFormatter.format(date)
}

export function formatStatus(status: ApplicationStatus) {
  return statusLabels[status]
}

export function formatProduct(productId: number) {
  return productLabels[productId as ProductId] ?? '—'
}
