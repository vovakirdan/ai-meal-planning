from __future__ import annotations

from aimealplanner.presentation.telegram.handlers.shopping import _split_shopping_message


def test_split_shopping_message_keeps_short_text_as_single_message() -> None:
    text = "Список покупок.\n\n- Авокадо\n- Рис"

    assert _split_shopping_message(text) == [text]


def test_split_shopping_message_splits_long_text_into_numbered_chunks() -> None:
    lines = ["Список покупок.", ""] + [f"- Позиция {index}" for index in range(500)]
    chunks = _split_shopping_message("\n".join(lines))

    assert len(chunks) > 1
    assert chunks[0].startswith("Список покупок (1/")
    assert all(len(chunk) <= 4096 for chunk in chunks)
