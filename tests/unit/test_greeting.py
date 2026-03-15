from aimealplanner.application.greeting import build_welcome_message


def test_build_welcome_message_is_russian() -> None:
    message = build_welcome_message()

    assert "Привет" in message
    assert "каркас" in message
