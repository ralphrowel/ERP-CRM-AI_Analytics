# Terminal and Command Formatting Rules

- **Shell Environment**: The user's active shell is **PowerShell on Windows**.
- **Line Continuations**:
  - **NEVER** use Unix/Bash backslashes (`\`) for line breaks or line continuations in commands proposed to the user.
  - In PowerShell, `\` is treated as a literal character or path separator, which causes errors like `fatal: \: '\' is outside repository`.
  - Always provide terminal commands as either:
    1. Clean, single-line commands without line continuation characters, or
    2. PowerShell-native backticks (`` ` ``) if multi-line formatting is strictly necessary.
- **Git and CLI commands**:
  - Always write paths with standard forward slashes or escaped backslashes appropriate for PowerShell.
  - Prefer clean, single-line `git add`, `git commit`, and `git push` blocks so the user can easily copy and paste them directly into PowerShell without syntax errors.
