# FSM заявки

```mermaid
stateDiagram-v2
    [*] --> DRAFT

    DRAFT --> SUBMITTED: submit
    DRAFT --> WITHDRAWN: withdraw

    SUBMITTED --> INTAKE_CHECK
    SUBMITTED --> WITHDRAWN

    INTAKE_CHECK --> ENRICHMENT
    INTAKE_CHECK --> NEEDS_INFO
    INTAKE_CHECK --> REJECTED
    INTAKE_CHECK --> WITHDRAWN

    NEEDS_INFO --> SUBMITTED: backend allows
    NEEDS_INFO --> WITHDRAWN

    ENRICHMENT --> SCORING
    ENRICHMENT --> NEEDS_INFO
    ENRICHMENT --> REJECTED
    ENRICHMENT --> WITHDRAWN

    SCORING --> OFFER_MADE
    SCORING --> NEEDS_INFO
    SCORING --> REJECTED
    SCORING --> WITHDRAWN

    OFFER_MADE --> OFFER_ACCEPTED: accept
    OFFER_MADE --> OFFER_DECLINED: decline
    OFFER_MADE --> OFFER_EXPIRED
    OFFER_MADE --> WITHDRAWN

    OFFER_ACCEPTED --> WITHDRAWN

    REJECTED --> [*]
    WITHDRAWN --> [*]
    OFFER_DECLINED --> [*]
    OFFER_EXPIRED --> [*]
    CANCELLED --> [*]
```

## Правила

- `OFFER_ACCEPTED` — финальный статус, кроме `WITHDRAWN`.
- `REJECTED`, `WITHDRAWN`, `OFFER_DECLINED`, `OFFER_EXPIRED`, `CANCELLED` — терминальные.
- `MANUAL_REVIEW`, `SIGNING`, `SIGNED`, `DISBURSING`, `DISBURSED` не используются.
- `NEEDS_INFO -> SUBMITTED` разрешён backend, но кнопка «Подать снова» убрана из UI.
- Каждый переход создаёт `ApplicationEvent`.
- Уведомление отправляется после commit.

## Статусы

```text
DRAFT
SUBMITTED
INTAKE_CHECK
NEEDS_INFO
ENRICHMENT
SCORING
OFFER_MADE
OFFER_ACCEPTED
REJECTED
CANCELLED
WITHDRAWN
OFFER_DECLINED
OFFER_EXPIRED
```
