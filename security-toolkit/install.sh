#!/usr/bin/env bash
# Installs the authorized security-assessment team onto this machine.
# Default: user level (~/.claude) so it is available in every local project.
# Or:     ./install.sh --project /path/to/app   (installs into that project)
#
# Authorized testing only — use on apps you own or may test.
set -euo pipefail

SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"   # repo root
AGENTS_SRC="$SRC_DIR/.claude/agents"
CMDS_SRC="$SRC_DIR/.claude/commands"

DEST_ROOT="$HOME/.claude"
if [[ "${1:-}" == "--project" && -n "${2:-}" ]]; then
  DEST_ROOT="$2/.claude"
fi

if [[ ! -d "$AGENTS_SRC" || ! -d "$CMDS_SRC" ]]; then
  echo "ERROR: run this from inside the ditri12 repo (cannot find .claude/agents)." >&2
  exit 1
fi

mkdir -p "$DEST_ROOT/agents" "$DEST_ROOT/commands"
cp -f "$AGENTS_SRC"/*.md "$DEST_ROOT/agents/"
cp -f "$CMDS_SRC"/security-assessment.md "$DEST_ROOT/commands/"

echo "Installed security-assessment team to: $DEST_ROOT"
echo "  agents:   $(ls -1 "$DEST_ROOT/agents" | grep -c reviewer) reviewers"
echo "  command:  /security-assessment"
echo
echo "Next: open a session in your project folder and run /security-assessment"
echo "  cd \"/path/to/Lifegene\" && claude   # then: /security-assessment"
