from aiogram.fsm.state import State, StatesGroup


class SettingsStates(StatesGroup):
    add_member_name = State()
    add_member_constraints = State()
    add_member_cuisines = State()
    add_member_note = State()
    rename_member = State()
    edit_member_constraints = State()
    edit_member_cuisines = State()
    edit_member_note = State()
    daily_reminder_time = State()
    weekly_reminder_time = State()
    pantry_add_name = State()
    pantry_add_hint = State()
    pantry_edit_hint = State()
