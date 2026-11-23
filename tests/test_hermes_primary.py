from dataclasses import replace

import pytest

from omnix.config import Settings
from omnix.hermes_primary import HermesPrimaryError, run_hermes_primary_probe


def test_hermes_primary_refuses_paid_or_ambiguous_routes():
    with pytest.raises(HermesPrimaryError, match="FREE mode"):
        run_hermes_primary_probe(Settings(mode="SMART", provider="omniroute", model="auto/best-free"), "hello")
    with pytest.raises(HermesPrimaryError, match="explicitly free"):
        run_hermes_primary_probe(replace(Settings(mode="FREE", provider="omniroute"), model="unknown-model"), "hello")


def test_hermes_primary_requires_managed_install(monkeypatch):
    settings = Settings(mode="FREE", provider="omniroute", model="auto/best-free", base_url="http://127.0.0.1:20128/v1")
    monkeypatch.setattr("omnix.hermes_primary.installed_hermes_source", lambda: None)
    monkeypatch.setattr("omnix.hermes_primary.hermes_python", lambda: None)
    with pytest.raises(HermesPrimaryError, match="managed Hermes"):
        run_hermes_primary_probe(settings, "hello")
