from __future__ import annotations

import time

import omnix.hermes_task_bridge as bridge


def test_schedule_bridge_fallback_is_durable_and_explicit(monkeypatch):
    monkeypatch.setattr(bridge, "installed_hermes_source", lambda: None)
    kind, due, recurrence = bridge.parse_schedule("every 0.1s")
    assert kind == "interval"
    assert due >= time.time()
    assert recurrence == 0.1

    kind, due, recurrence = bridge.parse_schedule("2030-01-01T00:00:00Z")
    assert kind == "once"
    assert due > time.time()
    assert recurrence is None


def test_capability_report_does_not_embed_hermes_scheduler(monkeypatch, tmp_path):
    monkeypatch.setattr(bridge, "installed_hermes_source", lambda: tmp_path)
    # A source-shaped directory without Hermes modules is reported unavailable
    # rather than guessed as usable.
    result = bridge.inspect_task_capabilities()
    assert result.source == str(tmp_path)
    assert result.schedule_parser is False
    assert result.scheduler_embedded is False
    assert result.worker_host_embedded is False
    assert result.delegated_worker_embedded is False
