# Модель данных

SQLite, SQLAlchemy, 12 таблиц.

```mermaid
erDiagram
    COMPANIES ||--o{ COMPANY_MEMBERSHIPS : has
    USERS ||--o{ COMPANY_MEMBERSHIPS : belongs
    COMPANIES ||--o{ APPLICATIONS : owns

    APPLICATIONS ||--o{ APPLICATION_REVISIONS : revisions
    APPLICATIONS ||--o{ DOCUMENTS : documents
    APPLICATIONS ||--o{ CONSENTS : consents
    APPLICATIONS ||--o{ CHECK_RESULTS : checks
    APPLICATIONS ||--o{ EVALUATIONS : evaluations
    APPLICATIONS ||--o{ OFFERS : offers
    APPLICATIONS ||--o{ APPLICATION_EVENTS : events
    APPLICATION_REVISIONS ||--o{ EVALUATIONS : evaluated_from
    EVALUATIONS ||--o{ OFFERS : produces

    COMPANIES {
        int id PK
        string inn
        string type
        string name
        datetime created_at
    }

    USERS {
        int id PK
        string email
        string password_hash
        string full_name
        datetime created_at
    }

    COMPANY_MEMBERSHIPS {
        int id PK
        int user_id FK
        int company_id FK
        json permissions
        bool is_confirmed
    }

    APPLICATIONS {
        int id PK
        int company_id FK
        int product_id
        string status
        int current_revision_id
        datetime created_at
    }

    APPLICATION_REVISIONS {
        int id PK
        int application_id FK
        int version
        json data
        datetime created_at
    }

    DOCUMENTS {
        int id PK
        int application_id FK
        string doc_type
        string url
        string status
    }

    CONSENTS {
        int id PK
        int application_id FK
        int user_id FK
        string type
        string status
        datetime expires_at
    }

    CHECK_RESULTS {
        int id PK
        int application_id FK
        string check_type
        string status
        string source
        string fixture_id
        datetime checked_at
    }

    EVALUATIONS {
        int id PK
        int application_id FK
        int revision_id FK
        string decision
        float risk_score
        string risk_category
        json offer_data
        json reason_codes
        json risk_details
        json missing_fields
        string next_action
        string engine_version
        string policy_version
        datetime created_at
    }

    OFFERS {
        int id PK
        int application_id FK
        int evaluation_id FK
        float amount
        int term
        float rate
        float payment
        datetime expires_at
        string status
    }

    APPLICATION_EVENTS {
        int id PK
        int application_id FK
        string event_type
        string from_status
        string to_status
        int actor_id FK
        json payload
        datetime created_at
    }

    IDEMPOTENCY_KEYS {
        int id PK
        string key
        string request_hash
        json response_body
        datetime created_at
    }
```

## Замечания

- `applications.current_revision_id` — логическая ссылка на `application_revisions.id`, не FK.
- `offers.evaluation_id` может быть `NULL`.
- `reason_codes` хранит массив объектов `{code,text,details}`.
- `risk_details` хранит `factors`, `calibrated_pd`, `next_action`.
- `idempotency_keys` не связана FK с заявкой: ключ глобальный.
