"""Latency fixtures: sample catalog and mocked Mercadona HTTP."""

from __future__ import annotations

from typing import Iterator

import pytest
from fastapi.testclient import TestClient

from tests.benchmark import latency_harness as harness


@pytest.fixture
def sample_client() -> Iterator[TestClient]:
    with harness.sample_client() as client:
        yield client


@pytest.fixture
def mocked_http_client() -> Iterator[TestClient]:
    with harness.mocked_http_client() as client:
        yield client


@pytest.fixture
def cold_warmup_client() -> Iterator[TestClient]:
    with harness.cold_warmup_client() as client:
        yield client
