import { useCallback, useEffect, useMemo, useState } from 'react'
import type { FormEvent } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import {
  Check,
  CheckCircle,
  CheckCircle2,
  Clock,
  FileText,
  Info,
  Loader2,
  Pencil,
  Send,
  Undo2,
  XCircle,
} from 'lucide-react'
import type { LucideIcon } from 'lucide-react'

import { ConfirmDialog } from '@/components/ConfirmDialog'
import { StatusBadge } from '@/components/StatusBadge'
import { Button } from '@/components/ui/button'
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Skeleton } from '@/components/ui/skeleton'
import { toast } from '@/hooks/use-toast'
import { api, apiMutation, getApiErrorMessage } from '@/lib/api'
import { parseNumericInput } from '@/lib/numberInput'
import {
  formatDate,
  formatMoney,
  formatProduct,
  formatStatus,
} from '@/lib/formatters'
import { cn } from '@/lib/utils'
import type {
  ApplicationDetail,
  ApplicationEvent,
  ApplicationRevision,
  ApplicationStatus,
  Offer,
  UpdateApplicationInput,
} from '@/lib/types'

const PROCESSING_STATUSES = new Set<ApplicationStatus>([
  'SUBMITTED',
  'INTAKE_CHECK',
  'ENRICHMENT',
  'SCORING',
])

const REFUSAL_STATUSES = new Set<ApplicationStatus>([
  'REJECTED',
  'OFFER_DECLINED',
  'OFFER_EXPIRED',
])

const STEP_LABELS = [
  'Создана',
  'Подана',
  'Оценка',
  'Предложение',
  'Принята',
]

const RISK_BAND_LABELS: Record<string, string> = {
  LOW: 'Низкий риск',
  MEDIUM: 'Средний риск',
  HIGH: 'Высокий риск',
}

const RISK_FACTOR_LABELS: Record<string, string> = {
  SHORT_BUSINESS_HISTORY: 'Возраст бизнеса',
  LOW_CASH_MARGIN: 'Доступный денежный поток',
  REVENUE_VOLATILITY: 'Вариация выручки',
  CLIENT_CONCENTRATION: 'Концентрация на клиенте',
  DELINQUENCY_HISTORY: 'Просрочки',
  EXISTING_DEBT_BURDEN: 'Существующая долговая нагрузка',
}

const MISSING_FIELD_LABELS: Record<string, string> = {
  'financials.monthly_revenue_rub': 'Выручка',
  'financials.monthly_cash_available_for_debt_service_rub':
    'Доступный денежный поток',
  'financials.existing_monthly_debt_service_rub':
    'Текущая долговая нагрузка',
  'financials.revenue_cv_12m': 'Вариация выручки',
  'financials.largest_customer_share': 'Доля крупнейшего клиента',
  credit_report_consent_valid: 'Согласие на проверку кредитной истории',
}

const NEXT_ACTION_LABELS: Record<string, string> = {
  ACCEPT_OR_DECLINE_OFFER: 'Примите или отклоните предложение.',
  PROVIDE_INFORMATION: 'Добавьте недостающие сведения и подайте заявку снова.',
  VIEW_RESULT: 'Ознакомьтесь с результатом.',
  CHANGE_PRODUCT: 'Попробуйте другой продукт.',
  WAIT_FOR_REVIEW: 'Заявка ожидает дополнительной проверки.',
}

const POLICY_REASON_CODES = new Set(['PRODUCT_BUSINESS_AGE_REQUIREMENT'])

const PRODUCT_ADJUSTMENT_REASONS = new Set([
  'AMOUNT_LIMITED_BY_PRODUCT_OR_AFFORDABILITY',
  'TERM_CHANGED_TO_PRODUCT_RANGE',
])

type DecisionStepState = 'passed' | 'failed' | 'skipped' | 'info'

const DECISION_STEP_STYLES: Record<
  DecisionStepState,
  { Icon: LucideIcon; tone: string }
> = {
  passed: { Icon: CheckCircle2, tone: 'text-green-600' },
  failed: { Icon: XCircle, tone: 'text-red-600' },
  skipped: { Icon: Clock, tone: 'text-gray-400' },
  info: { Icon: Info, tone: 'text-blue-600' },
}

function DecisionStep({
  state,
  title,
  detail,
}: {
  state: DecisionStepState
  title: string
  detail: string
}) {
  const { Icon, tone } = DECISION_STEP_STYLES[state]
  return (
    <div className="flex items-start gap-3">
      <Icon className={cn('mt-0.5 h-5 w-5 shrink-0', tone)} />
      <div>
        <p className="text-sm font-medium text-gray-900">{title}</p>
        <p className="mt-0.5 text-sm text-gray-600">{detail}</p>
      </div>
    </div>
  )
}

function formatRate(rate: number) {
  return `${(rate * 100).toLocaleString('ru-RU', {
    maximumFractionDigits: 2,
  })}%`
}

type Action = 'submit' | 'withdraw' | 'accept' | 'decline'

type EditFieldErrors = Partial<
  Record<
    | 'amount'
    | 'term'
    | 'age'
    | 'revenue'
    | 'cash'
    | 'debt'
    | 'cv'
    | 'share'
    | 'consent',
    string
  >
>

function editFieldClass(hasError: boolean, withSuffix = false) {
  return cn(
    withSuffix ? 'pr-9' : '',
    hasError && 'border-red-500 focus-visible:ring-red-500',
  )
}

const actionCopy: Record<
  Action,
  { title: string; description: string; confirmLabel: string; destructive?: boolean }
> = {
  submit: {
    title: 'Подать заявку?',
    description: 'Заявка уйдёт на оценку нейросети. Это действие нельзя отменить.',
    confirmLabel: 'Подать',
  },
  withdraw: {
    title: 'Отозвать заявку?',
    description: 'Заявка будет отозвана. Это действие нельзя отменить.',
    confirmLabel: 'Отозвать',
    destructive: true,
  },
  accept: {
    title: 'Принять предложение?',
    description: 'Вы принимаете условия предложения. Это действие нельзя отменить.',
    confirmLabel: 'Принять',
  },
  decline: {
    title: 'Отклонить предложение?',
    description: 'Предложение будет отклонено. Это действие нельзя отменить.',
    confirmLabel: 'Отклонить',
    destructive: true,
  },
}

function getStepper(status: ApplicationStatus): {
  active: number
  variant: 'normal' | 'rejected' | 'withdrawn'
} | null {
  if (status === 'DRAFT' || status === 'CANCELLED') {
    return null
  }
  if (status === 'SUBMITTED') {
    return { active: 1, variant: 'normal' }
  }
  if (
    status === 'INTAKE_CHECK' ||
    status === 'ENRICHMENT' ||
    status === 'SCORING' ||
    status === 'NEEDS_INFO'
  ) {
    return { active: 2, variant: 'normal' }
  }
  if (status === 'OFFER_MADE') {
    return { active: 3, variant: 'normal' }
  }
  if (status === 'OFFER_ACCEPTED') {
    return { active: 4, variant: 'normal' }
  }
  if (status === 'REJECTED') {
    return { active: 2, variant: 'rejected' }
  }
  if (status === 'OFFER_DECLINED' || status === 'OFFER_EXPIRED') {
    return { active: 3, variant: 'rejected' }
  }
  return { active: 0, variant: 'withdrawn' }
}

function stepClasses(
  index: number,
  active: number,
  variant: 'normal' | 'rejected' | 'withdrawn',
) {
  if (variant === 'withdrawn') {
    return index === active
      ? 'border-gray-500 bg-gray-500 text-white'
      : 'border-gray-200 bg-gray-200 text-gray-500'
  }
  if (index < active) {
    return 'border-indigo-200 bg-indigo-200 text-indigo-700'
  }
  if (index === active) {
    return variant === 'rejected'
      ? 'border-red-600 bg-red-600 text-white'
      : 'border-indigo-600 bg-indigo-600 text-white'
  }
  return 'border-gray-200 bg-gray-200 text-gray-500'
}

function ApplicationStepper({ status }: { status: ApplicationStatus }) {
  const stepper = getStepper(status)
  if (!stepper) {
    return null
  }

  return (
    <div className="rounded-lg border border-gray-200 bg-white p-5">
      <div className="flex items-start">
        {STEP_LABELS.map((label, index) => {
          const isLast = index === STEP_LABELS.length - 1
          const isComplete = index < stepper.active
          const isActive = index === stepper.active
          return (
            <div
              key={label}
              className={
                isLast
                  ? 'flex flex-col items-center gap-1.5'
                  : 'flex flex-1 flex-col items-center gap-1.5'
              }
            >
              <div className="flex w-full items-center">
                <div
                  className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full border-2 text-xs font-semibold ${stepClasses(
                    index,
                    stepper.active,
                    stepper.variant,
                  )}`}
                  aria-current={isActive ? 'step' : undefined}
                >
                  {isComplete ? <Check className="h-4 w-4" /> : index + 1}
                </div>
                {!isLast ? (
                  <div
                    className={`mx-2 h-px flex-1 ${
                      isComplete ? 'bg-indigo-200' : 'bg-gray-200'
                    }`}
                  />
                ) : null}
              </div>
              <span
                className={`text-center text-xs ${
                  isActive
                    ? 'font-medium text-gray-900'
                    : 'text-gray-500'
                }`}
              >
                {label}
              </span>
            </div>
          )
        })}
      </div>
    </div>
  )
}

function eventVisual(event: ApplicationEvent): {
  Icon: LucideIcon
  tone: string
} {
  const type = event.event_type.toUpperCase()
  if (type === 'CREATED') {
    return { Icon: FileText, tone: 'border-gray-200 text-gray-600' }
  }
  if (type === 'SUBMITTED') {
    return { Icon: Send, tone: 'border-blue-200 text-blue-600' }
  }
  if (type === 'OFFER_MADE') {
    return { Icon: CheckCircle2, tone: 'border-indigo-200 text-indigo-600' }
  }
  if (type === 'OFFER_ACCEPTED') {
    return { Icon: CheckCircle, tone: 'border-green-200 text-green-600' }
  }
  if (REFUSAL_STATUSES.has(event.to_status) || type === 'REJECTED') {
    return { Icon: XCircle, tone: 'border-red-200 text-red-600' }
  }
  return { Icon: Clock, tone: 'border-gray-200 text-gray-500' }
}

function reasonText(reason: string | { text: string }) {
  return typeof reason === 'string' ? reason : reason.text
}

function reasonCode(reason: string | { code: string }) {
  return typeof reason === 'string' ? reason : reason.code
}

function reasonDetails(reason: string | { details?: { title?: string; current?: string; limit?: string; action?: string } | null }) {
  return typeof reason === 'string' ? null : reason.details ?? null
}

function isApplicationDetail(value: unknown): value is ApplicationDetail {
  return (
    typeof value === 'object' &&
    value !== null &&
    'id' in value &&
    'status' in value &&
    'created_at' in value
  )
}

export function ApplicationDetailPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const applicationId = Number(id)

  const [application, setApplication] = useState<ApplicationDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [action, setAction] = useState<Action | null>(null)
  const [actionLoading, setActionLoading] = useState(false)
  const [actionError, setActionError] = useState<string | null>(null)
  const [editOpen, setEditOpen] = useState(false)
  const [editLoading, setEditLoading] = useState(false)
  const [editError, setEditError] = useState<string | null>(null)
  const [editFieldErrors, setEditFieldErrors] = useState<EditFieldErrors>({})
  const [editAmount, setEditAmount] = useState('')
  const [editTerm, setEditTerm] = useState('')
  const [editAge, setEditAge] = useState('')
  const [editRevenue, setEditRevenue] = useState('')
  const [editCash, setEditCash] = useState('')
  const [editDebt, setEditDebt] = useState('')
  const [editCv, setEditCv] = useState('')
  const [editShare, setEditShare] = useState('')
  const [editPurpose, setEditPurpose] = useState('')
  const [editConsent, setEditConsent] = useState(false)

  const fetchApplication = useCallback(
    async (silent = false) => {
      if (!Number.isFinite(applicationId) || applicationId <= 0) {
        setError('Некорректный номер заявки')
        setLoading(false)
        return
      }

      if (!silent) {
        setLoading(true)
      }

      try {
        const response = await api.get<ApplicationDetail>(
          `/api/applications/${applicationId}`,
        )
        setApplication(response.data)
        setError(null)
      } catch (cause) {
        if (!silent) {
          const message = getApiErrorMessage(
            cause,
            'Не удалось загрузить заявку',
          )
          setError(message)
          toast.error(message)
        }
      } finally {
        if (!silent) {
          setLoading(false)
        }
      }
    },
    [applicationId],
  )

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void fetchApplication()
  }, [fetchApplication])

  useEffect(() => {
    const status = application?.status
    if (!status || !PROCESSING_STATUSES.has(status)) {
      return
    }
    const timer = window.setInterval(() => {
      void fetchApplication(true)
    }, 3000)
    return () => window.clearInterval(timer)
  }, [application?.status, fetchApplication])

  const currentRevision: ApplicationRevision | null =
    application?.current_revision ?? null
  const data = currentRevision?.data
  const offers: Offer[] = application?.offers ?? []
  const latestOffer = offers.length > 0 ? offers[offers.length - 1] : null
  const evaluations = application?.evaluations ?? []
  const latestEvaluation =
    evaluations.length > 0 ? evaluations[evaluations.length - 1] : null
  const events = useMemo(() => {
    return [...(application?.events ?? [])].sort((a, b) => {
      const dateDiff =
        new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
      return dateDiff || b.id - a.id
    })
  }, [application?.events])

  function clearEditFieldError(field: keyof EditFieldErrors) {
    setEditFieldErrors((current) => {
      if (!current[field]) {
        return current
      }
      const next = { ...current }
      delete next[field]
      return next
    })
  }

  function openEditDialog() {
    if (!data) {
      return
    }
    setEditAmount(String(data.amount))
    setEditTerm(String(data.term_months))
    setEditAge(String(data.company_age_months))
    setEditRevenue(
      data.monthly_revenue === null || data.monthly_revenue === undefined
        ? ''
        : String(data.monthly_revenue),
    )
    setEditCash(
      data.monthly_cash_available_for_debt_service_rub === null ||
        data.monthly_cash_available_for_debt_service_rub === undefined
        ? ''
        : String(data.monthly_cash_available_for_debt_service_rub),
    )
    setEditDebt(
      data.existing_debt === null || data.existing_debt === undefined
        ? ''
        : String(data.existing_debt),
    )
    setEditCv(
      data.revenue_cv_12m === null || data.revenue_cv_12m === undefined
        ? ''
        : String(data.revenue_cv_12m),
    )
    setEditShare(
      data.largest_customer_share === null ||
        data.largest_customer_share === undefined
        ? ''
        : String(data.largest_customer_share),
    )
    setEditPurpose(data.purpose ?? '')
    setEditConsent(Boolean(data.credit_report_consent_valid))
    setEditError(null)
    setEditFieldErrors({})
    setEditOpen(true)
  }

  async function handleEditSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!currentRevision) {
      return
    }

    const amount = parseNumericInput(editAmount)
    const term = Number(editTerm)
    const age = Number(editAge)
    const revenue = parseNumericInput(editRevenue)
    const cash = parseNumericInput(editCash)
    const debt = parseNumericInput(editDebt)
    const cv = editCv ? Number(editCv) : null
    const share = editShare ? Number(editShare) : null

    const nextErrors: EditFieldErrors = {}
    if (
      amount === null ||
      !Number.isInteger(amount) ||
      amount < 1 ||
      amount > 1_000_000_000
    ) {
      nextErrors.amount = 'Сумма должна быть целым числом от 1 до 1 000 000 000 ₽'
    }
    if (
      !Number.isFinite(term) ||
      !Number.isInteger(term) ||
      term < 1 ||
      term > 120
    ) {
      nextErrors.term = 'Срок должен быть целым числом от 1 до 120 месяцев'
    }
    if (
      editAge.trim() === '' ||
      !Number.isFinite(age) ||
      !Number.isInteger(age) ||
      age < 0 ||
      age > 1200
    ) {
      nextErrors.age = 'Возраст бизнеса должен быть целым числом от 0 до 1200 месяцев'
    }
    if (editRevenue.trim() !== '' && revenue === null) {
      nextErrors.revenue = 'Выручка должна быть неотрицательным числом'
    }
    if (editCash.trim() !== '' && cash === null) {
      nextErrors.cash = 'Укажите корректную сумму'
    }
    if (editDebt.trim() !== '' && debt === null) {
      nextErrors.debt = 'Долговая нагрузка должна быть неотрицательным числом'
    }
    if (cv !== null && (!Number.isFinite(cv) || cv < 0 || cv > 1)) {
      nextErrors.cv = 'Укажите значение от 0 до 1'
    }
    if (share !== null && (!Number.isFinite(share) || share < 0 || share > 1)) {
      nextErrors.share = 'Укажите значение от 0 до 1'
    }
    if (!editConsent) {
      nextErrors.consent = 'Требуется согласие'
    }
    setEditFieldErrors(nextErrors)
    if (Object.keys(nextErrors).length > 0) {
      return
    }
    if (amount === null) {
      return
    }

    const payload: UpdateApplicationInput = {
      expected_revision: currentRevision.version,
      data: {
        amount,
        term_months: term,
        company_age_months: age,
        credit_report_consent_valid: editConsent,
        ...(revenue !== null ? { monthly_revenue: revenue } : {}),
        ...(cash !== null
          ? { monthly_cash_available_for_debt_service_rub: cash }
          : {}),
        ...(debt !== null ? { existing_debt: debt } : {}),
        ...(cv !== null ? { revenue_cv_12m: cv } : {}),
        ...(share !== null ? { largest_customer_share: share } : {}),
        ...(editPurpose.trim() ? { purpose: editPurpose.trim() } : {}),
      },
    }

    setEditLoading(true)
    setEditError(null)
    setActionError(null)

    try {
      const response = await api.patch<ApplicationDetail>(
        `/api/applications/${applicationId}`,
        payload,
      )
      setApplication(response.data)
    } catch (cause) {
      const message = getApiErrorMessage(cause, 'Не удалось обновить заявку')
      setEditError(message)
      toast.error(message)
      setEditLoading(false)
      return
    }

    setEditOpen(false)
    try {
      const response = await apiMutation(
        'POST',
        `/api/applications/${applicationId}/submit`,
      )
      if (isApplicationDetail(response.data)) {
        setApplication(response.data)
      } else {
        await fetchApplication(true)
      }
      toast.success(
        'Данные сохранены. Заявка отправлена на повторную оценку.',
      )
    } catch (cause) {
      const message = getApiErrorMessage(
        cause,
        'Данные сохранены, но не удалось отправить заявку на повторную оценку.',
      )
      setActionError(message)
      toast.error(message)
    } finally {
      setEditLoading(false)
    }
  }

  async function confirmAction() {
    if (!action) {
      return
    }

    setActionError(null)
    setActionLoading(true)
    try {
      let response
      if (action === 'submit') {
        response = await apiMutation(
          'POST',
          `/api/applications/${applicationId}/submit`,
        )
      } else if (action === 'withdraw') {
        response = await apiMutation(
          'POST',
          `/api/applications/${applicationId}/withdraw`,
        )
      } else {
        if (!latestOffer) {
          throw new Error('Предложение не найдено')
        }
        response = await apiMutation(
          'POST',
          `/api/applications/${applicationId}/offers/${latestOffer.id}/${action}`,
        )
      }

      setAction(null)
      setActionError(null)
      if (isApplicationDetail(response.data)) {
        setApplication(response.data)
      } else {
        await fetchApplication(true)
      }
      toast.success('Заявка обновлена')
    } catch (cause) {
      const message = getApiErrorMessage(cause, 'Ошибка')
      setAction(null)
      setActionError(message)
      toast.error(message)
    } finally {
      setActionLoading(false)
    }
  }

  if (loading) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-4 w-48" />
        <Skeleton className="h-9 w-80" />
        <Skeleton className="h-24 w-full rounded-lg" />
        <div className="grid gap-4 sm:grid-cols-2">
          <Skeleton className="h-40 w-full rounded-lg" />
          <Skeleton className="h-40 w-full rounded-lg" />
        </div>
        <Skeleton className="h-64 w-full rounded-lg" />
      </div>
    )
  }

  if (error || !application) {
    return (
      <div className="mx-auto max-w-2xl space-y-4 rounded-lg border border-red-200 bg-red-50 p-5">
        <p className="text-sm text-red-700">{error ?? 'Заявка не найдена'}</p>
        <div className="flex gap-3">
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => void fetchApplication()}
          >
            Повторить
          </Button>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={() => navigate('/applications')}
          >
            К заявкам
          </Button>
        </div>
      </div>
    )
  }

  const isProcessing = PROCESSING_STATUSES.has(application.status)
  const riskCategory = latestEvaluation?.risk_category?.toUpperCase()
  const hasRisk = Boolean(riskCategory)
  const riskFactors = latestEvaluation?.risk_details?.factors ?? []
  const decisionStage = latestEvaluation?.decision_stage ?? null
  const isPolicyRefusal =
    decisionStage === 'PRODUCT_ELIGIBILITY' ||
    (latestEvaluation?.reason_codes.some((reason) =>
      POLICY_REASON_CODES.has(reasonCode(reason)),
    ) ??
      false)
  const policyReason = latestEvaluation?.reason_codes.find((reason) =>
    POLICY_REASON_CODES.has(reasonCode(reason)),
  )
  const policyDetails = policyReason ? reasonDetails(policyReason) : null
  const productAdjustmentReason = latestEvaluation?.reason_codes.find(
    (reason) => PRODUCT_ADJUSTMENT_REASONS.has(reasonCode(reason)),
  )
  const missingFields = latestEvaluation?.missing_fields ?? []
  const riskLabel = riskCategory
    ? RISK_BAND_LABELS[riskCategory] ?? riskCategory
    : null
  const rateLabel = latestOffer ? `${formatRate(latestOffer.rate)} годовых` : null
  const offerDetail =
    latestOffer && rateLabel
      ? `${formatMoney(latestOffer.amount)} · ${rateLabel} · ${formatMoney(
          latestOffer.payment,
          { cents: true },
        )}/мес`
      : null

  const dataStepState: DecisionStepState = missingFields.length
    ? 'failed'
    : 'passed'
  const dataStepDetail = missingFields.length
    ? `Не хватает: ${missingFields
        .map((field) => MISSING_FIELD_LABELS[field] ?? field)
        .join(', ')}.`
    : 'Все обязательные сведения заполнены.'

  const productStepState: DecisionStepState = isPolicyRefusal
    ? 'failed'
    : productAdjustmentReason
      ? 'info'
      : decisionStage === 'DATA'
        ? 'skipped'
        : 'passed'
  const productStepDetail = isPolicyRefusal
    ? policyDetails?.title && policyDetails.current
      ? `${policyDetails.title}: ${policyDetails.current}. ${
          policyDetails.limit ?? ''
        }`.trim()
      : 'Не выполнены формальные требования продукта.'
    : productAdjustmentReason
      ? reasonText(productAdjustmentReason)
      : decisionStage === 'DATA'
        ? 'Не проверялись: сначала нужны данные.'
        : 'Продукт и параметры заявки допустимы.'

  const riskStepState: DecisionStepState = !hasRisk
    ? 'skipped'
    : isPolicyRefusal
      ? 'info'
      : decisionStage === 'RISK'
        ? 'failed'
        : 'passed'
  const riskStepDetail = hasRisk
    ? `${Math.round(
        latestEvaluation?.risk_score ?? 0,
      )} из 100 — ${(riskLabel ?? '').toLowerCase()}${
        isPolicyRefusal ? '. Справочно: на отказ не повлияла.' : '.'
      }`
    : '0 из 100 — недостаточно данных для расчёта.'

  const offerStepState: DecisionStepState = latestOffer ? 'passed' : 'skipped'
  const offerStepDetail = offerDetail
    ? offerDetail
    : isPolicyRefusal
      ? 'Не сформирован: заявка остановлена на условиях продукта.'
      : decisionStage === 'DATA'
        ? 'Не сформирован: не хватает данных.'
        : 'Не сформирован: банк не нашёл доступных условий.'

  return (
    <div className="space-y-6">
      <div>
        <nav className="flex items-center gap-2 text-sm text-gray-500">
          <Link
            to="/applications"
            className="transition-colors duration-150 hover:text-gray-900"
          >
            Мои заявки
          </Link>
          <span>/</span>
          <span className="text-gray-700">Заявка #{application.id}</span>
        </nav>

        <div className="mt-3 flex flex-wrap items-start justify-between gap-4">
          <div>
            <p className="text-sm text-gray-500">
              {formatProduct(application.product_id)}
            </p>
            <h1 className="mt-1 text-2xl font-bold text-gray-900">
              Заявка на {formatMoney(data?.amount)}
            </h1>
          </div>
          <StatusBadge status={application.status} />
        </div>
      </div>

      {application.status === 'DRAFT' ? (
        <div className="rounded-lg border border-blue-200 bg-blue-50 p-4">
          <p className="text-sm text-blue-800">
            Это черновик. Подайте заявку, чтобы нейросеть ее оценила.
          </p>
        </div>
      ) : null}

      {application.status === 'NEEDS_INFO' ? (
        <div className="rounded-lg border border-yellow-200 bg-yellow-50 p-4">
          <p className="text-sm font-medium text-yellow-900">
            Недостаточно данных для оценки риска.
          </p>
          <p className="mt-1 text-sm text-yellow-800">
            Дополните заявку и проверьте, каких сведений не хватает.
          </p>
          {latestEvaluation?.missing_fields?.length ? (
            <ul className="mt-2 list-inside list-disc text-sm text-yellow-800">
              {latestEvaluation.missing_fields.map((field) => (
                <li key={field}>{MISSING_FIELD_LABELS[field] ?? field}</li>
              ))}
            </ul>
          ) : null}
        </div>
      ) : null}

      <ApplicationStepper status={application.status} />

      {actionError ? (
        <div className="rounded-lg border border-red-200 bg-red-50 p-4">
          <p className="text-sm font-medium text-red-800">
            Не удалось выполнить действие
          </p>
          <p className="mt-1 text-sm text-red-700">{actionError}</p>
        </div>
      ) : null}

      {REFUSAL_STATUSES.has(application.status) ? (
        <div
          className="rounded-lg border-2 border-red-300 bg-red-50 p-5"
          role="alert"
        >
          <div className="flex items-start gap-3">
            <XCircle className="mt-0.5 h-6 w-6 shrink-0 text-red-600" />
            <div>
              <p className="text-base font-semibold text-red-900">
                {application.status === 'REJECTED'
                  ? isPolicyRefusal
                    ? 'Заявка не прошла проверку условий продукта'
                    : 'Заявка не одобрена'
                  : application.status === 'OFFER_DECLINED'
                    ? 'Вы отклонили предложение'
                    : 'Срок предложения истёк'}
              </p>
              {application.status === 'REJECTED' && isPolicyRefusal ? (
                <p className="mt-1 text-sm text-red-800">
                  Это не отказ по оценке риска. Заявка остановлена формальным
                  требованием продукта.
                </p>
              ) : null}
            </div>
          </div>

          {application.status === 'REJECTED' ? (
            latestEvaluation?.reason_codes.length ? (
              <div className="mt-4 space-y-3">
                {latestEvaluation.reason_codes.map((reason, index) => {
                  const details = reasonDetails(reason)
                  return (
                    <div
                      key={`${reasonCode(reason)}-${index}`}
                      className="rounded-md border border-red-100 bg-white p-4"
                    >
                      <p className="text-sm font-semibold text-red-900">
                        {reasonText(reason)}
                      </p>
                      {details?.title && details.current ? (
                        <p className="mt-2 text-sm text-gray-800">
                          {details.title}:{' '}
                          <span className="font-medium">
                            {details.current}
                          </span>
                        </p>
                      ) : null}
                      {details?.limit ? (
                        <p className="text-sm text-gray-600">
                          {details.limit}
                        </p>
                      ) : null}
                      {details?.action ? (
                        <p className="mt-3 rounded-md bg-red-50 px-3 py-2 text-sm font-medium text-red-800">
                          Что сделать: {details.action}
                        </p>
                      ) : null}
                    </div>
                  )
                })}
              </div>
            ) : (
              <p className="mt-3 text-sm text-red-800">
                Причина не указана. Попробуйте изменить параметры заявки.
              </p>
            )
          ) : (
            <p className="mt-3 text-sm text-red-800">
              {application.status === 'OFFER_DECLINED'
                ? 'Предложение отклонено. Вы можете подать новую заявку с другими параметрами.'
                : 'Срок действия предложения истёк. Подайте заявку снова, чтобы получить актуальные условия.'}
            </p>
          )}
        </div>
      ) : null}

      {isProcessing ? (
        <div className="flex items-center gap-3 rounded-lg border border-blue-200 bg-blue-50 p-4">
          <Loader2 className="h-5 w-5 animate-spin text-blue-600" />
          <p className="text-sm text-blue-800">
            Нейросеть оценивает ваш бизнес...
          </p>
        </div>
      ) : null}

      <Card>
        <CardHeader>
          <CardTitle className="text-lg">Данные заявки</CardTitle>
        </CardHeader>
        <CardContent>
          <dl className="grid gap-4 sm:grid-cols-2">
            <div>
              <dt className="text-sm text-gray-500">Сумма</dt>
              <dd className="mt-1 font-medium text-gray-900">
                {formatMoney(data?.amount)}
              </dd>
            </div>
            <div>
              <dt className="text-sm text-gray-500">Срок</dt>
              <dd className="mt-1 font-medium text-gray-900">
                {data ? `${data.term_months} мес.` : '—'}
              </dd>
            </div>
            <div>
              <dt className="text-sm text-gray-500">Возраст бизнеса</dt>
              <dd className="mt-1 font-medium text-gray-900">
                {data ? `${data.company_age_months} мес.` : '—'}
              </dd>
            </div>
            <div>
              <dt className="text-sm text-gray-500">Выручка в месяц</dt>
              <dd className="mt-1 font-medium text-gray-900">
                {formatMoney(data?.monthly_revenue)}
              </dd>
            </div>
            <div className="sm:col-span-2">
              <dt className="text-sm text-gray-500">Цель</dt>
              <dd className="mt-1 font-medium text-gray-900">
                {data?.purpose || '—'}
              </dd>
            </div>
          </dl>
        </CardContent>
      </Card>

      {latestOffer &&
      (application.status === 'OFFER_MADE' ||
        application.status === 'OFFER_ACCEPTED') ? (
        <Card>
          <CardHeader>
            <CardTitle className="text-lg">Предложение</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-3xl font-bold text-gray-900">
              {formatMoney(latestOffer.amount)}
            </p>

            <div className="mt-4 grid grid-cols-3 gap-4 text-sm">
              <div>
                <p className="text-gray-500">Ставка</p>
                <p className="mt-1 font-medium text-gray-900">
                  {rateLabel}
                </p>
              </div>
              <div>
                <p className="text-gray-500">Срок</p>
                <p className="mt-1 font-medium text-gray-900">
                  {latestOffer.term} мес.
                </p>
              </div>
              <div>
                <p className="text-gray-500">Платёж</p>
                <p className="mt-1 font-medium text-gray-900">
                  {formatMoney(latestOffer.payment, { cents: true })}
                </p>
              </div>
            </div>

            <p className="mt-4 text-xs text-gray-500">
              Коэффициент покрытия долга:{' '}
              {latestOffer.dscr === null || latestOffer.dscr === undefined
                ? '—'
                : latestOffer.dscr.toFixed(2)}
            </p>

            {application.status === 'OFFER_ACCEPTED' ? (
              <div className="mt-4 rounded-md border border-green-200 bg-green-50 p-3">
                <p className="text-sm font-medium text-green-800">
                  ✓ Предложение принято. Банк свяжется с вами для оформления.
                </p>
              </div>
            ) : null}
          </CardContent>
        </Card>
      ) : null}

      {latestEvaluation ? (
        <Card>
          <CardHeader>
            <CardTitle className="text-lg">Как принималось решение</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-4">
              <DecisionStep
                state={dataStepState}
                title="Данные заявки"
                detail={dataStepDetail}
              />
              <DecisionStep
                state={productStepState}
                title="Условия продукта"
                detail={productStepDetail}
              />
              <DecisionStep
                state={riskStepState}
                title="Оценка риска"
                detail={riskStepDetail}
              />
              <DecisionStep
                state={offerStepState}
                title="Предложение"
                detail={offerStepDetail}
              />
            </div>

            {hasRisk ? (
              <p className="mt-4 text-xs text-gray-500">
                Оценка риска — это не вероятность одобрения. Балл показывает
                устойчивость заявки по возрасту бизнеса, денежному потоку,
                выручке и долговой нагрузке.
              </p>
            ) : null}

            {riskFactors.length > 0 ? (
              <div className="mt-4">
                <p className="text-sm font-medium text-gray-900">
                  Факторы оценки риска
                </p>
                <ul className="mt-2 space-y-2">
                  {riskFactors.map((factor) => (
                    <li
                      key={factor.code}
                      className="flex items-start gap-2 text-sm text-gray-600"
                    >
                      <Info className="mt-0.5 h-4 w-4 shrink-0 text-gray-400" />
                      <span>
                        {RISK_FACTOR_LABELS[factor.code] ?? factor.code}:{' '}
                        {factor.points} баллов
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}

            {!REFUSAL_STATUSES.has(application.status) &&
            latestEvaluation.reason_codes.length > 0 ? (
              <div className="mt-4">
                <p className="text-sm font-medium text-gray-900">
                  Почему такое решение
                </p>
                <div className="mt-2 space-y-2">
                  {latestEvaluation.reason_codes.map((reason, index) => {
                    const details = reasonDetails(reason)
                    return (
                      <div
                        key={`${reasonCode(reason)}-${index}`}
                        className="rounded-md bg-gray-50 p-3 text-sm text-gray-700"
                      >
                        <p className="font-medium text-gray-900">
                          {reasonText(reason)}
                        </p>
                        {details?.title && details.current ? (
                          <p className="mt-1">
                            {details.title}: {details.current}
                          </p>
                        ) : null}
                        {details?.limit ? (
                          <p className="text-xs text-gray-600">
                            {details.limit}
                          </p>
                        ) : null}
                        {details?.action ? (
                          <p className="mt-1 text-xs text-gray-600">
                            {details.action}
                          </p>
                        ) : null}
                      </div>
                    )
                  })}
                </div>
              </div>
            ) : null}

            {latestEvaluation.next_action ? (
              <p className="mt-4 text-sm text-gray-600">
                {NEXT_ACTION_LABELS[latestEvaluation.next_action] ??
                  latestEvaluation.next_action}
              </p>
            ) : null}
          </CardContent>
        </Card>
      ) : null}

      <Card>
        <CardHeader>
          <CardTitle className="text-lg">История</CardTitle>
        </CardHeader>
        <CardContent>
          {application.status === 'DRAFT' ? (
            <p className="mb-4 rounded-md bg-blue-50 p-3 text-sm text-blue-800">
              Заявка создана, но еще не подана. Подайте ее, чтобы нейросеть
              оценила ваш бизнес.
            </p>
          ) : null}

          {events.length === 0 ? (
            <p className="text-sm text-gray-500">История пока пуста.</p>
          ) : (
            <div className="relative">
              <div className="absolute bottom-0 left-4 top-0 w-px bg-gray-200" />
              {events.map((event) => {
                const { Icon, tone } = eventVisual(event)
                const fromLabel = event.from_status
                  ? formatStatus(event.from_status)
                  : 'Создана'
                const toLabel = formatStatus(event.to_status)
                return (
                  <div
                    key={event.id}
                    className="relative flex gap-4 pb-6 last:pb-0"
                  >
                    <div
                      className={`relative z-10 flex h-8 w-8 shrink-0 items-center justify-center rounded-full border-2 bg-white ${tone}`}
                    >
                      <Icon className="h-4 w-4" />
                    </div>
                    <div className="min-w-0 pt-0.5">
                      <p className="text-sm font-medium text-gray-900">
                        {fromLabel} → {toLabel}
                      </p>
                      <p className="text-sm text-gray-600">{toLabel}</p>
                      <p className="mt-1 text-xs text-gray-500">
                        {formatDate(event.created_at)}
                      </p>
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </CardContent>
      </Card>

      <div>
        {application.status === 'DRAFT' ? (
          <div className="flex flex-wrap gap-3">
            <Button type="button" onClick={() => setAction('submit')}>
              <Send />
              Подать заявку
            </Button>
            <Button
              type="button"
              variant="outline"
              onClick={() => setAction('withdraw')}
            >
              <Undo2 />
              Отозвать
            </Button>
          </div>
        ) : null}

        {application.status === 'NEEDS_INFO' ? (
          <div className="flex flex-wrap gap-3">
            <Button type="button" onClick={openEditDialog}>
              <Pencil />
              Дополнить данные
            </Button>
            <Button
              type="button"
              variant="outline"
              onClick={() => setAction('withdraw')}
            >
              <Undo2 />
              Отозвать
            </Button>
          </div>
        ) : null}

        {application.status === 'OFFER_MADE' ? (
          <div className="flex flex-wrap gap-3">
            <Button
              type="button"
              onClick={() => setAction('accept')}
              disabled={!latestOffer}
            >
              <CheckCircle2 />
              Принять предложение
            </Button>
            <Button
              type="button"
              variant="destructive"
              onClick={() => setAction('decline')}
              disabled={!latestOffer}
            >
              <XCircle />
              Отклонить
            </Button>
          </div>
        ) : null}

        {application.status === 'WITHDRAWN' ||
        application.status === 'CANCELLED' ? (
          <div className="rounded-lg border border-gray-200 bg-gray-100 p-4">
            <p className="text-sm text-gray-700">
              {application.status === 'WITHDRAWN'
                ? 'Заявка отозвана.'
                : 'Заявка отменена.'}
            </p>
          </div>
        ) : null}
      </div>

      <ConfirmDialog
        open={action !== null}
        onOpenChange={(open) => {
          if (!open) {
            setAction(null)
          }
        }}
        title={action ? actionCopy[action].title : ''}
        description={action ? actionCopy[action].description : ''}
        confirmLabel={action ? actionCopy[action].confirmLabel : 'Подтвердить'}
        destructive={action ? actionCopy[action].destructive : false}
        loading={actionLoading}
        onConfirm={() => void confirmAction()}
      />

      <Dialog
        open={editOpen}
        onOpenChange={(open) => {
          if (!editLoading) {
            setEditOpen(open)
          }
        }}
      >
        <DialogContent className="max-h-[90vh] overflow-y-auto">
          <form onSubmit={handleEditSubmit} noValidate>
            <DialogHeader>
              <DialogTitle>Дополнить данные</DialogTitle>
              <DialogDescription>
                Обновите параметры заявки и подайте её снова.
              </DialogDescription>
            </DialogHeader>

            <div className="space-y-4 py-4">
              <div className="space-y-2">
                <Label htmlFor="edit-amount">Сумма</Label>
                <div className="relative">
                  <Input
                    id="edit-amount"
                    type="text"
                    inputMode="numeric"
                    autoComplete="off"
                    maxLength={20}
                    placeholder="Например, 5 000 000"
                    value={editAmount}
                    aria-invalid={Boolean(editFieldErrors.amount)}
                    className={editFieldClass(
                      Boolean(editFieldErrors.amount),
                      true,
                    )}
                    onChange={(event) => {
                      setEditAmount(event.target.value)
                      clearEditFieldError('amount')
                    }}
                    required
                  />
                  <span className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-sm text-gray-500">
                    ₽
                  </span>
                </div>
                {editFieldErrors.amount ? (
                  <p className="text-xs text-red-600">
                    {editFieldErrors.amount}
                  </p>
                ) : (
                  <p className="text-xs text-gray-500">
                    До 1 000 000 000 ₽. Можно вводить с пробелами: 5 000 000.
                  </p>
                )}
              </div>
              <div className="space-y-2">
                <Label htmlFor="edit-term">Срок, месяцев</Label>
                <Input
                  id="edit-term"
                  type="number"
                  min="1"
                  max="120"
                  step="1"
                  placeholder="Например, 12"
                  value={editTerm}
                  aria-invalid={Boolean(editFieldErrors.term)}
                  className={editFieldClass(Boolean(editFieldErrors.term))}
                  onChange={(event) => {
                    setEditTerm(event.target.value)
                    clearEditFieldError('term')
                  }}
                  required
                />
                {editFieldErrors.term ? (
                  <p className="text-xs text-red-600">{editFieldErrors.term}</p>
                ) : (
                  <p className="text-xs text-gray-500">От 1 до 120 месяцев.</p>
                )}
              </div>
              <div className="space-y-2">
                <Label htmlFor="edit-age">Возраст бизнеса, месяцев</Label>
                <Input
                  id="edit-age"
                  type="number"
                  min="0"
                  max="1200"
                  step="1"
                  placeholder="Например, 36"
                  value={editAge}
                  aria-invalid={Boolean(editFieldErrors.age)}
                  className={editFieldClass(Boolean(editFieldErrors.age))}
                  onChange={(event) => {
                    setEditAge(event.target.value)
                    clearEditFieldError('age')
                  }}
                  required
                />
                {editFieldErrors.age ? (
                  <p className="text-xs text-red-600">{editFieldErrors.age}</p>
                ) : (
                  <p className="text-xs text-gray-500">
                    Полных месяцев с регистрации бизнеса.
                  </p>
                )}
              </div>
              <div className="space-y-2">
                <Label htmlFor="edit-revenue">Выручка в месяц</Label>
                <div className="relative">
                  <Input
                    id="edit-revenue"
                    type="text"
                    inputMode="decimal"
                    autoComplete="off"
                    maxLength={20}
                    placeholder="Например, 500 000"
                    value={editRevenue}
                    aria-invalid={Boolean(editFieldErrors.revenue)}
                    className={editFieldClass(
                      Boolean(editFieldErrors.revenue),
                      true,
                    )}
                    onChange={(event) => {
                      setEditRevenue(event.target.value)
                      clearEditFieldError('revenue')
                    }}
                  />
                  <span className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-sm text-gray-500">
                    ₽
                  </span>
                </div>
                {editFieldErrors.revenue ? (
                  <p className="text-xs text-red-600">
                    {editFieldErrors.revenue}
                  </p>
                ) : (
                  <p className="text-xs text-gray-500">
                    Необязательно. Средняя выручка за месяц.
                  </p>
                )}
              </div>
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                <div className="space-y-2">
                  <Label htmlFor="edit-cash">Доступно на долг в месяц</Label>
                  <div className="relative">
                    <Input
                      id="edit-cash"
                      type="text"
                      inputMode="decimal"
                      autoComplete="off"
                      maxLength={20}
                      placeholder="Например, 400 000"
                      value={editCash}
                      aria-invalid={Boolean(editFieldErrors.cash)}
                      className={editFieldClass(
                        Boolean(editFieldErrors.cash),
                        true,
                      )}
                      onChange={(event) => {
                        setEditCash(event.target.value)
                        clearEditFieldError('cash')
                      }}
                    />
                    <span className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-sm text-gray-500">
                      ₽
                    </span>
                  </div>
                  {editFieldErrors.cash ? (
                    <p className="text-xs text-red-600">
                      {editFieldErrors.cash}
                    </p>
                  ) : (
                    <p className="text-xs text-gray-500">
                      После расходов и налогов.
                    </p>
                  )}
                </div>
                <div className="space-y-2">
                  <Label htmlFor="edit-debt">Текущий долг в месяц</Label>
                  <div className="relative">
                    <Input
                      id="edit-debt"
                      type="text"
                      inputMode="decimal"
                      autoComplete="off"
                      maxLength={20}
                      placeholder="Например, 200 000"
                      value={editDebt}
                      aria-invalid={Boolean(editFieldErrors.debt)}
                      className={editFieldClass(
                        Boolean(editFieldErrors.debt),
                        true,
                      )}
                      onChange={(event) => {
                        setEditDebt(event.target.value)
                        clearEditFieldError('debt')
                      }}
                    />
                    <span className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-sm text-gray-500">
                      ₽
                    </span>
                  </div>
                  {editFieldErrors.debt ? (
                    <p className="text-xs text-red-600">
                      {editFieldErrors.debt}
                    </p>
                  ) : (
                    <p className="text-xs text-gray-500">
                      Платежи по действующим кредитам.
                    </p>
                  )}
                </div>
                <div className="space-y-2">
                  <Label htmlFor="edit-cv">Вариация выручки, 0–1</Label>
                  <Input
                    id="edit-cv"
                    type="number"
                    min="0"
                    max="1"
                    step="0.01"
                    placeholder="0.15"
                    value={editCv}
                    aria-invalid={Boolean(editFieldErrors.cv)}
                    className={editFieldClass(Boolean(editFieldErrors.cv))}
                    onChange={(event) => {
                      setEditCv(event.target.value)
                      clearEditFieldError('cv')
                    }}
                  />
                  {editFieldErrors.cv ? (
                    <p className="text-xs text-red-600">{editFieldErrors.cv}</p>
                  ) : (
                    <p className="text-xs text-gray-500">
                      Нестабильность выручки.
                    </p>
                  )}
                </div>
                <div className="space-y-2">
                  <Label htmlFor="edit-share">Доля клиента, 0–1</Label>
                  <Input
                    id="edit-share"
                    type="number"
                    min="0"
                    max="1"
                    step="0.01"
                    placeholder="0.25"
                    value={editShare}
                    aria-invalid={Boolean(editFieldErrors.share)}
                    className={editFieldClass(Boolean(editFieldErrors.share))}
                    onChange={(event) => {
                      setEditShare(event.target.value)
                      clearEditFieldError('share')
                    }}
                  />
                  {editFieldErrors.share ? (
                    <p className="text-xs text-red-600">
                      {editFieldErrors.share}
                    </p>
                  ) : (
                    <p className="text-xs text-gray-500">
                      Концентрация на одном клиенте.
                    </p>
                  )}
                </div>
              </div>
              <div className="space-y-2">
                <Label htmlFor="edit-purpose">Цель</Label>
                <textarea
                  id="edit-purpose"
                  className="min-h-20 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background transition-colors duration-150 placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:ring-offset-2"
                  placeholder="Например, закупка оборудования"
                  value={editPurpose}
                  onChange={(event) => setEditPurpose(event.target.value)}
                />
                <p className="text-xs text-gray-500">
                  Необязательно. Кратко опишите цель.
                </p>
              </div>
              <div className="space-y-2">
                <label className="flex items-start gap-3 rounded-md border border-gray-200 bg-gray-50 p-3">
                  <input
                    type="checkbox"
                    className="mt-0.5 h-4 w-4 rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"
                    checked={editConsent}
                    onChange={(event) => {
                      setEditConsent(event.target.checked)
                      clearEditFieldError('consent')
                    }}
                  />
                  <span className="text-sm text-gray-700">
                    Согласен на проверку кредитной истории
                  </span>
                </label>
                {editFieldErrors.consent ? (
                  <p className="text-xs text-red-600">
                    {editFieldErrors.consent}
                  </p>
                ) : null}
              </div>
              {editError ? (
                <p className="text-sm text-red-600" role="alert">
                  {editError}
                </p>
              ) : null}
            </div>

            <DialogFooter className="gap-2">
              <Button
                type="button"
                variant="secondary"
                onClick={() => setEditOpen(false)}
                disabled={editLoading}
              >
                Отмена
              </Button>
              <Button type="submit" disabled={editLoading}>
                {editLoading ? <Loader2 className="animate-spin" /> : null}
                {editLoading ? 'Сохранение...' : 'Сохранить и подать'}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  )
}
