# Third-party notices

## Hermes Agent execution adapter

OMNI-X includes an adapted execution boundary and tool-call bridge from the Hermes Agent
from [NousResearch/hermes-agent](https://github.com/NousResearch/hermes-agent),
specifically the XML/bare-JSON tool-call contract from
`agent/acp_openai_bridge.py`.

Hermes Agent is licensed under the MIT License, copyright © 2025 Nous Research.
The adaptation includes the bounded conversation-loop and tool-executor
boundaries used by OMNI-X's `HermesExecutionBackend`; OMNI-X retains its own
branded runtime, provider routing, SQLite store, tool registry, approval policy,
and secure credential handling. Optional Hermes browser, scheduler, background
review, and delegated-worker services are not represented as integrated.

When `OMNIX_HERMES_SOURCE` is explicitly configured, OMNI-X also invokes
Hermes's `tools/browser_use_cli.py` for browser tasks and reads selected Hermes
`SKILL.md` trees. Those paths remain subject to OMNI-X approval and allowlist
controls; the MIT copyright and licence above apply to the reused source.
