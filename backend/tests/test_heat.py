import pytest

from heatsafe.heat import ExposureLevel, effective_heat_index_f, exposure_level, heat_index_f


@pytest.mark.parametrize(
    ("temp_f", "humidity", "expected", "tolerance"),
    [(90, 50, 95, 1), (100, 40, 109, 1), (96, 65, 121, 2), (75, 50, 75, 1)],
)
def test_heat_index_nws_table(temp_f: float, humidity: float, expected: float, tolerance: float) -> None:
    assert abs(heat_index_f(temp_f, humidity) - expected) <= tolerance


def test_effective_heat_index_full_sun() -> None:
    assert effective_heat_index_f(100, 1.0) == 115


@pytest.mark.parametrize(
    ("value", "level"),
    [
        (89.9, ExposureLevel.low),
        (90, ExposureLevel.moderate),
        (103, ExposureLevel.high),
        (115, ExposureLevel.extreme),
    ],
)
def test_exposure_thresholds(value: float, level: ExposureLevel) -> None:
    assert exposure_level(value) == level
