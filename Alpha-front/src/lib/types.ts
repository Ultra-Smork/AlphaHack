export type ProductId = 1 | 2

export type ApplicationStatus =
  | 'DRAFT'
  | 'SUBMITTED'
  | 'INTAKE_CHECK'
  | 'NEEDS_INFO'
  | 'ENRICHMENT'
  | 'SCORING'
  | 'OFFER_MADE'
  | 'OFFER_ACCEPTED'
  | 'REJECTED'
  | 'CANCELLED'
  | 'WITHDRAWN'
  | 'OFFER_DECLINED'
  | 'OFFER_EXPIRED'

export interface User {
  id: number
  email: string
}

export interface JwtPayload {
  sub?: string
  uid?: string
  exp?: number
  iat?: number
}

export interface LoginResponse {
  access_token: string
  user_id?: number
  email?: string
}

export interface ApiEnvelope<T> {
  data: T
}

export interface ApiErrorBody {
  error: {
    code: string
    message: string
  }
}

export interface QuestionnaireData {
  amount: number
  term_months: number
  company_age_months: number
  monthly_revenue?: number | null
  monthly_cash_available_for_debt_service_rub?: number | null
  revenue_cv_12m?: number | null
  largest_customer_share?: number | null
  credit_report_consent_valid?: boolean
  purpose?: string | null
  has_collateral?: boolean
  existing_debt?: number
}

export interface ApplicationRevision {
  id: number
  application_id: number
  version: number
  data: QuestionnaireData
  created_at: string
}

export interface Offer {
  id: number
  application_id: number
  evaluation_id: number | null
  amount: number
  term: number
  rate: number
  payment: number
  dscr: number | null
  expires_at: string | null
  status: string
}

export interface ReasonCode {
  code: string
  text: string
  details?: {
    title?: string
    current?: string
    limit?: string
    action?: string
  } | null
}

export interface RiskFactor {
  code: string
  points: number
}

export interface Evaluation {
  id: number
  decision: string
  risk_score: number
  risk_category: string | null
  reason_codes: Array<ReasonCode | string>
  risk_details?: {
    factors?: RiskFactor[]
    calibrated_pd?: number | null
    next_action?: string
  } | null
  missing_fields?: string[]
  next_action?: string | null
  engine_version: string
  policy_version: string
}

export interface ApplicationEvent {
  id: number
  application_id: number
  event_type: string
  from_status: ApplicationStatus | null
  to_status: ApplicationStatus
  actor_id: number | null
  payload: Record<string, unknown>
  created_at: string
}

export interface Application {
  id: number
  company_id: number
  product_id: ProductId
  status: ApplicationStatus
  current_revision_id: number | null
  created_at: string
  current_revision?: ApplicationRevision | null
  offers?: Offer[]
  evaluations?: Evaluation[]
  events?: ApplicationEvent[]
}

export type ApplicationSummary = Application

export interface ApplicationDetail extends Application {
  current_revision: ApplicationRevision | null
  offers: Offer[]
  evaluations: Evaluation[]
  events: ApplicationEvent[]
}

export interface CreateApplicationInput {
  product_id?: ProductId
  data: QuestionnaireData
}

export interface UpdateApplicationInput {
  expected_revision: number
  data: QuestionnaireData
}
