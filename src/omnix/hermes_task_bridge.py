"""Fail-closed compatibility boundary for Hermes task primitives.

Hermes' cron scheduler, worker host and delegated-worker ledger own Hermes
profiles and launch Hermes agents. OMNI-X therefore reuses the pure schedule
parser only; SQLite, process ownership, policy snapshots and execution remain
OMNI-X-owned so there is one runtime.
"""

from __future__ import annotations

import datetime as dt
import importlib
import re
import sys
import time
from dataclasses import dataclass

from .hermes_runtime import installed_hermes_source


@dataclass(frozen=True)
class HermesTaskCapabilities:
    source: str | None
    schedule_parser: bool
    scheduler_embedded: bool = False
    worker_host_embedded: bool = False
    delegated_worker_embedded: bool = False


def inspect_task_capabilities() -> HermesTaskCapabilities:
    source = installed_hermes_source()
    if source is None:
        return HermesTaskCapabilities(None, False)
    source_text = str(source)
    if source_text not in sys.path:
        sys.path.insert(0, source_text)
    try:
        importlib.import_module("cron.jobs").parse_schedule
    except (ImportError, AttributeError):
        return HermesTaskCapabilities(source_text, False)
    # Importing Hermes scheduler/worker modules would initialise their profile
    # stores and process protocol. They are references for lifecycle semantics,
    # not a second runtime embedded in OMNI-X.
    return HermesTaskCapabilities(source_text, True)


def parse_schedule(value: str) -> tuple[str, float, float | None]:
    """Normalise Hermes schedule syntax for the OMNI-X SQLite scheduler."""
    raw = value.strip()
    try:
        source = installed_hermes_source()
        if source:
            source_text = str(source)
            if source_text not in sys.path:
                sys.path.insert(0, source_text)
            from cron.jobs import parse_schedule as hermes_parse  # type: ignore

            try:
                parsed = hermes_parse(raw)
            except (ValueError, TypeError):
                # Hermes rejects sub-minute decimal intervals that OMNI-X uses
                # in deterministic tests; retain the local fallback for those
                # inputs while preserving explicit cron dependency errors below.
                parsed = None
            if parsed is None:
                raise ImportError("Hermes parser did not accept this local schedule")
            kind = str(parsed["kind"])
            if kind == "once":
                when = dt.datetime.fromisoformat(str(parsed["run_at"]))
                if when.tzinfo is None:
                    when = when.replace(tzinfo=dt.timezone.utc)
                return kind, when.timestamp(), None
            if kind == "interval":
                seconds = float(parsed["minutes"]) * 60
                return kind, time.time() + seconds, seconds
            if kind == "cron":
                try:
                    from croniter import croniter  # type: ignore
                except ImportError as exc:
                    raise ValueError("cron schedules require Hermes' optional croniter dependency") from exc
                now = dt.datetime.now(dt.timezone.utc)
                return kind, croniter(str(parsed["expr"]), now).get_next(dt.datetime).timestamp(), None
    except ImportError:
        pass

    if re.fullmatch(r"(?:every\s+)?\d+(?:\.\d+)?[smhd]", raw.lower()):
        token = raw.lower().replace("every", "").strip()
        amount, unit = float(token[:-1]), token[-1]
        seconds = amount * {"s": 1, "m": 60, "h": 3600, "d": 86400}[unit]
        return "interval", time.time() + seconds, seconds
    try:
        when = dt.datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("schedule must be a Hermes-supported ISO timestamp or interval such as 'every 1m'") from exc
    if when.tzinfo is None:
        when = when.replace(tzinfo=dt.timezone.utc)
    return "once", when.timestamp(), None
