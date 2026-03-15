# AI Meal Planner Bot

Telegram-бот для недельного планирования питания семьи: onboarding, генерация меню на неделю, локальные правки блюд, рецепты, список покупок, feedback по блюдам, reminders и постоянные настройки.

Проект собран как async Python monolith на `aiogram` + PostgreSQL + Redis. Генерация меню и рецептов идет через OpenAI-compatible endpoint, а дополнительные recipe hints можно получать через Spoonacular.

## Что уже умеет MVP

- household-first onboarding через `/start`
- недельное планирование через `/plan`
- просмотр и редактирование активной недели через `/week`
- просмотр рецептов через `/recipe`
- просмотр ингредиентов через `/ingredients`
- генерация корзины через `/shopping`
- сбор обратной связи по блюдам через `/review`
- редактирование постоянных настроек через `/settings`
- ежедневные и weekly reminders
- PostHog analytics и Sentry monitoring

## Основной пользовательский цикл

Для нового пользователя типичный сценарий такой:

1. `/start` — пройти onboarding
2. `/plan` — составить недельный план
3. `/week` — проверить и при необходимости поправить блюда
4. `/shopping` — собрать список покупок
5. `/recipe` / `/ingredients` — открыть детали по блюдам
6. `/review` — оставить feedback после готовки

## Публичные команды

- `/start` — стартовая настройка профиля
- `/plan` — создать новый недельный план
- `/week` — открыть текущую неделю
- `/recipe` — открыть рецепты недели
- `/ingredients` — открыть ингредиенты блюд
- `/shopping` — собрать корзину покупок
- `/review` — оценить блюда
- `/settings` — изменить постоянные настройки
- `/help` — краткая справка
- `/cancel` — отменить активный сценарий ввода

Полный справочник: [docs/BOT_COMMANDS.md](/home/zov/projects/aimealplanner/docs/BOT_COMMANDS.md)

## Технологии

- Python 3.13
- `aiogram` 3.x
- SQLAlchemy 2.x + `asyncpg`
- Alembic
- Redis
- `uv`
- Docker Compose
- OpenAI-compatible AI provider
- Spoonacular
- PostHog
- Sentry

## Быстрый локальный запуск

### 1. Подготовить `.env`

Возьми за основу [.env.example](/home/zov/projects/aimealplanner/.env.example) и заполни минимум:

```dotenv
BOT_TOKEN=...
AI_API_KEY=...
AI_MODEL=...
AI_BASE_URL=...
```

Опционально:

- `SPOONACULAR_API_KEY`
- `SENTRY_DSN`
- `POSTHOG_API_KEY`
- `POSTHOG_HOST`

### 2. Поднять стек

```bash
docker compose up -d --build
```

Это поднимет:

- `bot`
- `postgres`
- `redis`

### 3. Проверить бота

Напиши боту в Telegram:

```text
/start
```

После завершения onboarding можно идти в `/plan`.

## Локальная разработка

Если нужен запуск quality checks вне Docker:

```bash
uv sync --frozen --dev
```

Полезные команды:

```bash
uv run ruff check aimealplanner tests
uv run ty check
uv run pytest
uv run pre-commit run --all-files
```

Локальный entrypoint в контейнере:

```bash
docker compose up -d --build
```

## Структура проекта

- [aimealplanner/presentation](/home/zov/projects/aimealplanner/aimealplanner/presentation) — Telegram handlers, keyboards, routers, middleware
- [aimealplanner/application](/home/zov/projects/aimealplanner/aimealplanner/application) — use cases: onboarding, planning, shopping, review, settings, reminders
- [aimealplanner/domain](/home/zov/projects/aimealplanner/aimealplanner/domain) — доменные типы
- [aimealplanner/infrastructure](/home/zov/projects/aimealplanner/aimealplanner/infrastructure) — DB, Redis, AI clients, analytics, monitoring
- [migrations](/home/zov/projects/aimealplanner/migrations) — Alembic migrations
- [docs](/home/zov/projects/aimealplanner/docs) — архитектура, flow spec, команды, deployment

## Документация

- [docs/ARCHITECTURE.md](/home/zov/projects/aimealplanner/docs/ARCHITECTURE.md) — базовая архитектура
- [docs/2026-03-15-onboarding-and-planning-flow-spec.md](/home/zov/projects/aimealplanner/docs/2026-03-15-onboarding-and-planning-flow-spec.md) — текущий продуктовый flow
- [docs/BOT_COMMANDS.md](/home/zov/projects/aimealplanner/docs/BOT_COMMANDS.md) — slash-команды
- [docs/DEPLOYMENT.md](/home/zov/projects/aimealplanner/docs/DEPLOYMENT.md) — production deployment через GitHub Actions

## Production Deploy

Продакшен деплой собран через manual GitHub Actions workflow:

- quality checks параллельно
- сборка и push Docker image в GHCR
- SSH deploy на сервер

Подробности: [docs/DEPLOYMENT.md](/home/zov/projects/aimealplanner/docs/DEPLOYMENT.md)

## Примечания

- Бот сейчас работает в polling mode.
- Активная неделя может быть `draft` или `confirmed`; подтвержденная неделя остается редактируемой.
- Shopping list строится по ingredient snapshots текущей недели, а не по каноническим рецептам.
- Локальный bot container лучше останавливать перед production smoke test тем же Telegram токеном.
