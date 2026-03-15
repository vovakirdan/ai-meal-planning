# Deployment

Проект деплоится через manual workflow GitHub Actions: `.github/workflows/deploy.yml`.

Flow:
- вручную запускается workflow на `main`;
- три quality-проверки идут параллельно: `ruff`, `ty`, `pytest`;
- после них собирается Docker image и пушится в `ghcr.io`;
- затем workflow по SSH заходит на сервер, кладет `compose.prod.yaml` и `.env`, делает `docker compose pull` и `docker compose up -d`.

## GitHub Variables

Нужно добавить repository variables:

- `DEPLOY_HOST`
  - значение: `104.194.156.226`
- `DEPLOY_USER`
  - значение: `root`
- `DEPLOY_PORT`
  - значение: `22`
- `DEPLOY_PATH`
  - значение: `/opt/aimealplanner`

## GitHub Secrets

Нужно добавить repository secrets:

- `DEPLOY_SSH_PRIVATE_KEY`
  - приватный SSH-ключ, которым GitHub Actions сможет зайти на `root@104.194.156.226`
  - соответствующий публичный ключ должен быть в `/root/.ssh/authorized_keys` на сервере

- `PRODUCTION_ENV_FILE`
  - полный production `.env` целиком, многострочным secret
  - workflow кладет его на сервер как `${DEPLOY_PATH}/.env`

- `GHCR_PULL_USERNAME`
  - обычно `vovakirdan`

- `GHCR_PULL_TOKEN`
  - GitHub token для `docker login ghcr.io` на сервере
  - самый простой вариант: classic PAT с `read:packages`
  - если репозиторий приватный, обычно нужен еще доступ к repo

## Production Env

В `PRODUCTION_ENV_FILE` должны быть минимум такие переменные:

```dotenv
BOT_TOKEN=...
APP_ENV=production
LOG_LEVEL=INFO

POSTGRES_DB=aimealplanner
POSTGRES_USER=aimealplanner
POSTGRES_PASSWORD=change-me
DATABASE_URL=postgresql+asyncpg://aimealplanner:change-me@postgres:5432/aimealplanner
REDIS_URL=redis://redis:6379/0

AI_API_KEY=...
AI_MODEL=chatgpt/gpt-5.3-codex-spark
AI_BASE_URL=http://host.docker.internal:4001/v1

SPOONACULAR_API_KEY=...

SENTRY_DSN=...

POSTHOG_API_KEY=...
POSTHOG_HOST=https://eu.posthog.com
```

Примечание по `AI_BASE_URL`:
- на сервере endpoint на `127.0.0.1:4001` отвечает;
- контейнер бота не видит host loopback напрямую;
- поэтому в `compose.prod.yaml` уже добавлен `host.docker.internal:host-gateway`;
- внутри контейнера нужно использовать именно `http://host.docker.internal:4001/v1`.

## One-Time Server Requirements

На сервере уже проверено:
- есть Docker
- есть Docker Compose plugin

От тебя нужен только доступ по SSH для GitHub Actions и корректный `.env`.

## Deploy Runbook

1. Добавить variables и secrets.
2. Запустить workflow `Deploy Production` из GitHub Actions на ветке `main`.
3. Дождаться:
   - `Quality / ruff`
   - `Quality / ty`
   - `Quality / pytest`
   - `Build and Push Image`
   - `Deploy to Production`

После успешного деплоя стек будет жить в `${DEPLOY_PATH}` на сервере.
