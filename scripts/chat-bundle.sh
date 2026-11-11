#!/usr/bin/env bash
# Collect the files to upload as knowledge in a Claude chat project (see "Use it in Claude chat" in README.md).
# Output: dist/claude-chat/ (flat folder, git-ignored). Contains docs only, no personal data.
set -euo pipefail
cd "$(dirname "$0")/.."

out=dist/claude-chat
rm -rf "$out"
mkdir -p "$out"
cp claude-chat/project-instructions.md \
   docs/mcp-reference.md docs/garmin-reference.md docs/course-json.md docs/coaching-science.md \
   .claude/skills/run-coach/references/decision-process.md \
   .claude/skills/run-coach/references/periodization.md \
   .claude/skills/run-coach/references/session-library.md \
   scripts/readiness.py \
   .claude/skills/run-workout/examples/*.json \
   "$out/"
echo "→ $out/ ($(find "$out" -type f | wc -l | tr -d ' ') files)"
echo "  1. paste project-instructions.md into the project's instructions"
echo "  2. upload all the other files to the project's knowledge"
