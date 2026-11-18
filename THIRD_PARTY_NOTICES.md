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
