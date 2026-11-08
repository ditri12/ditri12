# Runbook — assessing Lifegene & the sales-rep visit system

Both projects live on your computer, so run the team **locally**, where the
code already is. Authorized testing only (your own apps).

## 1. Install the team once (one command)

Clone or pull this repo on your machine, then from inside it:

**macOS / Linux / WSL / Git Bash**
```bash
./security-toolkit/install.sh          # installs to ~/.claude (all projects)
```

**Windows PowerShell**
```powershell
.\security-toolkit\install.ps1
```

This copies the 8 reviewer agents and the `/security-assessment` command into
`~/.claude`, so they are available in every project session on this machine.

## 2. Run on the Lifegene site

```bash
cd "/path/to/Lifegene"     # the "אתר חדש ל-Lifegene" folder
claude
```
In the session:
```
/security-assessment
```
The team reviews the code and writes a consolidated report to
`security-toolkit/reports/report-<date>.md` in that project (or prints it if
the toolkit folder is absent).

## 3. Run on the visit-management system

```bash
cd "/path/to/visit-management"   # "מערכת ניהול ביקורים לנציגי מכירות"
claude
/security-assessment
```

## What you get back, per issue
Verdict (vulnerable / not / needs manual check), the data that could be
read / modified / deleted and by whom, how it works, a minimal proof shown
only for your own environment, a concrete fix with code, and a severity.
Findings are sorted Critical → Info, with a prioritized fix list at the end.

## If you'd rather I run it from here
Either share the project folder via the Claude desktop app
(Settings → Claude Code → Remote Control) and tell me, or push each project to
a private GitHub repo and give me the name. Then I'll run the full team and
deliver the report from this session.
