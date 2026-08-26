from backend.app.common.enums import ActivationReason, DesiredState
from backend.app.lights.resolver import calculate_desired_state


def test_no_activation_resolves_off() -> None:
    result = calculate_desired_state((), DesiredState.OFF)

    assert result.desired_state == "OFF"
    assert result.active_reasons == ()
    assert result.changed is False


def test_visit_resolves_on() -> None:
    result = calculate_desired_state((ActivationReason.VISIT,), DesiredState.OFF)

    assert result.desired_state == "ON"
    assert result.active_reasons == ("VISIT",)
    assert result.changed is True


def test_overlapping_anniversary_and_visit_remains_on() -> None:
    result = calculate_desired_state(
        (ActivationReason.VISIT, ActivationReason.ANNIVERSARY),
        DesiredState.ON,
    )

    assert result.desired_state == "ON"
    assert result.active_reasons == ("ANNIVERSARY", "VISIT")
    assert result.changed is False


def test_ending_visit_while_anniversary_active_has_no_off_intent() -> None:
    result = calculate_desired_state((ActivationReason.ANNIVERSARY,), DesiredState.ON)

    assert result.desired_state == "ON"
    assert result.active_reasons == ("ANNIVERSARY",)
    assert result.changed is False
