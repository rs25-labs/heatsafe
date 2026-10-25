import pytest

from scripts.build_heat_overlay import dn_to_fahrenheit


def test_dn_to_fahrenheit() -> None:
    assert dn_to_fahrenheit(44000) == pytest.approx(79.3, abs=0.1)
