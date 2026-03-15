from aiogram.fsm.state import State, StatesGroup


class OnboardingStates(StatesGroup):
    household_size = State()
    meal_count = State()
    desserts_enabled = State()
    repeatability_mode = State()
    member_name = State()
    member_constraints = State()
    member_cuisines = State()
    member_note = State()
    daily_reminder_enabled = State()
    daily_reminder_time = State()
    weekly_reminder_enabled = State()
    weekly_reminder_day = State()
    weekly_reminder_time = State()
    pantry_choice = State()
    pantry_item_name = State()
    pantry_stock_level = State()
    pantry_quantity_hint = State()
    pantry_continue = State()
