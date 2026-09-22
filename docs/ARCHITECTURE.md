# Architecture

## Reflex

Fast local model for bounded decisions: intent, tool retrieval, argument extraction, model routing, risk, confirmation, anticipation eligibility and task completion.

## Main reasoner

Used for multi step reasoning, coding, research, planning and complex orchestration.

## Harness

Owns state, permissions, tool execution, retries, verification, cancellation and audit logs. The model proposes actions. The harness decides whether and how an action is executed.

## Memory

Personal knowledge stays external to model weights.

Categories: stable preferences, projects, active tasks, decisions, technical environment, documents, tool relationships and episodic experience.

## MCP

Initial target integrations: GitHub, VPS, browser, files, Google services and custom Brainbox services.

## Anticipation

Only reversible or preparatory operations may begin from partial input.

Allowed: connect, read, search, load, prepare, fetch, inspect.

Confirmation required before delete, publish, deploy, send, purchase, credential changes and destructive shell commands.

## Evolution

Meaningful actions produce experience records. Records become training examples. Candidate adapters are tested against a fixed evaluation suite before promotion. Failed candidates roll back.
