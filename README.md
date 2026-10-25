# Суирники3

B2C-кредитный симулятор для предпринимателей. Клиент заполняет заявку, локальный кредитный движок оценивает бизнес и выдаёт финальное решение: одобрение, counteroffer, запрос данных или отказ.

Ручного рассмотрения, подписания договора и выдачи денег нет. `OFFER_ACCEPTED` — финальный статус.

## Стек

- Backend: FastAPI, SQLAlchemy, SQLite, Pydantic v2, PyJWT.
- Frontend: React 19, TypeScript, Vite, Tailwind CSS v3, shadcn/ui, axios.
- Кредитное ядро: локальный Python-движок `app/platform/ai/credit_engine.py`.
- Docker: Python 3.12 + собранный frontend в одном контейнере.

## Как это работает

1. Пользователь логинится по email и паролю.
2. Создаёт черновик заявки.
3. Подаёт заявку.
4. Backend синхронно прогоняет FSM:
   `DRAFT -> SUBMITTED -> INTAKE_CHECK -> ENRICHMENT -> SCORING`.
5. `credit_engine` возвращает решение.
6. Backend сохраняет `Evaluation`, `Offer`, `ApplicationEvent` и обновляет статус.
7. Пользователь принимает или отклоняет оффер.

## Запуск локально

```bash
make install
make dev
```

- Frontend: http://localhost:5173
- Backend: http://localhost:8000
- Swagger: http://localhost:8000/docs

`make dev` запускает оба процесса и останавливает их по `Ctrl+C`.

## Docker

Один контейнер: frontend собирается Node-стадией, backend работает на Python 3.12 и отдаёт SPA с того же порта.

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

## Проверка

```bash
make check
```

Запускает:

- backend `pytest`;
- frontend `lint`;
- frontend `build`.

Текущий результат: **16 backend tests passed**, frontend lint/build clean.

## Демо-аккаунт

```text
client@demo.ru / password123
```

## Демо за 3 минуты

1. Войти под `client@demo.ru`.
2. Открыть **#4** — финальный `OFFER_ACCEPTED`.
3. Открыть **#3** — `OFFER_MADE`, counteroffer: движок снизил сумму.
4. Открыть **#2** — `NEEDS_INFO`, показать недостающие поля.
5. Открыть **#1** — `REJECTED`, показать risk score и причины.
6. Создать новую заявку — показать форму.
7. Подать заявку — показать обработку и результат.
8. Вернуться к списку — показать статистику и фильтры.

## Демо-данные

Seed создаёт четыре заявки:

- `#1` — `REJECTED`, 1 000 000 ₽, 24 мес, high risk 25/100.
- `#2` — `NEEDS_INFO`, 1 000 000 ₽, 24 мес, не хватает финансовых данных.
- `#3` — `OFFER_MADE`, запрошено 5 000 000 ₽, engine дал counteroffer:
  1 630 000 ₽, 24 мес, 23%, платёж 85 368.49 ₽, DSCR 1.300182.
- `#4` — `OFFER_ACCEPTED`, 1 000 000 ₽, 24 мес, 24%,
  платёж 52 871.10 ₽, DSCR 3.888361.

Список сортируется по `id DESC`, поэтому сверху видны `#4`, `#3`, `#2`, `#1`.

Seed идемпотентный. Если движок недоступен, seed создаёт только пользователя и DRAFT.

Полный сброс локальной БД:

```bash
make reset-db
```

`DROP_ON_START=true` удаляет таблицы при старте. Использовать только для очистки.

## Продукты

| ID | Продукт | Сумма | Срок | Возраст бизнеса | Margin |
|---|---|---|---|---|---|
| 1 | Оборотные средства | 100 000–3 000 000 ₽ | 6–24 мес | от 12 мес | +4 п.п. |
| 2 | Оборудование | 300 000–5 000 000 ₽ | 12–36 мес | от 24 мес | +2 п.п. |

Engine-политика — источник истины. UI не блокирует нестандартные значения; engine сам решает:

- `APPROVED` -> `OFFER_MADE`;
- `COUNTEROFFER` -> `OFFER_MADE`;
- `NEED_INFO` -> `NEEDS_INFO`;
- `DECLINED` -> `REJECTED`.

## Risk score

`risk score` — это балл **0..100**, а не вероятность одобрения.

- 75–100 — низкий риск;
- 50–74 — средний риск;
- 0–49 — высокий риск;
- выше — лучше.

На решение также влияют продукт, сумма, срок, DSCR, денежный поток, проверки и долговая нагрузка. `calibrated_pd` в demo-движке всегда `null`.

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

## API

Все ответы в envelope:

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

Один `.env` в корне проекта. Vite читает его через `envDir`.

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
- `mock` — простой mock для тестов;
- `http` — будущий внешний ML-сервис через `POST {ML_BASE_URL}/evaluate`.

## Ограничения demo

- синтетические данные;
- нет реальных адаптеров ЕГРЮЛ, БКИ и антифрода;
- checks замоканы в `CreditEngineClient`;
- нет manual review;
- нет подписания и выдачи;
- SQLite, не production-конфигурация;
- JWT secret в примере предназначен только для локального demo.
