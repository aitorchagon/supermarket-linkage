from datetime import timedelta

from supermarket_linkage.app.streamlit_app import _health_poll_interval
from supermarket_linkage.app.streamlit_consts import _HEALTH_POLL_WHILE_COLD_S


def test_health_poll_stops_when_worker_is_warm() -> None:
    assert _health_poll_interval(True) is None


def test_health_poll_runs_only_while_cold() -> None:
    assert _health_poll_interval(False) == timedelta(seconds=_HEALTH_POLL_WHILE_COLD_S)
