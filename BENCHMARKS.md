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
- Concrete partial live trace: parent job `aa2d285a-cbd3-4e1b-8769-65fbe676b108` created specialist job `5aa0011d-e51d-4334-81bf-808ffc802db7` through `delegate_task`; both used OmniRoute model `auto/best-free`, FREE mode, `allow_paid=false`, `$0` limit, and the approved tool policy. The child reached terminal `completed` after independent model calls, but its recorded result was only `Tool call: read_file(path="delegated_result.txt")`; the file was not created, so the parent was not credited with successful autonomous completion. A companion attempt created `bd8a2e57-408d-4921-9dce-060928eb699e`; its result was a textual `write_file` claim without tool evidence. Usage rows recorded prompt/completion pairs including `16064/167`, `15992/172`, `16132/823`, `16262/202`, `16362/462`, `15992/111`, `16169/168`, `16337/229`, and `16679/517` tokens; provider-call latencies ranged from 5.4s to 98.7s. These are real failure/partial results, not completion evidence.
- The later single-agent probe failed before inference with a recorded OmniRoute timeout (`45,050.4ms`, no usage row); unavailable Groq/Cerebras credentials were excluded from fallback. This confirms the current live blocker is also upstream availability, distinct from the corrected parser/runtime defects.

## Free-model catalogue and bounded health probes — 2026-11-18

Using the authenticated local OmniRoute `/v1/models` endpoint, OMNI-X observed 453 catalogue entries and nine explicitly free entries. The explicitly free set was: `auto/best-free`, `auto/coding:free`, `ddgw/gpt-5.4-mini`, `ddgw/gpt-5.6-luna`, `ddgw/claude-haiku-4-5`, `ddgw/mistral-small-2603`, `ddgw/tinfoil/gpt-oss-120b`, `ddgw/tinfoil/gemma4-31b`, and `unc/turboderp/Qwen3.8-27B-exl3`. The gateway metadata declared `combo`/400000 context/tool calling for both auto routes, DDG zero pricing and no declared tool calling for the DDG routes, and `uncloseai`/65536 context/tool calling for the Qwen route. The local gateway credential was read from secure storage and was not written to logs or source.

The bounded probe selected the two declared tool-capable auto routes plus the Qwen route (two concurrent workers; one minimal request per route). Results persisted in the local `model_health` table:

| Model | Upstream | Result | Tokens | Latency | Tool probe |
|---|---|---|---:|---:|---|
| `auto/best-free` | `combo` | real response received | 110 / 112 | 9138ms | no executable call; unverified |
| `auto/coding:free` | `combo` | real response received | 110 / 76 | 8517ms | no executable call; unverified |
| `unc/turboderp/Qwen3.8-27B-exl3` | `uncloseai` | HTTP 401; public beta closed | 0 / 0 | 468ms | not attempted |

No paid route was used. The two auto routes are usable for text inference, but this run does not provide evidence that either is reliable for autonomous tool execution. OMNI-X's FREE router consequently excludes the tested-unavailable Qwen route, records the auto routes as available but tool-unverified, and will not claim a verified live tool workflow from this probe alone.

## Controlled tool-call investigation — 2026-11-18

The same minimal native OpenAI-compatible request was sent directly to the local OmniRoute gateway and once through `ModelClient`. The direct response was sanitized to fields only and contained:

`model=zai-org/glm-5.2`, `finish_reason=stop`, `tool_calls=null`, `content=tool_call({ "name": "list_directory", "arguments": { "path": "." } })`, usage `122 prompt / 99 completion`.

The separate OMNI-X client request contained:

`model=zai-org/glm-5.2`, `finish_reason=stop`, `tool_calls=null`, `content=list_directory(path=".")`, usage `122 prompt / 113 completion`.

These were separate free-model calls, so the differing textual forms demonstrate nondeterministic/provider formatting rather than client-side loss of a native `tool_calls` field. In both cases OmniRoute returned no structured native tool call. A later real OMNI-X call returned `tool_calls: [{"name":"list_directory","arguments":"{}"}]` in assistant content; OMNI-X initially rejected it as narration. The compatibility bridge now strictly normalizes this anchored JSON-list form, as well as `tool_call({...})`, without parsing ordinary narrative.

Evidence after the fix:

- Real read-only task succeeded through `auto/best-free`: `list_directory` was invoked and returned `["probe.txt"]`; the task emitted a verified event. Two model calls recorded `15961/107` and `16122/127` tokens with observed latencies `5579.3ms` and `8293.6ms`.
- Real isolated file task succeeded: `write_file` created `verified.txt` with `SINGLE-LIVE-VERIFIED`, then the agent issued `read_file(filename: "verified.txt")`; the file content was verified. This run used model `zai-org/glm-5.2` and recorded two provider calls (`6886.1ms`, `5230.5ms`).
- One existing single-agent attempt failed to create the file, demonstrating free-model variability; it was not counted as success.
- Parent/child live validation was attempted once after the read-only gate but OmniRoute timed out at 45 seconds before the first parent model response. The failure recorded no child job and no model usage; direct credentialed Groq, Cerebras and Gemini fallbacks were correctly excluded. No repeated delegation retries were made.

Conclusion: the original defect was incomplete normalization of valid textual gateway formats, not evidence that OmniRoute strips structured calls in the client. Native structured function calling remains unverified for the selected free model; successful autonomous execution currently depends on the compatibility text formats.

## Parent/child timeout and prompt-size investigation — 2026-11-19

The previous live parent/child attempt failed before creating a child because OmniRoute timed out on the first parent request at approximately 45 seconds. The persisted job state was `failed`, with no child delegation row and no usage row. This is an upstream availability failure, not a child-result verification failure; no repeated expensive delegation retry was made.

The parent and child code paths already create separate sessions and do not copy the parent's SQLite message history into a child. The child receives its own system policy, relevant skills, full approved tool schema and only the delegated prompt. Parent waiting is now bounded separately from child execution: child jobs receive a persisted 2-request-window deadline (60–180 seconds), while the parent waits at most 3 request windows (45–180 seconds) before cancelling only that child.

Prompt telemetry identified the local cause of the approximately 32,000-token simple-task total. `relevant_instructions()` searched every skill body for any prompt token, so common words selected five large skills. For a comparable read-only fixture, OMNI-X measured:

| Fixture | OMNI-X estimated prompt | Provider prompt tokens | Tool schema chars | Outcome |
|---|---:|---:|---:|---|
| Before optimization | ~1,321 local chars/4 estimate; provider calls 15,961 and 16,091 | 15,965 and 16,091 in the earlier trace | 1,375 | tool execution was intermittent |
| After meaningful-token filtering | 1,321 and 1,333 estimated local tokens | 2,004 and 2,165 | 1,375 | read-only tool succeeded once |
| After skill-name-only filtering | 215 local estimated tokens | 524 in the bounded rerun | 1,375 | upstream returned `[list_directory]` text without an executable call; not counted as success |

The final reduction leaves the 712-character security/system policy and all seven approved tool schemas intact. Skills are still available when explicitly named by skill name (for example `review-code`), but unrelated skill bodies and duplicated conversation history are not injected.

## Release-candidate audit — 2026-11-19

- Complete local collection: 46 tests; 43 deterministic tests passed and 3 opt-in live-provider tests were skipped by default. Compileall, `pip check` and `git diff --check` passed.
- Hermes browser live test initially exposed a Windows Python compatibility defect (`Popen(capture_output=True)`). Replacing it with explicit `stdout=PIPE` and `stderr=PIPE` fixed the issue; the opt-in browser test then passed for navigation, screenshot, shutdown and restart recovery.
- Security review confirmed command and browser subprocesses are owned process trees; cancellation uses the captured PID/tree and does not match or terminate OmniRoute. Filesystem tools remain workspace-contained and sensitive tools remain approval-gated.
- FREE routing continues to reject paid-only providers/models when `allow_paid=false`; usage records estimated cost `$0.00` and child policy snapshots cannot broaden mode, spending or tool policy.
- The `[list_directory]` response observed after context reduction produced no `tool_result` event and was not treated as task evidence.

Release-candidate conclusion: suitable as a clearly labelled Phase 2 development baseline for review, not production-ready and not evidence of fully validated live multi-agent AI execution.

## Phase 3 desktop foundation — 2026-11-19

- `desktop/`: `npm install` completed with zero reported vulnerabilities;
  `npm run typecheck` and `npm run build` passed.
- Python suite including authenticated loopback bridge coverage: 44 passed,
  3 opt-in live tests skipped.
- Tauri/Rust build remains unvalidated because host Application Control blocks
  `cargo.exe`; no installer or production desktop readiness is claimed.
- Desktop bridge deterministic coverage now includes authenticated chat
  forwarding to the existing runtime, session ID return, origin rejection and
  stop/shutdown endpoints. The desktop UI has no fake model response and does
  not bypass backend approval policy. Live desktop chat remains unexecuted in
  this increment to avoid repeating unstable free-provider calls.
- Local `npm run tauri build` now passes Tauri configuration/version validation
  but cannot execute Rust build scripts because Code Integrity blocks unsigned
  generated executables. The hosted Windows build is the required compilation
  evidence; no installer is claimed until that run succeeds.

