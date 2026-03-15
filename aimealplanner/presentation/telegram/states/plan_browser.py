from aiogram.fsm.state import State, StatesGroup


class PlanBrowserStates(StatesGroup):
    custom_item_adjustment = State()
