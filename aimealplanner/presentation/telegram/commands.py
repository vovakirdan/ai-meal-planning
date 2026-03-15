# ruff: noqa: RUF001
from __future__ import annotations

from dataclasses import dataclass

from aiogram.types import BotCommand


@dataclass(frozen=True, slots=True)
class PublicCommandSpec:
    command: str
    description: str
    help_line: str


_PUBLIC_COMMAND_SPECS: tuple[PublicCommandSpec, ...] = (
    PublicCommandSpec(
        command="start",
        description="Стартовая настройка профиля",
        help_line="`/start` — пройти стартовую настройку или начать заново",
    ),
    PublicCommandSpec(
        command="plan",
        description="Составить план недели",
        help_line="`/plan` — создать новый недельный план",
    ),
    PublicCommandSpec(
        command="week",
        description="Открыть текущий план",
        help_line="`/week` — открыть текущий черновик или последнюю подтвержденную неделю",
    ),
    PublicCommandSpec(
        command="recipe",
        description="Открыть рецепты недели",
        help_line="`/recipe` — выбрать блюдо и посмотреть рецепт целиком",
    ),
    PublicCommandSpec(
        command="ingredients",
        description="Открыть ингредиенты блюд",
        help_line="`/ingredients` — выбрать блюдо и посмотреть только ингредиенты",
    ),
    PublicCommandSpec(
        command="shopping",
        description="Собрать список покупок",
        help_line="`/shopping` — пересобрать корзину покупок по активной неделе",
    ),
    PublicCommandSpec(
        command="review",
        description="Оценить блюда",
        help_line="`/review` — пройти короткий feedback по блюдам за день",
    ),
    PublicCommandSpec(
        command="settings",
        description="Открыть настройки",
        help_line="`/settings` — изменить семью, pantry, напоминания и правила по блюдам",
    ),
    PublicCommandSpec(
        command="help",
        description="Показать список команд",
        help_line="`/help` — открыть краткую справку по возможностям бота",
    ),
    PublicCommandSpec(
        command="cancel",
        description="Отменить текущий шаг",
        help_line="`/cancel` — остановить текущий сценарий ввода",
    ),
)


def get_public_command_specs() -> tuple[PublicCommandSpec, ...]:
    return _PUBLIC_COMMAND_SPECS


def build_public_bot_commands() -> list[BotCommand]:
    return [
        BotCommand(command=command.command, description=command.description)
        for command in _PUBLIC_COMMAND_SPECS
    ]


def render_help_text() -> str:
    lines = [
        "Meal Planner Bot",
        "",
        "Если это первый запуск, начни с `/start`.",
        "После онбординга обычно хватает цикла `/plan` -> `/week` -> `/shopping` -> `/review`.",
        "",
        "Доступные команды:",
    ]
    lines.extend(command.help_line for command in _PUBLIC_COMMAND_SPECS)
    lines.extend(
        [
            "",
            "Быстрый старт:",
            "1. `/start` — настроить семью и напоминания",
            "2. `/plan` — собрать меню на неделю",
            "3. `/week` — открыть план и при необходимости отредактировать блюда",
        ],
    )
    return "\n".join(lines)
