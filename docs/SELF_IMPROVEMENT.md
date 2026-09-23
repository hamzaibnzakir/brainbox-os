# Self Improvement

Brainbox can extend its own capabilities and evaluate changes to its core code.

## Capability creation

The agent can call `create_tool` with a standalone Python function. Brainbox parses the source, rejects selected process/network/dynamic execution primitives, compiles it, and optionally tests it. `install_tool` places a validated capability in the user tool directory. Generated tools are discovered when Brainbox starts again.

Generated tools are deliberately separate from the Brainbox source tree. This keeps experimental capabilities from silently becoming part of the core runtime.

## Core code evolution

When a capability requires changing Brainbox itself, the agent can:

1. Produce a unified patch.
2. Call `validate_code_patch`.
3. Brainbox creates a detached Git worktree.
4. The patch is checked and applied only inside that worktree.
5. A restricted Python or pytest command runs there.
6. The evaluation report is saved under `artifacts/self_improvement`.
7. If evaluation passes, `promote_code_patch` can apply the same patch to the live checkout.
8. Live tests run after promotion.
9. A failing live test automatically reverses the patch.

The live checkout must be clean before promotion. This prevents Brainbox from overwriting unrelated human changes.

## Learning loop

```text
experience / failure
        ↓
identify missing capability
        ↓
create tool OR propose source patch
        ↓
static validation
        ↓
isolated evaluation
        ↓
promotion + live verification
        ↓
execution traces + memory
        ↓
future improvement candidate
```

This is intentionally different from unrestricted self rewriting. Brainbox can improve itself, but every core change has a candidate, an evaluation, a promotion step, and a rollback path.
