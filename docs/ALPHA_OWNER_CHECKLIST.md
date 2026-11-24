# OMNI-X Windows alpha owner checklist

This checklist is for owner review. It does not publish, merge or deploy
anything.

## Candidate identity

- Source branch: `codex/alpha-candidate`
- Source commit: record the exact commit from the workflow artifact
- Version: `0.1.0-alpha`
- Installer: hosted Windows Desktop workflow artifact `omnix-windows-installer-*`
- Signing: development artifact is unsigned unless the workflow explicitly reports a certificate
- SHA-256 and byte size: record from the downloaded artifact before distribution

## Verified gates

- Python regression suite: hosted security/CI gate passed at the recorded head.
- TypeScript production build: passed locally on the recorded head.
- Rust formatting: passed locally; hosted Windows compilation is the authoritative packaging gate.
- Installer lifecycle: require install, launch, authenticated health, owned sidecar shutdown and silent uninstall.
- Live provider inference: unverified unless a real response is recorded for this exact candidate.

## Owner approval before distribution

1. Download the artifact from the successful Windows Desktop workflow.
2. Verify the SHA-256 against the value recorded in the release evidence.
3. Review the unsigned-build warning and test only on an authorised Windows 11 environment.
4. Confirm the known limitations in `docs/RELEASE_NOTES_v0.1.0-alpha.md`.
5. Approve any GitHub PR, release draft or website deployment separately.

## If GitHub write access is unavailable

Create the draft PR manually at:

https://github.com/e9aj/omni-x/compare/main...codex/alpha-candidate?expand=1

Suggested title: `feat: prepare OMNI-X Windows alpha candidate`

Use the verified test evidence, installer checksum, security limitations and
the explicit statement that no production release is being published.
