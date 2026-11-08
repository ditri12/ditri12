---
description: Run the full security-assessment team against a codebase you own or are authorized to test, and produce a consolidated report.
---

# Security assessment (authorized targets only)

Coordinate a defensive security review of **this repository** (or the path the
user names). Proceed only if the user owns or is authorized to test the target;
if unclear, confirm authorization first.

## Steps

1. **Scope.** Identify the stack, entry points (routes/handlers/CLI), data
   stores, auth model, and any user-input boundaries. Note the target and
   scope at the top of the report.

2. **Dispatch the team.** Launch these agents in parallel with the Agent tool,
   each on the relevant paths:
   - `injection-reviewer`
   - `access-control-reviewer`
   - `auth-session-reviewer`
   - `xss-client-reviewer`
   - `ssrf-redirect-reviewer`
   - `crypto-secrets-reviewer`
   - `config-headers-reviewer`
   - `logic-deps-reviewer`

3. **Consolidate.** Merge findings into one report using
   `security-toolkit/reports/REPORT_TEMPLATE.md`. De-duplicate, assign
   severities, and sort Critical → Info. Save it to
   `security-toolkit/reports/report-<date>.md`.

4. **For each finding report:** verdict (vulnerable / not / needs manual
   confirmation), the data that could be read/modified/deleted and by whom,
   how it works (vulnerable path), a minimal PoC **for the user's own
   environment only**, and a concrete fix with a code example.

5. **Prioritize.** End with a ranked remediation list (biggest risk first) and
   quick wins.

## Boundaries
- Defensive output only. No weaponized exploits for third-party systems, no
  detection-evasion for malicious use, no testing of systems the user does not
  control.
- Static review by default. Any dynamic test is something the **user** runs
  against their **own** staging environment; provide safe, non-destructive
  steps.
- Never print secret values — report their location and advise rotation.
