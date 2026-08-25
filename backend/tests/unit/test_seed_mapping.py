import pytest

from backend.app.seed import excel_zone_code, main, mapping_for_location

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("index", "expected"),
    [
        (1, "A"),
        (26, "Z"),
        (27, "AA"),
        (52, "AZ"),
        (53, "BA"),
    ],
)
def test_excel_zone_code_uses_one_based_excel_notation(
    index: int,
    expected: str,
) -> None:
    assert excel_zone_code(index) == expected


@pytest.mark.parametrize(
    ("number", "zone", "controller", "channel"),
    [
        (1, "A", "CTRL-A-01", 1),
        (64, "A", "CTRL-A-01", 64),
        (65, "A", "CTRL-A-02", 1),
        (250, "A", "CTRL-A-04", 58),
        (300, "A", "CTRL-A-05", 44),
        (301, "B", "CTRL-B-01", 1),
        (7801, "AA", "CTRL-AA-01", 1),
    ],
)
def test_mapping_for_location_is_deterministic(
    number: int,
    zone: str,
    controller: str,
    channel: int,
) -> None:
    mapping = mapping_for_location(number)

    assert (
        mapping.zone_code,
        mapping.gateway_code,
        mapping.controller_code,
        mapping.controller_address,
        mapping.channel_number,
    ) == (
        zone,
        f"GW-{zone}",
        controller,
        int(controller.rsplit("-", maxsplit=1)[1]),
        channel,
    )


def test_mapping_supports_configurable_topology() -> None:
    mapping = mapping_for_location(
        11,
        locations_per_zone=10,
        controller_capacity=4,
    )

    assert mapping.zone_code == "B"
    assert mapping.controller_code == "CTRL-B-01"
    assert mapping.channel_number == 1


@pytest.mark.parametrize("index", [0, -1])
def test_excel_zone_code_rejects_non_positive_index(index: int) -> None:
    with pytest.raises(ValueError, match="positive"):
        excel_zone_code(index)


@pytest.mark.parametrize(
    ("location_number", "locations_per_zone", "controller_capacity"),
    [
        (0, 300, 64),
        (-1, 300, 64),
        (1, 0, 64),
        (1, 300, 0),
    ],
)
def test_mapping_rejects_non_positive_inputs(
    location_number: int,
    locations_per_zone: int,
    controller_capacity: int,
) -> None:
    with pytest.raises(ValueError, match="positive"):
        mapping_for_location(
            location_number,
            locations_per_zone=locations_per_zone,
            controller_capacity=controller_capacity,
        )


def test_seed_cli_rejects_non_positive_location_count(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as exit_info:
        main(["--locations", "0"])

    assert exit_info.value.code == 2
    assert "location count must be positive" in capsys.readouterr().err
