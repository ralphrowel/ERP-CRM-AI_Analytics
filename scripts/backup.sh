#!/usr/bin/env bash
set -euo pipefail

# Automated Backup Script for ERP/CRM (Roadmap §V1.9)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"

echo "Starting automated nightly backup..."
"${PYTHON_BIN}" "${SCRIPT_DIR}/backup.py" "$@"
echo "Backup execution completed successfully."
