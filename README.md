# Суирники3

B2C-кредитный симулятор для предпринимателей: заявка, оценка локального credit engine и финальное решение — оффер, отказ или запрос данных.

Ручного рассмотрения, подписания договора и выдачи денег нет.

[Видео-демо: TODO — вставить ссылку]

## Скриншоты

TODO: добавить 2–3 изображения.

- `TODO: скриншот списка заявок`
- `TODO: скриншот карточки заявки с оффером`
- `TODO: скриншот формы создания`

## Проверка за 30 секунд

```bash
docker compose up --build
```

Открыть http://localhost:8000

```text
client@demo.ru / password123
```

## Соответствие ТЗ

| Требование | Статус | Где реализовано |
|---|---|---|
| B2C без банков и ручного review | ✅ | `ApplicationStatus`, `credit_engine` с `staff_review=False` |
| Email + JWT auth | ✅ | `/api/auth/login`, `AuthContext` |
| FSM из 13 статусов | ✅ | `app/services/application_service.py` |
| Локальный credit engine | ✅ | `app/platform/ai/credit_engine.py` |
| 2 кредитных продукта | ✅ | `working_capital`, `equipment` |
| Product-политика и лимиты | ✅ | `POLICY` внутри engine |
| Оффер: accept / decline / withdraw | ✅ | `/accept`, `/decline`, `/withdraw` |
| Объяснение отказа и лимитов | ✅ | `reason_codes.details`, UI-плашки |
| Risk score и факторы | ✅ | `Evaluation.risk_score`, `risk_details` |
| 4 демо-заявки | ✅ | `app/platform/seed.py` |
| Docker one-container | ✅ | `Dockerfile`, `docker-compose.yml` |
| 19 backend-тестов | ✅ | `pytest` |
| Идемпотентность | ✅ частично | submit / accept / decline |
| Реальные ЕГРЮЛ / БКИ / антифрод | ❌ | checks замоканы в `CreditEngineClient` |
| Подписание и выдача денег | ❌ | не входят в MVP |

## Что реализовано в MVP

- ✅ Регистрация/вход по email и паролю.
- ✅ JWT на 24 часа.
- ✅ Создание, редактирование и подача заявки.
- ✅ FSM: `DRAFT` -> `SUBMITTED` -> `INTAKE_CHECK` -> `ENRICHMENT` -> `SCORING`.
- ✅ Локальный credit engine без HTTP-сервиса.
- ✅ `APPROVED`, `COUNTEROFFER`, `NEED_INFO`, `DECLINED`.
- ✅ Оффер с суммой, сроком, ставкой, платежом и DSCR.
- ✅ Принятие и отклонение оффера.
- ✅ Отзыв заявки.
- ✅ Объяснение причин отказа и изменения условий.
- ✅ Risk score 0..100, LOW/MEDIUM/HIGH.
- ✅ 4 demo-заявки разных статусов.
- ✅ Docker: frontend + backend в одном контейнере.
- ❌ Manual review.
- ❌ Подписание договора.
- ❌ Выдача денег.
- ❌ Реальные внешние проверки.

## Как это работает

```text
DRAFT
  -> SUBMITTED
  -> INTAKE_CHECK
  -> ENRICHMENT
  -> SCORING
  -> OFFER_MADE | NEEDS_INFO | REJECTED
  -> OFFER_ACCEPTED | OFFER_DECLINED | OFFER_EXPIRED
```

`SCORING` вызывает локальный `credit_engine`:

- `APPROVED` -> `OFFER_MADE`;
- `COUNTEROFFER` -> `OFFER_MADE` с изменёнными условиями;
- `NEED_INFO` -> `NEEDS_INFO`;
- `DECLINED` -> `REJECTED`.

`MANUAL_REVIEW` при `staff_review=False` не используется. Если движок всё же вернёт его, backend логирует ошибку и безопасно переводит заявку в `REJECTED`.

### Продукты

| ID | Продукт | Сумма | Срок | Возраст бизнеса | Margin |
|---|---|---|---|---|---|
| 1 | Оборотные средства | 100 000–3 000 000 ₽ | 6–24 мес | от 12 мес | +4 п.п. |
| 2 | Оборудование | 300 000–5 000 000 ₽ | 12–36 мес | от 24 мес | +2 п.п. |

UI не блокирует нестандартные значения. Engine — источник истины: он делает counteroffer или decline.

### Risk score

`risk score` — это балл 0..100, а не вероятность одобрения.

- 75–100 — низкий риск;
- 50–74 — средний риск;
- 0–49 — высокий риск;
- выше — лучше.

`calibrated_pd` всегда `null`: модель не обучена на реальных исходах.

## Стек

- Backend: FastAPI, SQLAlchemy, SQLite, Pydantic v2, PyJWT.
- Frontend: React 19, TypeScript, Vite, Tailwind CSS v3, shadcn/ui, axios.
- Credit engine: локальный Python-модуль.
- Docker: Python 3.12 + собранный frontend в одном образе.

## Запуск локально

```bash
make install
make dev
```

- Frontend: http://localhost:5173
- Backend: http://localhost:8000
- Swagger: http://localhost:8000/docs

Проверка:

```bash
make check
```

Сброс локальной БД:

```bash
make reset-db
```

## Docker

```bash
docker compose up --build
```

Приложение: http://localhost:8000

Сброс Docker-БД:

```bash
docker compose down -v
docker compose up --build
```

SQLite хранится в volume `sqlite_data`, внутри контейнера: `/app/data/alphahack.db`.

## Документация

- [Архитектура](docs/architecture.md)
- [Демо-кейсы клиентов](docs/demo-cases.md)
- [FSM и статусы](docs/state-machine.md)
- [Модель данных](docs/data-model.md)
- [API](docs/api.md)
- [OpenAPI JSON](docs/openapi.json)
- [HTTP-запросы](docs/api.http)
- [Тестовые сценарии](docs/test-scenarios.md)
- [THIRD_PARTY_NOTICES](THIRD_PARTY_NOTICES)

Зависимости зафиксированы:

- backend: `requirements.lock`;
- frontend: `Alpha-front/package-lock.json`.

## Демо-аккаунт

```text
client@demo.ru / password123
```

## Демо за 3 минуты

1. Войти под `client@demo.ru`.
2. Открыть **#4** — финальный `OFFER_ACCEPTED`.
3. Открыть **#3** — `OFFER_MADE`, counteroffer.
4. Открыть **#2** — `NEEDS_INFO`, показать недостающие поля.
5. Открыть **#1** — `REJECTED`, показать risk score и причины.
6. Создать новую заявку — показать форму.
7. Подать заявку — показать обработку.
8. Вернуться к списку — показать статистику и фильтры.

### Демо-заявки

- `#1` — `REJECTED`, 1 000 000 ₽, 24 мес, risk 25/100 HIGH.
- `#2` — `NEEDS_INFO`, 1 000 000 ₽, 24 мес, не хватает финансовых данных.
- `#3` — `OFFER_MADE`, запрошено 5 000 000 ₽, counteroffer 1 630 000 ₽,
  24 мес, 23%, платёж 85 368.49 ₽, DSCR 1.300182.
- `#4` — `OFFER_ACCEPTED`, 1 000 000 ₽, 24 мес, 24%,
  платёж 52 871.10 ₽, DSCR 3.888361.

Список сортируется по `id DESC`: `#4`, `#3`, `#2`, `#1`.

Seed идемпотентный. Если engine недоступен, создаются только пользователь и DRAFT.

## Ограничения MVP

1. Все внешние проверки синтетические: нет реальных ЕГРЮЛ, БКИ и антифрода.
2. Нет ручного рассмотрения заявок.
3. Нет подписания договора и выдачи денег.
4. SQLite и demo JWT secret не предназначены для production.
5. Risk score не является калиброванной вероятностью одобрения.

## API

Все успешные ответы:

```json
{"data": {}}
```

Ошибки:

```json
{"error": {"code": "forbidden", "message": "not allowed"}}
```

Основные endpoints:

```text
POST   /api/auth/login
GET    /api/applications
POST   /api/applications
GET    /api/applications/{id}
PATCH  /api/applications/{id}
POST   /api/applications/{id}/submit
POST   /api/applications/{id}/offers/{offer_id}/accept
POST   /api/applications/{id}/offers/{offer_id}/decline
POST   /api/applications/{id}/withdraw
GET    /health
GET    /readyz
```

Для submit/accept/decline/withdraw frontend отправляет `Idempotency-Key`.

## Конфигурация

Один `.env` в корне. Vite читает его через `envDir`.

```env
APP_ENV=development
HTTP_ADDR=:8000
DATABASE_URL=sqlite:///./alphahack.db
DROP_ON_START=false
JWT_SECRET=dev-insecure-change-me
JWT_TTL=24h
ML_MODE=engine
ML_BASE_URL=http://localhost:8001
CORS_ORIGINS=http://localhost:5173,http://localhost:3000
VITE_API_URL=http://localhost:8000
```

`ML_MODE`:

- `engine` — локальный credit engine, default;
- `mock` — mock для тестов;
- `http` — будущий внешний ML-сервис.
