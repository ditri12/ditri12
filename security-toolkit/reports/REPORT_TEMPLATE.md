# Security Assessment Report

- **Target:** <repo / app / URL you own or are authorized to test>
- **Date:** <date>
- **Assessor:** <you> (authorized)
- **Scope reviewed:** <paths / endpoints>

## Summary

| Severity | Count |
|----------|-------|
| Critical |       |
| High     |       |
| Medium   |       |
| Low      |       |
| Info     |       |

Overall verdict: <e.g. "2 High findings allow reading other users' records">

## Findings

### [SEVERITY] <short title> — <domain>

- **Verdict:** Vulnerable / Not vulnerable / Needs manual confirmation
- **Location:** `path/to/file:line` (and/or endpoint `METHOD /route`)
- **Data at risk:** what could be read / modified / deleted, and by which actor
- **How it works:** the vulnerable code path or request flow
- **Proof of concept (own environment only):**
  ```
  <minimal request/input demonstrating the issue on YOUR system>
  ```
- **Fix:** concrete remediation
  ```
  <corrected code snippet>
  ```
- **References:** OWASP / CWE ids

<repeat per finding>

## Recommended priorities

1. ...
2. ...
