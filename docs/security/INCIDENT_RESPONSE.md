# OMNI-X incident response

This runbook is an engineering baseline, not legal advice.

## Detect and preserve

Record UTC time, affected version, environment, task/session IDs and the
smallest necessary logs. Preserve SQLite and process evidence. Do not delete,
rewrite or publish evidence to hide an incident. Redact credentials, tokens and
unnecessary personal data.

## Contain

Stop affected tasks, disable the integration or skill, isolate the provider or
sidecar, and revoke/rotate exposed credentials. Do not disable security logging
or terminate unrelated processes. Keep the rollback artifact available.

## Assess and notify

Identify affected users, data categories, providers, subprocessors and time
window. The owner/legal lead decides whether UK GDPR/DPA 2018, PECR, contract,
provider or other notification duties apply. Potential UK GDPR personal-data
breaches require prompt assessment against the applicable ICO deadline; do not
make a legal conclusion from this runbook alone.

## Recover and learn

Patch the root cause, restore from a verified backup if needed, test the fix in
an authorised environment, and record residual risk and owner approval. Update
the threat model, integration register, tests and release checklist.

## Contacts to supply before launch

- Incident owner: TBD
- Security disclosure route: TBD
- Data-protection/legal lead: TBD
- Provider and hosting contacts: TBD
- Recovery authority and backup owner: TBD
