# OMNI-X Benchmarks

No performance numbers are claimed yet. This file defines the evidence required for reproducible measurements.

Each benchmark run must record:

- commit SHA and Python version;
- provider, model, mode, and whether the run was live or local;
- input and output token counts from provider usage metadata;
- model-call count, wall-clock time, estimated API cost, and task outcome;
- optimization settings and the unoptimized comparison;
- exact task prompt and test fixture identifier.

The current test suite verifies deterministic compression behavior and records provider usage when a response includes usage metadata. It does not fabricate token savings or cost. A live benchmark is blocked until a valid provider credential and a user-approved model budget are available.
