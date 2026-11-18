# Third-party notices

## Hermes Agent compatibility bridge

OMNI-X includes a small adapted portion of the Hermes Agent tool-call bridge
from [NousResearch/hermes-agent](https://github.com/NousResearch/hermes-agent),
specifically the XML/bare-JSON tool-call contract from
`agent/acp_openai_bridge.py`.

Hermes Agent is licensed under the MIT License, copyright © 2025 Nous Research.
The adaptation is limited to parsing and prompt-contract compatibility; OMNI-X
retains its own branded runtime, provider routing, SQLite store, tool registry,
approval policy, and secure credential handling.
