# Architecture

## Decision

На старте проект оформлен как bot-first async monolith.

Это сознательный выбор под текущую цель:

- нагрузка ожидается низкая;
- нужен быстрый и понятный bootstrap;
- важно не тащить лишние процессы раньше времени;
- при этом нужно оставить нормальные границы для роста.

## Runtime shape

Сейчас есть один исполняемый процесс:

- Telegram polling bot на `aiogram`

Снаружи к нему подключены:

- PostgreSQL как source of truth
- Redis как инфраструктурный компонент под future FSM/cache/locks

## Layering

### Presentation

`aimealplanner/presentation`

Отвечает за Telegram-specific слой:

- роутеры;
- handlers;
- дальнейшие inline-кнопки и guided flows.

### Application

`aimealplanner/application`

Слой use cases. Здесь должна жить orchestration-логика сценариев:

- onboarding;
- weekly planning;
- replanning;
- shopping generation;
- feedback processing.

### Domain

`aimealplanner/domain`

Слой доменных типов и ограничений. Пока он минимальный, но именно сюда будут выноситься:

- value objects;
- enum-ы и статусы;
- правила repeatability/diversity;
- pantry- и planning-related инварианты.

### Infrastructure

`aimealplanner/infrastructure`

Адаптеры к внешнему миру:

- SQLAlchemy models и session factory;
- Redis client;
- позднее LLM provider, background jobs, внешние интеграции.

## Persistence

На этом этапе миграций нет. Вместо этого при старте вызывается `metadata.create_all()`.

Это допустимо для bootstrap, потому что:

- схема еще не стабилизирована;
- сейчас важнее быстро получить рабочий каркас;
- позже можно безболезненно добавить Alembic поверх уже выделенного persistence-слоя.

## Operational decision

Локальный entrypoint один:

```bash
docker compose up --build
```

Так поднимаются:

- бот;
- PostgreSQL;
- Redis.

## Growth path

Когда появится реальная функциональность, этот каркас можно расширять без перелома структуры:

1. добавить Alembic;
2. вынести LLM orchestration в отдельный application service;
3. подключить Redis как FSM/cache;
4. при необходимости добавить FastAPI/webhook adapter рядом с polling-режимом или вместо него.
