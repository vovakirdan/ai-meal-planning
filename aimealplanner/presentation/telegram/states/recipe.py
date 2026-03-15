from aiogram.fsm.state import State, StatesGroup


class RecipeStates(StatesGroup):
    feedback = State()
