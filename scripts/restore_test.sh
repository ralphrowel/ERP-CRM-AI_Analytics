#!/usr/bin/env bash
set -euo pipefail

# Automated Restore Drill Script for ERP/CRM (Roadmap §V1.9)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"

echo "Starting automated restore verification drill..."
"${PYTHON_BIN}" "${SCRIPT_DIR}/restore_test.py" "$@"
echo "Restore verification drill completed successfully."
