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
suite passed with 22 tests on Windows.
