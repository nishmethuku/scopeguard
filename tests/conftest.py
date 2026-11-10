import pytest

from scopeguard.scenarios import build_suite


@pytest.fixture(scope="session")
def suite():
    return build_suite(100, 0)


@pytest.fixture(scope="session")
def small():
    return build_suite(6, 0)
