# Needle 3 setup

Brainbox OS uses **Needle 3 as its local reflex model**. Needle handles fast tool selection, structured extraction and local routing. It is not the main general reasoning model. The Brainbox harness stays in charge of permissions, execution, verification, cancellation and audit logs.

The official Needle package is `cactus-needle`. Its current Python API supports `needle.Needle(...)`, local `.cact` weights, tool calling, confidence and a full tool loop. The base `needle3.cact` weights are fetched from Hugging Face and can be cached locally. citeturn0search1

## Windows

```powershell
.\scripts\setup_needle.ps1
```

## Linux/macOS

```bash
./scripts/setup_needle.sh
```

The setup installs Brainbox OS with the Needle extra and downloads:

```text
models/needle3.cact
```

The base model binary is included in this private repository at models/needle3.cact so a clone contains the local reflex model immediately. Future tuned models should remain outside Git unless explicitly promoted.

## Python usage

```python
from brainbox_os.needle_reflex import NeedleReflex

reflex = NeedleReflex(tools=[...])
result = reflex.decide("check my GitHub notifications", tools=[...])
```

For the full agent loop:

```python
result = reflex.run("check my GitHub notifications")
```

Needle's `run()` executes declared Python tools itself. In Brainbox OS, production execution should instead flow through the harness so policy, confirmation, MCP permissions and verification remain centralized. The current Needle API also exposes confidence and an escalation signal for routing low confidence requests to the main reasoner. citeturn0search3

## Fine tuning later

Needle 3 supports local LoRA fine tuning and export to a `.cact` model. Keep personal knowledge in external memory. Fine tune behavior, tool usage, routing and Brainbox specific workflows rather than trying to store the user's entire memory inside the weights. citeturn0search6
