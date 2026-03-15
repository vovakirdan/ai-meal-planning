from aimealplanner.presentation.telegram.commands import (
    build_public_bot_commands,
    get_public_command_specs,
    render_help_text,
)


def test_public_command_registry_contains_help_and_settings() -> None:
    commands = build_public_bot_commands()

    assert any(command.command == "help" for command in commands)
    assert any(command.command == "settings" for command in commands)
    assert commands[0].command == "start"


def test_help_text_mentions_core_journey() -> None:
    help_text = render_help_text()

    assert "/start" in help_text
    assert "/plan" in help_text
    assert "/week" in help_text
    assert "/shopping" in help_text
    assert "/review" in help_text
    assert len(get_public_command_specs()) == len(build_public_bot_commands())
