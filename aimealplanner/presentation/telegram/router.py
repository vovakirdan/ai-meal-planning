from aiogram import Router

from aimealplanner.presentation.telegram.handlers.start import router as start_router


def build_router() -> Router:
    router = Router(name="root")
    router.include_router(start_router)
    return router
