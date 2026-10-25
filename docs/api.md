# API

Base URL локально: `http://localhost:8000`

Swagger UI: `/docs`  
OpenAPI JSON: `docs/openapi.json`

## Envelope

Успех:

```json
{"data": {}}
```

Ошибка:

```json
{"error": {"code": "not_found", "message": "resource not found"}}
```

## Auth

Защищённые endpoints требуют:

```http
Authorization: Bearer <access_token>
```

Токен выдаётся на 24 часа.

## Endpoints

### POST `/api/auth/login`

```json
{
  "email": "client@demo.ru",
  "password": "password123"
}
```

Ответ:

```json
{"data": {"access_token": "<jwt>"}}
```

### GET `/api/applications`

Список заявок текущего пользователя.

### POST `/api/applications`

```json
{
  "product_id": 1,
  "data": {
    "amount": 1000000,
    "term_months": 24,
    "company_age_months": 36,
    "monthly_revenue": 1500000,
    "monthly_cash_available_for_debt_service_rub": 400000,
    "revenue_cv_12m": 0.15,
    "largest_customer_share": 0.25,
    "credit_report_consent_valid": true,
    "purpose": "Пополнение оборотных средств"
  }
}
```

### GET `/api/applications/{id}`

Карточка заявки: текущая revision, offers, evaluations, events.

### PATCH `/api/applications/{id}`

```json
{
  "expected_revision": 1,
  "data": {
    "amount": 1000000,
    "term_months": 24,
    "company_age_months": 36,
    "monthly_revenue": 1500000,
    "credit_report_consent_valid": true
  }
}
```

### POST `/api/applications/{id}/submit`

Запускает FSM и credit engine. Требует `Idempotency-Key`.

### POST `/api/applications/{id}/offers/{offer_id}/accept`

Принимает оффер. Требует `Idempotency-Key`.

### POST `/api/applications/{id}/offers/{offer_id}/decline`

Отклоняет оффер. Требует `Idempotency-Key`.

### POST `/api/applications/{id}/withdraw`

Отзывает заявку. Frontend отправляет `Idempotency-Key`.

### GET `/health`

Liveness.

### GET `/readyz`

Readiness + доступность SQLite.

## Idempotency

Повторный запрос с тем же `Idempotency-Key` возвращает сохранённый ответ.

Если ключ уже есть, но request hash другой:

```text
409 conflict
```

## Основные ошибки

- `400 bad_request` — невалидный запрос.
- `401 unauthorized` — нет/просрочен токен.
- `403 forbidden` — чужая заявка.
- `404 not_found` — заявка/оффер не найдены.
- `409 conflict` — недопустимый переход FSM.
- `422 invalid_application_data` — engine отклонил payload.
- `503 engine_unavailable` — engine недоступен.
