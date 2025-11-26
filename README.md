# HumanEval Rust: Evaluation Harness for SigilDERG Ecosystem

A specialized evaluation harness for assessing Rust code generation capabilities of language models, designed as a core component of the [SigilDERG ecosystem](https://github.com/Superuser666-Sigil) for Rust-focused AI development.

> 📖 **Ecosystem Architecture**: For a comprehensive overview of how this project integrates with [SigilDERG-Data_Production](https://github.com/Superuser666-Sigil/SigilDERG-Data_Production) and [SigilDERG-Finetuner](https://github.com/Superuser666-Sigil/SigilDERG-Finetuner), see [ARCHITECTURE.md](https://github.com/Superuser666-Sigil/SigilDERG-Data_Production/blob/main/ARCHITECTURE.md) in the Data Production repository.

## About the SigilDERG Ecosystem

This evaluation harness is part of an integrated pipeline for training and evaluating Rust code generation models:

1. **[SigilDERG-Data_Production](https://github.com/Superuser666-Sigil/SigilDERG-Data_Production)**: Generates high-quality, instruction-style Rust code datasets from real-world crates using static analysis and quality filters
2. **[SigilDERG-Finetuner](https://github.com/Superuser666-Sigil/SigilDERG-Finetuner)**: Fine-tunes language models (like Llama-3.1-8B-Instruct) on Rust code using QLoRA and multi-phase training strategies
3. **HumanEval Rust** (this project): Evaluates model performance on standardized Rust programming problems using the HumanEval benchmark format
4. **[sigil-mmf-codex-priv](https://github.com/Superuser666-Sigil/sigil-mmf-codex-priv)**: Additional components for the ecosystem

### Target Model

This evaluator is designed to work with fine-tuned Rust code generation models, particularly:
- **[Llama-3.1-8B-Instruct-Rust-QLora](https://huggingface.co/Superuser666-Sigil/Llama-3.1-8B-Instruct-Rust-QLora)**: A Phase 1 fine-tuned model produced using the SigilDERG Finetuner

## Installation

### Prerequisites

This package requires **Python 3.12.10 or later**. We recommend using a virtual environment:

```bash
# Using venv (recommended)
python3.12 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Or using uv (fast alternative)
uv venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
```

Install a Rust toolchain via [`rustup`](https://www.rust-lang.org/tools/install) and ensure a modern compiler with Edition 2021 support (Rust 1.56+; we recommend the latest stable toolchain):
```bash
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
rustup default stable
rustc --version
```

### Install from PyPI

```bash
pip install human-eval-rust
```

📦 **Package available on PyPI**: [https://pypi.org/project/human-eval-rust/](https://pypi.org/project/human-eval-rust/)

### Install Full Ecosystem

Install all three SigilDERG packages together:

```bash
pip install human-eval-rust[ecosystem]
```

Or install via the pipeline package:

```bash
pip install sigil-pipeline[ecosystem]
```

This installs:
- `human-eval-rust>=1.2.2`
- `sigil-pipeline>=1.2.1`
- `sigilderg-finetuner>=2.8.0`

### Install from source

```bash
git clone https://github.com/Superuser666-Sigil/human-eval-Rust.git
cd human-eval-Rust
pip install -e .
```

## Usage

**⚠️ Security Warning**: This program exists to run untrusted model-generated Rust code. Users are strongly encouraged not to do so outside of a robust security sandbox. Rust completions are compiled and executed via [`rust_execution.py`](human_eval/rust_execution.py); you should sandbox the Rust evaluator, because it builds binaries from untrusted code and runs their tests locally.

### Basic Evaluation Workflow

1. **Generate completions** from your model using the HumanEval Rust prompts
2. **Save samples** in JSONL format with `task_id` and `completion` fields
3. **Run evaluation** to get pass@k metrics and detailed results

### Example: Evaluating a Fine-Tuned Model

```python
from human_eval.data import read_problems, write_jsonl, get_human_eval_dataset
from transformers import AutoTokenizer, AutoModelForCausalLM
import torch

# Load your fine-tuned model (e.g., from HuggingFace)
model_name = "Superuser666-Sigil/Llama-3.1-8B-Instruct-Rust-QLora"
tokenizer = AutoTokenizer.from_pretrained(model_name)
model = AutoModelForCausalLM.from_pretrained(model_name)

# Load HumanEval Rust problems
rust_problems = read_problems(get_human_eval_dataset())

# Generate completions
samples = []
for task_id, problem in rust_problems.items():
    prompt = problem["prompt"]
    
    # Generate completion (adjust parameters as needed)
    inputs = tokenizer(prompt, return_tensors="pt")
    with torch.no_grad():
        outputs = model.generate(
            **inputs,
            max_new_tokens=512,
            temperature=0.2,
            do_sample=True,
        )
    completion = tokenizer.decode(outputs[0][inputs.input_ids.shape[1]:], skip_special_tokens=True)
    
    samples.append(dict(task_id=task_id, completion=completion))

# Save samples
write_jsonl("rust_samples.jsonl", samples)

# Evaluate
# Run: evaluate_functional_correctness rust_samples.jsonl
```

### Command-Line Evaluation

```bash
$ evaluate_functional_correctness rust_samples.jsonl
Reading samples...
164it [00:01, 1959.50it/s]
Running test suites...
100%|...| 164/164 [00:45<00:00,  3.62it/s]
Writing results to rust_samples.jsonl_results.jsonl...
100%|...| 164/164 [00:00<00:00, 42876.84it/s]
{'pass@1': 0.42, 'pass@10': 0.68, 'pass@100': 0.85}
```

The evaluator provides detailed results in `<input>_results.jsonl` with per-sample pass/fail status and execution results ("passed", "timed out", or "failed").

### Integration with SigilDERG Finetuner

The evaluation workflow integrates seamlessly with the [SigilDERG Finetuner](https://github.com/Superuser666-Sigil/SigilDERG-Finetuner) evaluation system:

1. **After training**: Use the finetuner's evaluation scripts to generate samples
2. **Run this evaluator**: Process the generated samples to get HumanEval metrics
3. **Compare metrics**: Track improvements across training phases

Example integration:
```bash
# After Phase 1 training, evaluate checkpoint
python scripts/generate_samples.py \
  --checkpoint out/llama8b-rust-qlora-phase1/checkpoint-1000 \
  --output eval_samples.jsonl

# Evaluate with HumanEval Rust
evaluate_functional_correctness eval_samples.jsonl \
  --problem_file=data/HumanEval_rust.jsonl
```

### Quick Sanity Check

The example samples should yield 0.5 pass@1:
```bash
$ evaluate_functional_correctness data/example_rust_samples.jsonl --problem_file=data/example_rust_problem.jsonl
Reading samples...
4it [00:00, 1959.50it/s]
Running test suites...
100%|...| 4/4 [00:03<00:00,  1.13it/s]
Writing results to data/example_rust_samples.jsonl_results.jsonl...
100%|...| 4/4 [00:00<00:00, 1536.38it/s]
{'pass@1': 0.5}
```

### Advanced Options

```bash
# Custom pass@k values
evaluate_functional_correctness samples.jsonl --k=1,5,10,20

# Adjust parallelism (default: 24 workers optimized for H100)
evaluate_functional_correctness samples.jsonl --n_workers=8

# Custom timeout (default: 10.0s optimized for H100)
evaluate_functional_correctness samples.jsonl --timeout=5.0

# Sandboxing options (recommended for production)
evaluate_functional_correctness samples.jsonl --sandbox-mode=docker
evaluate_functional_correctness samples.jsonl --sandbox-mode=firejail
evaluate_functional_correctness samples.jsonl --sandbox-mode=auto  # Auto-detect (default)
evaluate_functional_correctness samples.jsonl --sandbox-mode=none  # UNSAFE: local dev only

# Policy enforcement (pattern filtering)
evaluate_functional_correctness samples.jsonl --enforce-policy  # Default: enabled
evaluate_functional_correctness samples.jsonl --no-enforce-policy  # Disable for pure HumanEval compatibility

# See all options
evaluate_functional_correctness --help
```

### Security and Sandboxing

**⚠️ Important**: This evaluator runs untrusted LLM-generated Rust code. For production use, **always use Docker or Firejail sandboxing**.

The evaluator includes multiple layers of security:

1. **Pattern-based filtering** (optional, enabled by default): Blocks dangerous code patterns before execution (filesystem, network, process operations, unsafe code, etc.). Can be disabled with `--no-enforce-policy` for pure HumanEval compatibility.
2. **Process isolation**: Each evaluation runs in a separate process
3. **Docker/Firejail sandboxing** (recommended): Full container/jail isolation with resource limits

**Policy Enforcement Modes**:
- `--enforce-policy` (default): Enables pattern-based filtering for security. Use this for production evaluation of untrusted LLM-generated code.
- `--no-enforce-policy`: Disables pattern filtering for pure HumanEval compatibility. Use this when you need exact 1:1 comparability with the original HumanEval benchmark format (research/publication mode).

**Sandbox Modes**:
- `docker` (recommended): Uses Docker containers with `--network=none`, read-only filesystem, memory/CPU limits
- `firejail`: Uses Firejail for Linux systems without Docker
- `auto` (default): Auto-detects available sandbox (Docker → Firejail → none)
- `none`: No sandboxing (UNSAFE - only for local development with trusted code)

**Docker Setup**:
```bash
# Docker image is built automatically on first use
# Or build manually:
docker build -t human-eval-rust-sandbox -f Dockerfile.eval .
```

**Firejail Setup** (Linux only):
```bash
# Install Firejail
sudo apt-get install firejail  # Debian/Ubuntu
# or
sudo yum install firejail       # RHEL/CentOS
```

## Dataset Format

The HumanEval Rust dataset (`data/HumanEval_rust.jsonl`) contains 164 Rust programming problems. Each problem includes:
- `task_id`: Unique identifier (e.g., "HumanEval/0")
- `prompt`: Function signature and docstring
- `canonical_solution`: Reference implementation
- `test`: Rust test cases using `#[cfg(test)]`
- `entry_point`: Function name

Sample format:
```json
{"task_id": "HumanEval/0", "prompt": "fn has_close_elements(...) -> bool{", "canonical_solution": "...", "test": "#[cfg(test)]\nmod tests {...}", "entry_point": "has_close_elements"}
```

## Integration with SigilDERG Pipeline

### Complete Workflow

1. **Data Production** → Generate training data with [SigilDERG-Data_Production](https://github.com/Superuser666-Sigil/SigilDERG-Data_Production)
2. **Model Fine-Tuning** → Train on Rust code with [SigilDERG-Finetuner](https://github.com/Superuser666-Sigil/SigilDERG-Finetuner)
3. **Evaluation** → Assess performance with this HumanEval Rust harness
4. **Iteration** → Use results to guide further training and data collection

### Metrics and Benchmarking

This evaluator provides standardized `pass@k` metrics that complement the comprehensive evaluation metrics from the SigilDERG Finetuner:
- **Compilation metrics**: Success rates, clippy warnings
- **Code quality**: Documentation, idiomatic patterns
- **Functional correctness**: HumanEval pass@k scores (this project)

Together, these metrics provide a complete picture of model performance for Rust code generation.

## Hardware Optimizations (H100 Configuration)

Version 1.2.2+ includes optimizations specifically tuned for high-performance GPU evaluation environments (e.g., 1x H100 with 26 vCPUs and 225GB RAM):

### Default Configuration
- **Parallel Workers**: 24 (default `--n_workers=24`) - Optimized to saturate 26 vCPUs (reserving 2 for OS/orchestration)
- **Timeout**: 10.0 seconds (default `--timeout=10.0`) - Increased from 3.0s to handle compilation latency on loaded systems
- **Docker Memory Limit**: 4GB per container (increased from 512MB) - Handles complex, macro-heavy Rust code compilation
- **Docker tmpfs Size**: 2GB (increased from 300MB) - Prevents "disk full" errors during build artifact generation

### Resource Usage
With 24 workers and 4GB memory per container:
- **Maximum Memory Usage**: ~96GB (24 workers × 4GB) - Well within 225GB safety margin
- **CPU Utilization**: ~92% (24/26 vCPUs) - Near-saturation for maximum throughput

These defaults are optimized for production evaluation on high-end hardware. For smaller systems, you can override with `--n_workers` and `--timeout` flags.

## Known Issues

While evaluation uses very little memory, you might see the following error message when the system is running out of RAM. Since this may cause some correct programs to fail, we recommend that you free some memory and try again.
```
malloc: can't allocate region
```

## Citation

This evaluation harness is based on the HumanEval benchmark format described in the original Codex paper. Please cite:

```
@article{chen2021codex,
  title={Evaluating Large Language Models Trained on Code},
  author={Mark Chen and Jerry Tworek and Heewoo Jun and Qiming Yuan and Henrique Ponde de Oliveira Pinto and Jared Kaplan and Harri Edwards and Yuri Burda and Nicholas Joseph and Greg Brockman and Alex Ray and Raul Puri and Gretchen Krueger and Michael Petrov and Heidy Khlaaf and Girish Sastry and Pamela Mishkin and Brooke Chan and Scott Gray and Nick Ryder and Mikhail Pavlov and Alethea Power and Lukasz Kaiser and Mohammad Bavarian and Clemens Winter and Philippe Tillet and Felipe Petroski Such and Dave Cummings and Matthias Plappert and Fotios Chantzis and Elizabeth Barnes and Ariel Herbert-Voss and William Hebgen Guss and Alex Nichol and Alex Paino and Nikolas Tezak and Jie Tang and Igor Babuschkin and Suchir Balaji and Shantanu Jain and William Saunders and Christopher Hesse and Andrew N. Carr and Jan Leike and Josh Achiam and Vedant Misra and Evan Morikawa and Alec Radford and Matthew Knight and Miles Brundage and Mira Murati and Katie Mayer and Peter Welinder and Bob McGrew and Dario Amodei and Sam McCandlish and Ilya Sutskever and Wojciech Zaremba},
  year={2021},
  eprint={2107.03374},
  archivePrefix={arXiv},
  primaryClass={cs.LG}
}
```

## License

MIT License

