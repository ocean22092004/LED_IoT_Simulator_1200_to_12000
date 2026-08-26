from datetime import date

import pytest

from backend.app.anniversaries.lunar import LunarDate, VietnameseLunarCalendarProvider

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("solar_date", "expected_lunar"),
    [
        (date(2026, 2, 17), LunarDate(year=2026, month=1, day=1, is_leap_month=False)),
        (date(2024, 2, 10), LunarDate(year=2024, month=1, day=1, is_leap_month=False)),
    ],
)
def test_known_tet_dates(
    solar_date: date,
    expected_lunar: LunarDate,
) -> None:
    provider = VietnameseLunarCalendarProvider()

    assert provider.from_solar(solar_date) == expected_lunar
    assert provider.to_solar(expected_lunar) == solar_date


def test_verified_2004_leap_month_start() -> None:
    """Fixture from lunar-vn/Hồ Ngọc Đức: 2004-03-21 is leap lunar 01/02."""
    provider = VietnameseLunarCalendarProvider()
    lunar_date = LunarDate(year=2004, month=2, day=1, is_leap_month=True)

    assert provider.from_solar(date(2004, 3, 21)) == lunar_date
    assert provider.to_solar(lunar_date) == date(2004, 3, 21)
