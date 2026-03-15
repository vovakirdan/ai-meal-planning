from __future__ import annotations

from aimealplanner.presentation.telegram.keyboards.onboarding import SKIP_LABEL
from aimealplanner.presentation.telegram.keyboards.planning import (
    CUSTOM_WEEK_MOOD_LABEL,
    WEEK_MOOD_LABELS,
    build_week_mood_keyboard,
)


def test_build_week_mood_keyboard_offers_expected_presets_and_custom_option() -> None:
    keyboard = build_week_mood_keyboard()

    rows = [[button.text for button in row] for row in keyboard.keyboard]

    assert rows == [
        ["Азиатская", "Грузинская"],
        ["Русская", "Мексиканская"],
        [CUSTOM_WEEK_MOOD_LABEL],
        [SKIP_LABEL],
    ]
    assert WEEK_MOOD_LABELS == {
        "Азиатская": "Азиатская",
        "Грузинская": "Грузинская",
        "Мексиканская": "Мексиканская",
        "Русская": "Русская",
    }
