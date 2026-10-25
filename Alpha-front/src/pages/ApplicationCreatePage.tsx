import { useState } from 'react'
import type { FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { ChevronDown, ChevronUp, Info, Loader2 } from 'lucide-react'

import { Button } from '@/components/ui/button'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { toast } from '@/hooks/use-toast'
import { api, getApiErrorMessage } from '@/lib/api'
import { parseNumericInput } from '@/lib/numberInput'
import { cn } from '@/lib/utils'
import type {
  ApplicationDetail,
  CreateApplicationInput,
  ProductId,
} from '@/lib/types'

type FieldErrors = Partial<
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

const MAX_AMOUNT = 1_000_000_000
const MAX_TERM_MONTHS = 120
const MAX_COMPANY_AGE_MONTHS = 1200

function fieldClass(hasError: boolean, withSuffix = false) {
  return cn(
    withSuffix ? 'pr-9' : '',
    hasError && 'border-red-500 focus-visible:ring-red-500',
  )
}

export function ApplicationCreatePage() {
  const navigate = useNavigate()
  const [productId, setProductId] = useState<ProductId>(1)
  const [amount, setAmount] = useState('')
  const [termMonths, setTermMonths] = useState('')
  const [companyAgeMonths, setCompanyAgeMonths] = useState('')
  const [monthlyRevenue, setMonthlyRevenue] = useState('')
  const [monthlyCash, setMonthlyCash] = useState('')
  const [existingDebt, setExistingDebt] = useState('')
  const [revenueCv, setRevenueCv] = useState('')
  const [customerShare, setCustomerShare] = useState('')
  const [consent, setConsent] = useState(false)
  const [extraOpen, setExtraOpen] = useState(false)
  const [purpose, setPurpose] = useState('')
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({})
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  function clearFieldError(field: keyof FieldErrors) {
    setFieldErrors((current) => {
      if (!current[field]) {
        return current
      }
      const next = { ...current }
      delete next[field]
      return next
    })
  }

  function validate(): FieldErrors {
    const next: FieldErrors = {}
    const parsedAmount = parseNumericInput(amount)
    const parsedTerm = Number(termMonths)
    const parsedAge = Number(companyAgeMonths)
    const parsedRevenue = parseNumericInput(monthlyRevenue)
    const parsedCash = parseNumericInput(monthlyCash)
    const parsedDebt = parseNumericInput(existingDebt)
    const parsedCv = revenueCv ? Number(revenueCv) : null
    const parsedShare = customerShare ? Number(customerShare) : null

    if (
      parsedAmount === null ||
      !Number.isInteger(parsedAmount) ||
      parsedAmount < 1 ||
      parsedAmount > MAX_AMOUNT
    ) {
      next.amount = 'Сумма должна быть целым числом от 1 до 1 000 000 000 ₽'
    }
    if (
      !Number.isFinite(parsedTerm) ||
      !Number.isInteger(parsedTerm) ||
      parsedTerm < 1 ||
      parsedTerm > MAX_TERM_MONTHS
    ) {
      next.term = 'Срок должен быть целым числом от 1 до 120 месяцев'
    }
    if (
      companyAgeMonths.trim() === '' ||
      !Number.isFinite(parsedAge) ||
      !Number.isInteger(parsedAge) ||
      parsedAge < 0 ||
      parsedAge > MAX_COMPANY_AGE_MONTHS
    ) {
      next.age = 'Возраст бизнеса должен быть целым числом от 0 до 1200 месяцев'
    }
    if (monthlyRevenue.trim() !== '' && parsedRevenue === null) {
      next.revenue = 'Выручка должна быть неотрицательным числом'
    }
    if (monthlyCash.trim() !== '' && parsedCash === null) {
      next.cash = 'Укажите корректную сумму'
    }
    if (existingDebt.trim() !== '' && parsedDebt === null) {
      next.debt = 'Долговая нагрузка должна быть неотрицательным числом'
    }
    if (
      parsedCv !== null &&
      (!Number.isFinite(parsedCv) || parsedCv < 0 || parsedCv > 1)
    ) {
      next.cv = 'Укажите значение от 0 до 1'
    }
    if (
      parsedShare !== null &&
      (!Number.isFinite(parsedShare) || parsedShare < 0 || parsedShare > 1)
    ) {
      next.share = 'Укажите значение от 0 до 1'
    }
    if (!consent) {
      next.consent = 'Требуется согласие'
    }
    return next
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError(null)

    const nextErrors = validate()
    setFieldErrors(nextErrors)
    if (Object.keys(nextErrors).length > 0) {
      return
    }

    const amountValue = parseNumericInput(amount)
    const revenueValue = parseNumericInput(monthlyRevenue)
    const cashValue = parseNumericInput(monthlyCash)
    const debtValue = parseNumericInput(existingDebt)
    const parsedCv = revenueCv ? Number(revenueCv) : null
    const parsedShare = customerShare ? Number(customerShare) : null

    if (amountValue === null) {
      return
    }

    const payload: CreateApplicationInput = {
      product_id: productId,
      data: {
        amount: amountValue,
        term_months: Number(termMonths),
        company_age_months: Number(companyAgeMonths),
        credit_report_consent_valid: consent,
        ...(revenueValue !== null ? { monthly_revenue: revenueValue } : {}),
        ...(cashValue !== null
          ? { monthly_cash_available_for_debt_service_rub: cashValue }
          : {}),
        ...(debtValue !== null ? { existing_debt: debtValue } : {}),
        ...(parsedCv !== null ? { revenue_cv_12m: parsedCv } : {}),
        ...(parsedShare !== null
          ? { largest_customer_share: parsedShare }
          : {}),
        ...(purpose.trim() ? { purpose: purpose.trim() } : {}),
      },
    }

    setLoading(true)
    try {
      const response = await api.post<ApplicationDetail>(
        '/api/applications',
        payload,
      )
      toast.success('Черновик создан')
      navigate(`/applications/${response.data.id}`, { replace: true })
    } catch (cause) {
      const message = getApiErrorMessage(cause, 'Не удалось создать заявку')
      setError(message)
      toast.error(message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="mx-auto max-w-2xl space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Новая заявка</h1>
        <p className="mt-1 text-sm text-gray-600">
          Заполните данные, чтобы нейросеть оценила ваш бизнес.
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-lg">Параметры заявки</CardTitle>
          <CardDescription>
            Черновик можно изменить перед подачей.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form className="space-y-5" onSubmit={handleSubmit} noValidate>
            <div className="space-y-2">
              <Label htmlFor="product">Продукт</Label>
              <select
                id="product"
                className="h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm transition-colors duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:ring-offset-2"
                value={productId}
                onChange={(event) => {
                  setProductId(Number(event.target.value) as ProductId)
                  setFieldErrors({})
                }}
              >
                <option value={1}>Оборотные средства</option>
                <option value={2}>Оборудование</option>
              </select>
              <p className="text-xs text-gray-500">
                Выберите продукт. Итоговые параметры определит оценка заявки.
              </p>
            </div>

            <div className="space-y-2">
              <Label htmlFor="amount">Сумма</Label>
              <div className="relative">
                <Input
                  id="amount"
                  type="text"
                  inputMode="numeric"
                  autoComplete="off"
                  maxLength={20}
                  placeholder="Например, 5 000 000"
                  value={amount}
                  aria-invalid={Boolean(fieldErrors.amount)}
                  className={fieldClass(Boolean(fieldErrors.amount), true)}
                  onChange={(event) => {
                    setAmount(event.target.value)
                    clearFieldError('amount')
                  }}
                  required
                />
                <span className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-sm text-gray-500">
                  ₽
                </span>
              </div>
              {fieldErrors.amount ? (
                <p className="text-xs text-red-600">{fieldErrors.amount}</p>
              ) : (
                <p className="text-xs text-gray-500">
                  Сумма кредита в рублях. До 1 000 000 000 ₽. Можно вводить с
                  пробелами: 5 000 000.
                </p>
              )}
            </div>

            <div className="space-y-2">
              <Label htmlFor="term">Срок, месяцев</Label>
              <Input
                id="term"
                type="number"
                min="1"
                max={MAX_TERM_MONTHS}
                step="1"
                placeholder="Например, 12"
                value={termMonths}
                aria-invalid={Boolean(fieldErrors.term)}
                className={fieldClass(Boolean(fieldErrors.term))}
                onChange={(event) => {
                  setTermMonths(event.target.value)
                  clearFieldError('term')
                }}
                required
              />
              {fieldErrors.term ? (
                <p className="text-xs text-red-600">{fieldErrors.term}</p>
              ) : (
                <p className="text-xs text-gray-500">
                  От 1 до 120 месяцев.
                </p>
              )}
            </div>

            <div className="space-y-2">
              <Label htmlFor="age">Возраст бизнеса, месяцев</Label>
              <Input
                id="age"
                type="number"
                min="0"
                max={MAX_COMPANY_AGE_MONTHS}
                step="1"
                placeholder="Например, 36"
                value={companyAgeMonths}
                aria-invalid={Boolean(fieldErrors.age)}
                className={fieldClass(Boolean(fieldErrors.age))}
                onChange={(event) => {
                  setCompanyAgeMonths(event.target.value)
                  clearFieldError('age')
                }}
                required
              />
              {fieldErrors.age ? (
                <p className="text-xs text-red-600">{fieldErrors.age}</p>
              ) : (
                <p className="text-xs text-gray-500">
                  Полных месяцев с регистрации бизнеса.
                </p>
              )}
            </div>

            <div className="space-y-2">
              <Label htmlFor="revenue">Выручка в месяц</Label>
              <div className="relative">
                <Input
                  id="revenue"
                  type="text"
                  inputMode="decimal"
                  autoComplete="off"
                  maxLength={20}
                  placeholder="Например, 500 000"
                  value={monthlyRevenue}
                  aria-invalid={Boolean(fieldErrors.revenue)}
                  className={fieldClass(Boolean(fieldErrors.revenue), true)}
                  onChange={(event) => {
                    setMonthlyRevenue(event.target.value)
                    clearFieldError('revenue')
                  }}
                />
                <span className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-sm text-gray-500">
                  ₽
                </span>
              </div>
              {fieldErrors.revenue ? (
                <p className="text-xs text-red-600">{fieldErrors.revenue}</p>
              ) : (
                <p className="text-xs text-gray-500">
                  Необязательно. Средняя выручка за месяц.
                </p>
              )}
            </div>

            <div className="space-y-2">
              <Label htmlFor="purpose">Цель</Label>
              <textarea
                id="purpose"
                className="min-h-24 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background transition-colors duration-150 placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:ring-offset-2"
                placeholder="Например, закупка оборудования"
                value={purpose}
                onChange={(event) => setPurpose(event.target.value)}
              />
              <p className="text-xs text-gray-500">
                Необязательно. Кратко опишите цель.
              </p>
            </div>

            <div className="flex gap-3 rounded-md border border-gray-200 bg-gray-50 p-3 text-sm text-gray-600">
              <Info className="mt-0.5 h-4 w-4 shrink-0" />
              <p>
                Автоматические проверки (реестр, кредитная история, антифрод)
                выполняются нашей системой. Вы заполняете только финансовые
                показатели.
              </p>
            </div>

            <div className="space-y-3">
              <button
                type="button"
                className="flex w-full items-center justify-between rounded-md border border-gray-200 bg-white px-3 py-2 text-sm font-medium text-gray-800 transition-colors duration-150 hover:bg-gray-50"
                aria-expanded={extraOpen}
                onClick={() => setExtraOpen((value) => !value)}
              >
                <span>Дополнительные сведения</span>
                {extraOpen ? (
                  <ChevronUp className="h-4 w-4" />
                ) : (
                  <ChevronDown className="h-4 w-4" />
                )}
              </button>

              {extraOpen ? (
                <div className="space-y-4 rounded-md border border-gray-200 bg-white p-4">
                  <div className="space-y-2">
                    <Label htmlFor="cash">
                      Доступно на обслуживание долга в месяц
                    </Label>
                    <div className="relative">
                      <Input
                        id="cash"
                        type="text"
                        inputMode="decimal"
                        autoComplete="off"
                        maxLength={20}
                        placeholder="Например, 400 000"
                        value={monthlyCash}
                        aria-invalid={Boolean(fieldErrors.cash)}
                        className={fieldClass(Boolean(fieldErrors.cash), true)}
                        onChange={(event) => {
                          setMonthlyCash(event.target.value)
                          clearFieldError('cash')
                        }}
                      />
                      <span className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-sm text-gray-500">
                        ₽
                      </span>
                    </div>
                    {fieldErrors.cash ? (
                      <p className="text-xs text-red-600">{fieldErrors.cash}</p>
                    ) : (
                      <p className="text-xs text-gray-500">
                        После операционных расходов и налогов. Если не знаете —
                        оставьте пустым, мы оценим по выручке.
                      </p>
                    )}
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="debt">
                      Текущая долговая нагрузка в месяц
                    </Label>
                    <div className="relative">
                      <Input
                        id="debt"
                        type="text"
                        inputMode="decimal"
                        autoComplete="off"
                        maxLength={20}
                        placeholder="Например, 200 000"
                        value={existingDebt}
                        aria-invalid={Boolean(fieldErrors.debt)}
                        className={fieldClass(Boolean(fieldErrors.debt), true)}
                        onChange={(event) => {
                          setExistingDebt(event.target.value)
                          clearFieldError('debt')
                        }}
                      />
                      <span className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-sm text-gray-500">
                        ₽
                      </span>
                    </div>
                    {fieldErrors.debt ? (
                      <p className="text-xs text-red-600">{fieldErrors.debt}</p>
                    ) : (
                      <p className="text-xs text-gray-500">
                        Платежи по действующим кредитам. Если их нет — оставьте
                        пустым или укажите 0.
                      </p>
                    )}
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="cv">Вариация выручки, 0–1</Label>
                    <Input
                      id="cv"
                      type="number"
                      min="0"
                      max="1"
                      step="0.01"
                      placeholder="0.15 (15%)"
                      value={revenueCv}
                      aria-invalid={Boolean(fieldErrors.cv)}
                      className={fieldClass(Boolean(fieldErrors.cv))}
                      onChange={(event) => {
                        setRevenueCv(event.target.value)
                        clearFieldError('cv')
                      }}
                    />
                    {fieldErrors.cv ? (
                      <p className="text-xs text-red-600">{fieldErrors.cv}</p>
                    ) : (
                      <p className="text-xs text-gray-500">
                        Необязательно. Насколько нестабильна выручка.
                      </p>
                    )}
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="share">Доля крупнейшего клиента, 0–1</Label>
                    <Input
                      id="share"
                      type="number"
                      min="0"
                      max="1"
                      step="0.01"
                      placeholder="0.25 (25%)"
                      value={customerShare}
                      aria-invalid={Boolean(fieldErrors.share)}
                      className={fieldClass(Boolean(fieldErrors.share))}
                      onChange={(event) => {
                        setCustomerShare(event.target.value)
                        clearFieldError('share')
                      }}
                    />
                    {fieldErrors.share ? (
                      <p className="text-xs text-red-600">{fieldErrors.share}</p>
                    ) : (
                      <p className="text-xs text-gray-500">
                        Необязательно. Концентрация выручки на одном клиенте.
                      </p>
                    )}
                  </div>
                </div>
              ) : null}
            </div>

            <div className="space-y-2">
              <label className="flex items-start gap-3 rounded-md border border-gray-200 bg-white p-3">
                <input
                  type="checkbox"
                  className="mt-0.5 h-4 w-4 rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"
                  checked={consent}
                  onChange={(event) => {
                    setConsent(event.target.checked)
                    clearFieldError('consent')
                  }}
                />
                <span className="text-sm text-gray-700">
                  Согласен на проверку кредитной истории
                </span>
              </label>
              {fieldErrors.consent ? (
                <p className="text-xs text-red-600">{fieldErrors.consent}</p>
              ) : null}
            </div>

            {error ? (
              <p className="text-sm text-red-600" role="alert">
                {error}
              </p>
            ) : null}

            <div className="flex flex-col gap-3 pt-1 sm:flex-row">
              <Button
                type="submit"
                className="min-h-[44px] w-full sm:w-auto"
                disabled={loading}
              >
                {loading ? <Loader2 className="animate-spin" /> : null}
                Создать черновик
              </Button>
              <Button
                type="button"
                variant="secondary"
                className="min-h-[44px] w-full sm:ml-2 sm:w-auto"
                onClick={() => navigate('/applications')}
                disabled={loading}
              >
                Отмена
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>
    </div>
  )
}
