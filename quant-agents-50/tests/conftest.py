from __future__ import annotations

from pathlib import Path

import pytest

from quantagents.config import AppConfig
from quantagents.data.synthetic import synthetic_market
from quantagents.market import MarketData
from quantagents.registry import Registry

REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def repo_root() -> Path:
    return REPO_ROOT


@pytest.fixture
def cfg() -> AppConfig:
    return AppConfig()


@pytest.fixture(scope="session")
def market() -> MarketData:
    return synthetic_market()


@pytest.fixture(scope="session")
def registry() -> Registry:
    return Registry.load(REPO_ROOT / "config" / "agents.yaml")
