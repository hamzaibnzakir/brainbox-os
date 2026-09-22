# Brainbox OS

A local first personal AI operating system for one user.

Goal: run primarily on the user's PC, respond quickly, learn workflows over time, connect to tools through MCP, maintain external memory, anticipate safe work while a request is still being formed, and improve itself through controlled evaluation and fine tuning.

Architecture

User -> streaming input -> fast local reflex -> memory/MCP/main reasoner -> verifier/policy -> execution -> experience log -> evaluation -> training -> candidate model -> promotion or rollback.

The first reflex candidate is Needle 3 because the current open source release is designed for local tool calling, structured extraction, retrieval, embeddings and LoRA fine tuning.

We will benchmark it against small Qwen class models and other open decision models before choosing a production reflex model.

V1 rules

* Do not train a foundation model from scratch.
* Do not put all personal knowledge into model weights.
* Do not give the model unrestricted self modification.
* Do not allow speculative execution of destructive actions.
* Do not expose credentials to the model when a scoped MCP tool can hide them.

Current phase: architecture and local tool calling prototype.

See docs/ROADMAP.md and docs/ARCHITECTURE.md.
