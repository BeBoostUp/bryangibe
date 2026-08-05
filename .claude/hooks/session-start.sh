#!/bin/bash
# SessionStart hook: inyecta el contexto maestro de Bryan en cada sesión de Claude Code,
# desde cualquier ordenador. Ejecuta síncrono para garantizar que el contexto está cargado
# antes de que empiece el trabajo.
set -euo pipefail

CONTEXT_FILE="${CLAUDE_PROJECT_DIR:-.}/.claude/CONTEXTO-BRYAN.md"

if [ ! -f "$CONTEXT_FILE" ]; then
  exit 0
fi

# Emitir el contenido como additionalContext (JSON escapado de forma segura con python3).
python3 - "$CONTEXT_FILE" <<'PY'
import json, sys
with open(sys.argv[1], encoding="utf-8") as f:
    content = f.read()
print(json.dumps({
    "hookSpecificOutput": {
        "hookEventName": "SessionStart",
        "additionalContext": content
    }
}))
PY
