# Safety model

The AI may be autonomous only inside explicit boundaries.

READ: read, search, inspect, list and fetch.

PREPARE: connect, load, calculate, stage reversible work.

WRITE: modify files, create commits and update records.

EXTERNAL: send messages, publish, deploy, purchase or change public resources.

DESTRUCTIVE: delete, revoke, overwrite critical infrastructure or run destructive shell commands.

Default policy: READ and PREPARE may be automated. WRITE is policy evaluated. EXTERNAL and DESTRUCTIVE require explicit confirmation unless a future user policy explicitly permits them.

Self improvement may generate code and training candidates but may not silently promote them. Every candidate needs an isolated branch, tests, evaluation report, diff and rollback point.

Never place API keys, tokens, cookies, SSH keys or credentials in model context. MCP servers should perform authenticated actions on behalf of the model.
