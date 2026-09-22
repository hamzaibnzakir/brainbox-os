# Development rules

1. Keep the core harness provider agnostic.
2. Keep credentials outside model context.
3. Add tests for routing and safety changes.
4. Never allow speculative execution of destructive actions.
5. Record latency and correctness for model changes.
6. Treat model upgrades as experiments with rollback.
