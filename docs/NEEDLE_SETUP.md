# Needle 3 setup

The official cactus-compute/needle repository currently exposes the cactus-needle Python package.

Runtime:

    pip install cactus-needle

Training:

    pip install "cactus-needle[train]"

GPU training on CUDA:

    pip install "cactus-needle[train,gpu]"

The official CLI supports:

    needle finetune data.jsonl --epochs 3
    needle build --lora checkpoints/needle_lora.safetensors --out tuned.cact

The data format is JSONL with a query, tool schemas and expected answers. We will not start fine tuning until the baseline tool selection benchmark is passing.

For the first experiment, use a small fake tool catalogue and no production credentials.

Reference:
https://github.com/cactus-compute/needle
