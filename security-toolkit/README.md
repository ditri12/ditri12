# Security Assessment Team (authorized testing only)

A reusable team of specialized security-review agents for assessing the
security of **your own** applications, APIs, and websites — code and systems
you own or have **explicit written permission** to test.

## Scope and legal boundary

- Use this only against targets you own or are explicitly authorized to test.
- The agents perform **code review and static analysis** by default, plus
  guidance for **dynamic testing you run yourself** against your own staging
  environment.
- Every finding is reported for **defensive** purposes: what is wrong, what
  data is at risk, and how to fix it.
- These agents will not generate working exploit payloads for third-party
  systems, help evade detection for malicious use, or target systems you do
  not control.

By running this toolkit you confirm you are authorized to test the target.

## The team

| Agent | Domain (OWASP-aligned) |
|-------|------------------------|
| `injection-reviewer`       | SQL/NoSQL/command/template/LDAP injection |
| `access-control-reviewer`  | Broken access control, IDOR, path traversal, privilege escalation |
| `auth-session-reviewer`    | Authentication, session & token management |
| `xss-client-reviewer`      | XSS, CSRF, clickjacking, client-side issues |
| `ssrf-redirect-reviewer`   | SSRF, open redirect, request forgery |
| `crypto-secrets-reviewer`  | Weak crypto, sensitive-data exposure, hardcoded secrets |
| `config-headers-reviewer`  | Security misconfiguration, headers, CORS, defaults |
| `logic-deps-reviewer`      | Business-logic flaws, vulnerable dependencies |

## How to run

In Claude Code, from the repository you want to assess:

```
/security-assessment
```

This orchestrates the whole team. Or launch a single specialist with the
Agent tool, e.g. "Use the access-control-reviewer agent on src/api".

## What each agent returns

For every issue, in the shared report format (`reports/REPORT_TEMPLATE.md`):

1. **Verdict** — was a weakness found (and, for dynamic tests you ran,
   whether it was confirmed exploitable in your own environment).
2. **Impact** — which data could be read, modified, or deleted, and by whom.
3. **How** — the vulnerable code path / request, with a minimal
   proof-of-concept scoped to your own system.
4. **Fix** — concrete remediation with a code example.
5. **Severity** — Critical / High / Medium / Low / Info.
