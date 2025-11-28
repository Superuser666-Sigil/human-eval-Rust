# SigilDERG Ecosystem Integration

## Overview

HumanEval Rust is the evaluation component of the SigilDERG ecosystem for Rust code generation:

```
┌─────────────────────┐     ┌─────────────────────┐     ┌─────────────────────┐
│  sigil-pipeline     │ ──▶ │  sigilderg-finetuner│ ──▶ │  human-eval-rust    │
│  Dataset Generation │     │  Model Fine-tuning  │     │  Model Evaluation   │
└─────────────────────┘     └─────────────────────┘     └─────────────────────┘
```

| Package | Purpose | PyPI |
|---------|---------|------|
| `sigil-pipeline` | Generate Rust code datasets from crates | [link](https://pypi.org/project/sigil-pipeline/) |
| `sigilderg-finetuner` | Fine-tune LLMs on Rust code | [link](https://pypi.org/project/sigilderg-finetuner/) |
| `human-eval-rust` | Evaluate Rust code generation | [link](https://pypi.org/project/human-eval-rust/) |

---

## Installation

### Full Ecosystem

```bash
pip install sigil-pipeline[ecosystem]
```

### Individual Packages

```bash
pip install sigil-pipeline      # Dataset generation
pip install sigilderg-finetuner # Fine-tuning
pip install human-eval-rust     # Evaluation
```

### Evaluation Integration Only

```bash
pip install sigilderg-finetuner[evaluation]
```

---

## Complete Workflow

### Step 1: Generate Training Data

Use sigil-pipeline to create training datasets:

```bash
python -m sigil_pipeline.main \
    --crate-list data/crate_list.txt \
    --prompt-mode instruct \
    --output datasets/phase2_full.jsonl
```

### Step 2: Fine-Tune Model

Use sigilderg-finetuner with the generated data:

```yaml
# configs/llama8b-phase2.yml
model_name: "meta-llama/Meta-Llama-3.1-8B-Instruct"
dataset:
  names:
    - local:datasets/phase2_full.jsonl
train:
  num_steps: 12000
  lr: 1.0e-4
```

```bash
sigilderg-train configs/llama8b-phase2.yml
```

### Step 3: Generate Completions

Use the trained model to generate HumanEval completions:

```python
from human_eval.data import read_problems, write_jsonl, get_human_eval_dataset
from transformers import AutoTokenizer
from peft import AutoPeftModelForCausalLM
import torch

# Load model
model = AutoPeftModelForCausalLM.from_pretrained(
    "Superuser666-Sigil/Llama-3.1-8B-Instruct-Rust-QLora/checkpoint-9000",
    torch_dtype=torch.bfloat16,
    device_map="auto",
)
tokenizer = AutoTokenizer.from_pretrained(model.config._name_or_path)

# Generate completions
problems = read_problems(get_human_eval_dataset())
samples = []

for task_id, problem in problems.items():
    inputs = tokenizer(problem["prompt"], return_tensors="pt")
    outputs = model.generate(**inputs, max_new_tokens=512, temperature=0.2)
    completion = tokenizer.decode(outputs[0][inputs.input_ids.shape[1]:])
    samples.append({"task_id": task_id, "completion": completion})

write_jsonl("samples.jsonl", samples)
```

### Step 4: Evaluate

```bash
evaluate_functional_correctness samples.jsonl
```

Output:
```
{'pass@1': 0.42, 'pass@10': 0.68, 'compile_rate': 0.78, 'main_free_rate': 0.95}
```

---

## Format Compatibility

### Pipeline Output → Finetuner Input

Pipeline generates:
```json
{"prompt": "Write a Rust function...", "gen": "pub fn example() {...}"}
```

Finetuner expects `text` field. Use `local:` prefix to auto-convert:
```yaml
dataset:
  names:
    - local:datasets/phase2_full.jsonl
```

### Finetuner Output → Evaluation Input

Generated completions should be in format:
```json
{"task_id": "HumanEval/0", "completion": "..."}
```

### Format Conversion

```python
from sigil_pipeline.converters import prompt_gen_to_eval_format

# Convert pipeline format to evaluation format
prompt_gen_to_eval_format(
    jsonl_path="samples.jsonl",
    output_path="samples_eval.jsonl",
    task_id_prefix="rust_task"
)
```

---

## Unified CLI

The `sigil-ecosystem` command orchestrates the full workflow:

```bash
sigil-ecosystem \
    --crate-list data/crate_list.txt \
    --dataset-path datasets/phase2_full.jsonl \
    --config-path configs/llama8b-phase2.yml \
    --output-dir out/llama8b-rust-qlora
```

Options:
- `--no-generate-dataset`: Skip dataset generation
- `--no-fine-tune`: Skip fine-tuning
- `--no-evaluate`: Skip evaluation

---

## Metrics Flow

### Evaluation Metrics

| Metric | Description |
|--------|-------------|
| `pass@k` | Probability of at least one passing sample in k attempts |
| `compile_rate` | Fraction of completions that compile |
| `main_free_rate` | Fraction without `fn main()` |
| `clippy_pass_rate` | Fraction passing Clippy |
| `avg_compile_time_ms` | Average compilation time |
| `avg_binary_size_bytes` | Average binary size |

### Per-Sample Results

```json
{
  "task_id": "HumanEval/0",
  "completion": "...",
  "compile_ok": true,
  "test_ok": true,
  "clippy_ok": true,
  "error_type": null,
  "passed": true
}
```

---

## Lambda Package Integration

For remote evaluation on Lambda Labs instances:

```bash
# Setup (on Lambda instance)
./lib/sigilderg.sh setup

# Run evaluation
./lib/sigilderg.sh evaluate samples.jsonl
```

The lambda-package includes:
- Pre-configured H100 optimizations
- 24 parallel workers
- 10s timeout
- Firejail sandboxing

---

## Troubleshooting

### "human-eval-rust not available"

```bash
pip install human-eval-rust
# or
pip install sigil-pipeline[ecosystem]
```

### Format Mismatch

Ensure completions have `task_id` and `completion` fields:
```python
# Correct
{"task_id": "HumanEval/0", "completion": "fn add(a: i32, b: i32) -> i32 { a + b }"}

# Wrong
{"prompt": "...", "gen": "..."}  # Pipeline format, needs conversion
```

### Model Loading Errors

```python
# Explicitly prevent TensorFlow loading
model = AutoPeftModelForCausalLM.from_pretrained(
    model_name,
    from_tf=False,
    use_safetensors=True,
)
```

---

## Links

- **Pipeline**: https://github.com/Superuser666-Sigil/SigilDERG-Data_Production
- **Finetuner**: https://github.com/Superuser666-Sigil/SigilDERG-Finetuner
- **Evaluation**: https://github.com/Superuser666-Sigil/human-eval-Rust
- **Lambda Package**: https://github.com/Superuser666-Sigil/lambda-package

