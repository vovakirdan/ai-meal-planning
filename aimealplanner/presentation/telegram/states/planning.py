from aiogram.fsm.state import State, StatesGroup


class PlanningStates(StatesGroup):
    replace_existing_draft = State()
    range_choice = State()
    custom_start_date = State()
    custom_end_date = State()
    template_confirm = State()
    meal_count = State()
    desserts_enabled = State()
    week_mood = State()
    custom_week_mood = State()
    weekly_notes = State()
    pantry_considered = State()
