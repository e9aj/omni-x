# OMNI-X Benchmarks

This file records reproducible measurements. Live provider results below are limited to the verified free OmniRoute gateway run; no paid provider was configured.

Each benchmark run must record:

- commit SHA and Python version;
- provider, model, mode, and whether the run was live or local;
- input and output token counts from provider usage metadata;
- model-call count, wall-clock time, estimated API cost, and task outcome;
- optimization settings and the unoptimized comparison;
- exact task prompt and test fixture identifier.

The current test suite verifies deterministic compression behavior and records provider usage when a response includes usage metadata. It does not fabricate token savings or cost.

## Live endpoint checks

| Date | Endpoint | Result | Tokens | Cost |
|---|---|---|---:|---:|
| 2026-11-17 | Local OmniRoute `http://127.0.0.1:20128/v1/models`, no key | Connection refused; OmniRoute was not running. No model was selected and no inference request was sent. | 0 | $0 |
| 2026-11-18 | Local OmniRoute `/v1/models` with a locally generated gateway token | HTTP 200; 465 models discovered. Nine were explicitly advertised as free. No upstream provider key or payment method was used. | 0 | $0 |
| 2026-11-18 | `auto/best-free` chat completion through OmniRoute | **Success**. Actual response received from `zai-org/glm-5.2`: `OMNI-X free inference works.` | 75 prompt / 124 completion / 199 total | $0 estimated |
| 2026-11-18 | OmniRoute provider fallback during first inference attempt | **Expected failure handling observed**: Cloudflare route reported missing Playwright/Chromium; UncloseAI route returned HTTP 401 because its public beta/key registration was closed. After installing the supported Chromium runtime, the next request succeeded. | 0 | $0 |
| 2026-11-18 | OMNI-X agent write-tool run in isolated `.omnix-live` workspace | **Success** with an explicit test approver: the live model emitted a compatibility write call and `live_probe.txt` was created with the verified content. Normal CLI mode still prompts for approval and refused to proceed non-interactively. | Provider usage recorded in local task store | $0 estimated |

The first row is a real historical probe. The later rows are live execution evidence. The no-key result is specifically an unauthenticated upstream route exposed by OmniRoute; the local gateway itself used a loopback-only token stored by OMNI-X's secure credential store.

## Autonomous repair evidence — 2026-11-18

Temporary workspace: ignored `.omnix-phase2-repair/`; write and command permissions were explicitly approved by the test harness. Provider/model: OmniRoute / `auto/best-free`; mode: `FREE`; estimated cost: `$0`.

- The agent read the deliberately broken `calculator.py` and `test_calculator.py`.
- It identified and corrected subtraction/addition and division-by-zero handling via `write_file`.
- It ran `python -m unittest -v`, read the actual output (`Ran 5 tests ... OK`), and reran the tests after the repair; both observed test outputs passed all five tests.
- The runtime recorded 10 model calls, 1 narrative-without-call retry, 8 tool results (reads, write, and test commands), and task state `completed`.
- Recorded token totals: 19,282 prompt tokens and 3,513 completion tokens across 10 usage rows; every row had estimated cost `$0`.
- Measured provider-call latency ranged from 5.9 seconds to 136.8 seconds; the 136.8-second call was a real provider delay, not a fabricated benchmark.

The preceding failed attempts are also evidence: repeated non-executable model prose and a transient OmniRoute fallback ending in an UncloseAI HTTP 401 were recorded as retries/failures. They were not counted as successful autonomous completion.

## Backend integration verification — 2026-11-18

The unified runtime now delegates its task loop to `HermesExecutionBackend`, an
adaptation of Hermes Agent's conversation-loop and tool-executor boundaries.
Two previously unseen deterministic tasks passed through that backend: workspace
inspection (directory listing followed by an evidence-based response) and a
write/read task (approval-gated file creation followed by read-back verification).
No prompt-word or benchmark-specific task detection is used. The full automated
suite passed with 24 tests on Windows.

## Hermes adapter live inference — 2026-11-18

With the local gateway reachable, OMNI-X ran the unified Hermes execution
adapter using OmniRoute `auto/best-free` in `FREE` mode (`allow_paid=false`).
The actual response was `OMNI-X Hermes backend live inference verified.` The
task completed with one provider call, 552 prompt tokens, 61 completion tokens,
10.3 seconds measured latency, and estimated cost `$0.00`. The event trace
recorded `verified` followed by `completed`; no direct provider credential was
used.

The installed Hermes browser live test also passed on Windows: the actual
`tools/browser_use_cli.py` implementation opened Chromium, navigated from
`example.com` to IANA's example page, returned page metadata, captured a
screenshot into Hermes's managed browser workspace, shut down all sessions via
`tools/browser_session_lifecycle.py`, and successfully restarted the browser.
## Task service Stage 1 — 2026-11-18

- Windows 11: `py -m pytest tests/test_task_service.py` — 3 passed.
- A recurring interval schedule created and completed a persisted job using the OMNI-X task service.
- Restart recovery converted an abandoned running job back to queued; cancellation persisted as cancelled.
- Delegated child records completed independently under the same service.
- These tests use a deterministic local executor and are lifecycle evidence, not live model-inference evidence.

## Background worker Stage 2 — 2026-11-18

- Windows 11 task-service suite: 4 passed.
- A fresh worker host reclaimed a queued SQLite job after the first host closed and completed it with the second host's executor.
- The detached CLI worker is policy-safe by default: it cannot prompt for approval, so sensitive tools remain denied unless an embedding host supplies an explicit approval boundary.
- Cooperative cancellation is validated; hard termination of an in-flight provider request remains a limitation.

## Delegation Stage 3 and end-to-end lifecycle — 2026-11-18

- Full Windows task-service suite: 5 task-service tests passed; repository suite: 33 passed, 2 skipped.
- End-to-end evidence: persistent schedule fired, background job executed an approval-gated real file tool, specialist child completed, parent aggregation completed, and a reopened SQLite store retained the parent/child history.
- Child policy assertion passed for `mode=FREE`, `allow_paid=false`, zero spending limit and inherited tool policy.
- This proves task lifecycle and permission inheritance with a local executor; it does not replace the separate live OmniRoute inference evidence already recorded above.

## Final backend validation — 2026-11-18

- Owned-process cancellation passed on Windows: an OMNI-X-owned command process was stopped and an unrelated process remained alive until independently cleaned up.
- `ToolRegistry.run_command` now polls owned processes, gives graceful cancellation first, then uses Windows `taskkill /PID <owned-pid> /T /F` only for that process tree. Hermes browser subprocesses use the same ownership boundary.
- Live multi-agent attempts through OmniRoute `auto/best-free` did not complete successfully: the gateway returned free-route 502/401 failures on two attempts, and one later attempt created real specialist child jobs and made independent child model calls but did not produce verifiable write-tool evidence before the parent timed out. Phase 2 live multi-agent validation remains incomplete.

