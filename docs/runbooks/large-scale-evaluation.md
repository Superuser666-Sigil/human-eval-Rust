# Runbook: Large-Scale Evaluation

## Overview

Guide for running evaluations on production workloads (thousands of samples, multiple models).

## Prerequisites

- [ ] High-memory system (recommended: 64GB+ RAM)
- [ ] Multi-core CPU (recommended: 24+ cores)
- [ ] SSD storage for fast I/O
- [ ] Firejail installed (Linux)
- [ ] Rust toolchain (stable)

## Hardware Recommendations

### Lambda Labs H100 Instance (Recommended)

| Resource | Value |
|----------|-------|
| vCPUs | 26 |
| RAM | 225 GB |
| Workers | 24 (default) |
| Timeout | 10s (default) |
| Memory per worker | ~4 GB |

### Smaller Systems

| System | Workers | Timeout |
|--------|---------|---------|
| 16 cores, 32 GB RAM | 12 | 10s |
| 8 cores, 16 GB RAM | 6 | 15s |
| 4 cores, 8 GB RAM | 2 | 30s |

---

## Steps

### 1. Prepare Environment

```bash
# Create dedicated evaluation environment
python -m venv eval_env
source eval_env/bin/activate
pip install human-eval-rust

# Verify resources
free -h
nproc
```

### 2. Split Large Sample Files

For very large files (100k+ samples), split into chunks:

```bash
# Split into 10k-sample chunks
split -l 10000 samples.jsonl samples_chunk_

# Rename to .jsonl
for f in samples_chunk_*; do mv "$f" "${f}.jsonl"; done
```

### 3. Configure Workers

Calculate optimal workers:
```
workers = min(CPU_cores - 2, available_RAM_GB / 4)
```

```bash
# Example for 26 vCPUs, 225 GB RAM
# workers = min(24, 56) = 24
evaluate_functional_correctness samples.jsonl --n_workers=24
```

### 4. Run with Monitoring

```bash
# In one terminal: run evaluation
evaluate_functional_correctness samples.jsonl \
    --n_workers=24 \
    --timeout=10.0 \
    --sandbox-mode=firejail

# In another terminal: monitor
htop
watch -n 5 'free -h'
```

### 5. Handle Chunks (if split)

```bash
# Process each chunk
for chunk in samples_chunk_*.jsonl; do
    echo "Processing $chunk..."
    evaluate_functional_correctness "$chunk" \
        --n_workers=24 \
        --timeout=10.0
done

# Combine results
cat samples_chunk_*.jsonl_results.jsonl > all_results.jsonl
```

### 6. Aggregate Metrics

```python
import json
from collections import defaultdict

results = defaultdict(list)
with open('all_results.jsonl') as f:
    for line in f:
        r = json.loads(line)
        results[r['task_id']].append(r['passed'])

# Calculate pass@1
pass_at_1 = sum(any(passes) for passes in results.values()) / len(results)
print(f"pass@1: {pass_at_1:.4f}")

# Calculate compile rate
compile_ok = sum(1 for line in open('all_results.jsonl') 
                 if json.loads(line).get('compile_ok'))
total = sum(1 for _ in open('all_results.jsonl'))
print(f"compile_rate: {compile_ok/total:.4f}")
```

---

## Parallel Model Evaluation

To evaluate multiple models simultaneously:

```bash
# Model 1 (use half the workers)
evaluate_functional_correctness model1_samples.jsonl \
    --n_workers=12 &

# Model 2 (use other half)
evaluate_functional_correctness model2_samples.jsonl \
    --n_workers=12 &

# Wait for both
wait
```

---

## Checkpointing (Manual)

HumanEval Rust doesn't have built-in checkpointing. For resumability:

```bash
# Count processed
wc -l samples.jsonl_results.jsonl

# If interrupted, find last processed task_id
tail -1 samples.jsonl_results.jsonl | python -c "import json,sys; print(json.load(sys.stdin)['task_id'])"

# Skip already processed (manual)
# Re-run will overwrite, so copy partial results first
cp samples.jsonl_results.jsonl samples_partial.jsonl
```

---

## Resource Management

### Memory Pressure

```bash
# Monitor memory
watch -n 2 'free -h'

# If running low, reduce workers
# Kill and restart with fewer workers
pkill -9 -f evaluate_functional_correctness
evaluate_functional_correctness samples.jsonl --n_workers=8
```

### CPU Throttling

```bash
# Check for thermal throttling
cat /sys/class/thermal/thermal_zone*/temp

# Monitor CPU frequency
watch -n 1 'cat /proc/cpuinfo | grep MHz'
```

### Disk I/O

```bash
# Check I/O wait
iostat -x 1

# If high iowait, results file may be bottleneck
# Consider writing to ramdisk
mkdir -p /dev/shm/eval
cp samples.jsonl /dev/shm/eval/
cd /dev/shm/eval
evaluate_functional_correctness samples.jsonl
cp samples.jsonl_results.jsonl /original/path/
```

---

## Expected Performance

| Configuration | Throughput |
|--------------|------------|
| H100, 24 workers, 10s timeout | ~150 samples/min |
| 16 cores, 12 workers, 10s timeout | ~75 samples/min |
| 8 cores, 6 workers, 15s timeout | ~30 samples/min |

### Full HumanEval Timing

164 problems × k samples per problem:

| k | Total Samples | H100 Time |
|---|---------------|-----------|
| 1 | 164 | ~1 min |
| 10 | 1,640 | ~11 min |
| 100 | 16,400 | ~110 min |
| 200 | 32,800 | ~220 min |

---

## Post-Evaluation

### Verify Completeness

```bash
# Count input samples
wc -l samples.jsonl

# Count output results
wc -l samples.jsonl_results.jsonl

# Should match
```

### Check for Errors

```bash
# Count by error type
python -c "
import json
from collections import Counter
errors = Counter()
with open('samples.jsonl_results.jsonl') as f:
    for line in f:
        r = json.loads(line)
        errors[r.get('error_type', 'none')] += 1
print(dict(errors))
"
```

### Archive Results

```bash
# Compress for storage
gzip -k samples.jsonl_results.jsonl

# Include metadata
echo "Date: $(date)" > evaluation_metadata.txt
echo "Samples: $(wc -l samples.jsonl)" >> evaluation_metadata.txt
echo "rustc: $(rustc --version)" >> evaluation_metadata.txt
```

