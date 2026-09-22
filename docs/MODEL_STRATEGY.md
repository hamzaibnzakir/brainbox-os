# Model strategy

## Reflex model

Initial candidate: Needle 3.

The current official repository describes Needle 3 as a 29M to 121M parameter on device model for tool calling, structured extraction and embeddings, with tool retrieval and LoRA fine tuning/export.

We will benchmark before locking it in.

## General model

Use an adapter so the main reasoner can switch between local Qwen class models, other local open models and cloud models.

## Personalization

Fine tune behavior, not volatile personal facts.

Weights should learn tool usage, preferred workflows, terminology, routing behavior, safety behavior and common task patterns.

Memory should contain current projects, changing infrastructure, recent conversations, documents, active goals and current configuration.

## Long context

A huge personal knowledge base does not require a 2M token context window in the reflex model. Use retrieval and hierarchical memory. A future long context reasoner can consume larger assembled context when necessary.
