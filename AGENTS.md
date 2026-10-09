# Workspace Guidelines & Conventions

## Shell & Terminal Commands
- **Environment**: PowerShell on Windows.
- **Line Continuation**:
  - **NEVER** use bash-style backslashes (`\`) for multi-line terminal commands proposed to the user.
  - In PowerShell, `\` is treated as a literal argument or directory separator, resulting in errors such as `fatal: \: '\' is outside repository`.
  - Always output terminal commands as clean, single-line commands, or use PowerShell backticks (`` ` ``) if multi-line is necessary.
- **Git Operations**:
  - Provide ready-to-run single-line PowerShell commands for `git add`, `git commit`, and `git push`.
