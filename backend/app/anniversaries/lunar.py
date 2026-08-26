from dataclasses import dataclass
from datetime import date
from typing import Protocol

from lunar_vn import LunarDate as PackageLunarDate
from lunar_vn import lunar_to_solar, solar_to_lunar

VIETNAM_TIME_ZONE_OFFSET = 7.0


@dataclass(frozen=True)
class LunarDate:
    year: int
    month: int
    day: int
    is_leap_month: bool


class LunarCalendarProvider(Protocol):
    def from_solar(self, date: date) -> LunarDate: ...

    def to_solar(self, lunar: LunarDate) -> date: ...


class VietnameseLunarCalendarProvider:
    """Adapter isolating the application from lunar-vn's public API."""

    def from_solar(self, date: date) -> LunarDate:
        lunar = solar_to_lunar(date, time_zone=VIETNAM_TIME_ZONE_OFFSET)
        return LunarDate(
            year=lunar.year,
            month=lunar.month,
            day=lunar.day,
            is_leap_month=lunar.leap,
        )

    def to_solar(self, lunar: LunarDate) -> date:
        return lunar_to_solar(
            PackageLunarDate(
                lunar.day,
                lunar.month,
                lunar.year,
                lunar.is_leap_month,
            ),
            time_zone=VIETNAM_TIME_ZONE_OFFSET,
        )


default_lunar_calendar = VietnameseLunarCalendarProvider()
