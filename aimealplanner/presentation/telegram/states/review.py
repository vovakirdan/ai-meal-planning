from aiogram.fsm.state import State, StatesGroup


class ReviewStates(StatesGroup):
    active = State()
    comment = State()
