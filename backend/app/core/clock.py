import zoneinfo
from abc import ABC, abstractmethod
from datetime import UTC, date, datetime

MANILA_TZ = zoneinfo.ZoneInfo("Asia/Manila")


class Clock(ABC):
    @abstractmethod
    def now(self) -> datetime:
        """Returns current datetime in UTC (timezone-aware)."""
        pass

    def today(self) -> date:
        """Returns current business date in Asia/Manila timezone."""
        return self.now().astimezone(MANILA_TZ).date()


class SystemClock(Clock):
    def now(self) -> datetime:
        return datetime.now(UTC)


class ControllableClock(Clock):
    """Controllable clock for deterministic tests and business data simulation."""

    def __init__(self, initial_time: datetime | None = None) -> None:
        if initial_time is None:
            self._current_time = datetime.now(UTC)
        elif initial_time.tzinfo is None:
            self._current_time = initial_time.replace(tzinfo=UTC)
        else:
            self._current_time = initial_time.astimezone(UTC)

    def now(self) -> datetime:
        return self._current_time

    def set_time(self, new_time: datetime) -> None:
        if new_time.tzinfo is None:
            self._current_time = new_time.replace(tzinfo=UTC)
        else:
            self._current_time = new_time.astimezone(UTC)

    def advance(self, **kwargs) -> None:
        from datetime import timedelta

        self._current_time += timedelta(**kwargs)


default_clock = SystemClock()


def get_clock() -> Clock:
    return default_clock
