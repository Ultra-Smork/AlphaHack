# Тестовые сценарии

## Подготовка

```bash
make reset-db
make dev
```

Логин:

```text
client@demo.ru / password123
```

## TC-01. Финальный оффер

- Открыть заявку `#4`.
- Ожидается: `OFFER_ACCEPTED`, risk 100 LOW, зелёная плашка.
- Offer: 1 000 000 ₽, 24 мес, 24%, платёж 52 871.10 ₽, DSCR 3.888361.

## TC-02. Counteroffer

- Открыть заявку `#3`.
- Ожидается: `OFFER_MADE`, risk 90 LOW.
- Запрошено 5 000 000 ₽.
- Предложение: 1 630 000 ₽, 24 мес, 23%, платёж 85 368.49 ₽, DSCR 1.300182.
- Причина: `AMOUNT_LIMITED_BY_PRODUCT_OR_AFFORDABILITY`.
- В блоке «Почему такое решение» видны лимит продукта и лимит по платёжеспособности.

## TC-03. Не хватает данных

- Открыть заявку `#2`.
- Ожидается: `NEEDS_INFO`.
- Risk: `0 из 100`, категория отсутствует.
- Показаны missing fields:
  - выручка;
  - доступный денежный поток;
  - существующая долговая нагрузка.
- Сверху жёлтая плашка «Недостаточно данных для оценки риска».

## TC-04. Автоматический отказ

- Открыть заявку `#1`.
- Ожидается: `REJECTED`, risk 25 HIGH.
- Причина: `HIGH_DEMO_RISK`.
- Видны факторы риска и действие «Что сделать».

## TC-05. Создание заявки

- Открыть «Создать заявку».
- Заполнить:
  - product 1;
  - amount 1 000 000;
  - term 24;
  - age 36;
  - revenue 1 500 000;
  - consent true.
- Ожидается: DRAFT, toast «Черновик создан», переход в карточку.

## TC-06. Валидация формы

- amount 0 -> ошибка суммы.
- term 0 -> ошибка срока.
- age -1 -> ошибка возраста.
- consent false -> ошибка согласия.
- Данные не отправляются.

## TC-07. Product limit

- Создать equipment-заявку с возрастом бизнеса 18 мес.
- Подать.
- Ожидается: `REJECTED`, причина `PRODUCT_BUSINESS_AGE_REQUIREMENT`.
- В причине:
  - текущий возраст;
  - минимум 24 мес;
  - рекомендация выбрать другой продукт.

## TC-08. NEEDS_INFO recovery

- Создать заявку без `monthly_revenue`.
- Подать.
- Ожидается: `NEEDS_INFO`, risk 0, missing fields.
- `PATCH` с revenue.
- Кнопка «Подать снова» отсутствует по UX-решению.

## TC-09. Idempotency

- `POST /submit` с `Idempotency-Key: test-1`.
- Повторить тот же запрос.
- Ожидается одинаковый response body.
- Повторить с тем же ключом, но другим request hash -> `409`.

## TC-10. Auth

- Без токена `GET /api/applications` -> `401`.
- Чужой токен/чужая заявка -> `403`.
- Неверный пароль -> `401 invalid_credentials`.

## TC-11. Engine errors

- Engine technical invalid -> `422 invalid_application_data`, заявка остаётся `DRAFT`.
- Engine unavailable -> `503 engine_unavailable`, заявка не остаётся в `SCORING`.
- UI показывает toast + постоянную красную плашку.

## TC-12. Docker

```bash
docker compose up --build
```

- `GET /health` -> 200.
- `/` -> React SPA.
- `/api/applications` -> 4 demo заявки.
- Python внутри контейнера: 3.12.
