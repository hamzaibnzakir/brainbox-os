# Experiments

## E001 Needle 3 baseline

Measure cold start, warm latency, tokens per second, tool selection exact match, argument exact match, no tool accuracy, invalid tool rate and confidence calibration.

Hardware target: local Windows PC.

## E002 Needle versus tiny Qwen

Same tool catalogue and same test set. Compare latency and correctness.

## E003 Personal tool tuning

Create 500 to 2,000 synthetic and real anonymized tool examples. Fine tune a LoRA adapter and compare against the base model.

## E004 Anticipatory execution

Measure time saved, cancelled speculation, wrong speculation, wasted work and perceived latency.

Never include destructive tools in the first experiment.
