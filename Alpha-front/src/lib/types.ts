export type UserRole = 'client' | 'bank'

export type ProductId = 1 | 2

export type ApplicationStatus =
  | 'DRAFT'
  | 'SUBMITTED'
  | 'INTAKE_CHECK'
  | 'NEEDS_INFO'
  | 'ENRICHMENT'
  | 'SCORING'
  | 'MANUAL_REVIEW'
  | 'OFFER_MADE'
  | 'OFFER_ACCEPTED'
  | 'SIGNING'
  | 'SIGNED'
  | 'DISBURSING'
  | 'DISBURSEMENT_FAILED'
  | 'REJECTED'
  | 'CANCELLED'
  | 'WITHDRAWN'
  | 'OFFER_DECLINED'
  | 'OFFER_EXPIRED'
  | 'DISBURSED'

export type ReviewDecision = 'APPROVE' | 'REJECT' | 'NEED_INFO'

export interface User {
  id: number
  email: string
  role: UserRole
}

export interface JwtPayload {
  sub?: string
  uid?: string
  role?: UserRole
  exp?: number
  iat?: number
}

export interface LoginResponse {
  access_token: string
  role?: UserRole
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
  expires_at: string | null
  status: string
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
}

export interface ApplicationSummary extends Application {
  amount: number | null
  term_months: number | null
}

export interface ApplicationDetail extends Application {
  revision: ApplicationRevision | null
  offer: Offer | null
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

export interface AcceptOfferResponse {
  status: ApplicationStatus
  offer: Offer
}

export interface Contract {
  id: number
  application_id: number
  offer_id: number
  status: string
  signed_at: string | null
}

export interface Disbursement {
  id: number
  application_id: number
  status: string
  amount: number
  created_at: string
}

export interface SignResponse {
  status: ApplicationStatus
  contract: Contract
  disbursement: Disbursement
}

export interface WithdrawResponse {
  id: number
  status: ApplicationStatus
}

export interface BankQueueItem {
  id: number
  company_id: number
  company_name: string
  product_id: ProductId
  status: ApplicationStatus
  amount: number | null
  term_months: number | null
  company_age_months: number | null
  created_at: string
}

export interface ReviewInput {
  decision: ReviewDecision
  reason?: string | null
}

export interface ReviewResponse {
  application_id: number
  status: ApplicationStatus
  manual_review_id: number
  offer: Offer | null
}
