# AI Meal Planner

Стартовый каркас Telegram-бота для meal planning MVP.

## Что уже есть

- `aiogram`-бот с polling-mode и командой `/start`
- асинхронное подключение к PostgreSQL через SQLAlchemy 2.x
- подключение к Redis
- автосоздание таблиц при старте без миграций
- `ruff`, `ty`, `pytest`, `pre-commit`
- локальный запуск одной командой через Docker Compose

## Запуск

1. Создай `.env` на основе `.env.example` и вставь реальный `BOT_TOKEN`.
2. Запусти:

```bash
docker compose up --build
```

После этого бот ответит на `/start` приветствием на русском языке.

## Локальные проверки

```bash
uv run ruff format
uv run ruff check
uv run ty check
uv run pytest
uv run pre-commit run --all-files
```

## Структура

- `aimealplanner/presentation` — Telegram handlers и routers
- `aimealplanner/application` — простые application-level use cases
- `aimealplanner/domain` — типы и будущие доменные сущности
- `aimealplanner/infrastructure` — PostgreSQL и Redis адаптеры
- `docs/ARCHITECTURE.md` — стартовая архитектура
