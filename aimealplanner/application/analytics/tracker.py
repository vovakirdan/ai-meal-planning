from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol

AnalyticsProperties = Mapping[str, object]


class AnalyticsTracker(Protocol):
    def identify(
        self,
        *,
        telegram_user_id: int,
        properties: AnalyticsProperties | None = None,
    ) -> None: ...

    def capture(
        self,
        *,
        telegram_user_id: int,
        event: str,
        properties: AnalyticsProperties | None = None,
    ) -> None: ...

    async def aclose(self) -> None: ...


class NullAnalyticsTracker:
    def identify(
        self,
        *,
        telegram_user_id: int,
        properties: AnalyticsProperties | None = None,
    ) -> None:
        del telegram_user_id, properties

    def capture(
        self,
        *,
        telegram_user_id: int,
        event: str,
        properties: AnalyticsProperties | None = None,
    ) -> None:
        del telegram_user_id, event, properties

    async def aclose(self) -> None:
        return None
