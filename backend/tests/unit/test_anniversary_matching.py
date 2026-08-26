from dataclasses import dataclass

import pytest

from backend.app.anniversaries.lunar import LunarDate
from backend.app.anniversaries.service import anniversary_matches

pytestmark = pytest.mark.unit


@dataclass(frozen=True)
class Rule:
    lunar_day: int
    lunar_month: int
    is_leap_month: bool
    is_enabled: bool = True


def test_anniversary_match_requires_day_month_and_leap_flag() -> None:
    lunar_date = LunarDate(year=2004, month=2, day=1, is_leap_month=True)

    assert anniversary_matches(Rule(1, 2, True), lunar_date)
    assert not anniversary_matches(Rule(1, 2, False), lunar_date)
    assert not anniversary_matches(Rule(2, 2, True), lunar_date)
    assert not anniversary_matches(Rule(1, 3, True), lunar_date)
    assert not anniversary_matches(Rule(1, 2, True, is_enabled=False), lunar_date)


def test_day_30_uses_exact_match_policy() -> None:
    rule = Rule(30, 4, False)

    assert not anniversary_matches(
        rule,
        LunarDate(year=2026, month=4, day=29, is_leap_month=False),
    )
    assert anniversary_matches(
        rule,
        LunarDate(year=2026, month=4, day=30, is_leap_month=False),
    )
