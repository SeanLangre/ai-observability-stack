**llama.cpp is the inference engine, Prometheus is the time-series store, Grafana is visualization, and MCP is the control/benchmark API**.

```text
                         ┌─────────────────────┐
                         │  MCP Client          │
                         │  Claude / IDE / App  │
                         └──────────┬──────────┘
                                    │ MCP
                                    ▼
                         ┌─────────────────────┐
                         │     MCP Server      │
                         │                     │
                         │ benchmark()         │
                         │ models()            │
                         │ stats()             │
                         │ run_test_suite()    │
                         └───────┬───────┬─────┘
                                 │       │
                         HTTP API │       │ Prometheus query
                                 │       │
                                 ▼       ▼
                         ┌────────────┐  ┌────────────┐
                         │ llama.cpp  │  │ Prometheus │
                         │ llama-     │  │            │
                         │ server     │  └─────┬──────┘
                         └─────┬──────┘        │
                               │                │
                         metrics│                │
                               ▼                ▼
                         ┌────────────┐   ┌────────────┐
                         │ Exporter / │   │  Grafana   │
                         │ metrics    │   │            │
                         └────────────┘   └────────────┘
```

## 1. Docker Compose

A reasonable starting point would be:

```yaml
services:

  llama:
    image: ghcr.io/ggerganov/llama.cpp:server
    container_name: llama
    restart: unless-stopped

    command:
      - "-m"
      - "/models/model.gguf"
      - "--host"
      - "0.0.0.0"
      - "--port"
      - "8080"
      - "-c"
      - "8192"
      - "-ngl"
      - "999"

    volumes:
      - ./models:/models:ro

    ports:
      - "8080:8080"

    # NVIDIA example
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]

  mcp:
    build:
      context: ./mcp
    container_name: llama-mcp
    restart: unless-stopped

    environment:
      LLAMA_URL: http://llama:8080
      PROMETHEUS_URL: http://prometheus:9090

    depends_on:
      - llama
      - prometheus

    ports:
      - "8000:8000"

  prometheus:
    image: prom/prometheus:latest
    container_name: prometheus
    restart: unless-stopped

    volumes:
      - ./prometheus/prometheus.yml:/etc/prometheus/prometheus.yml:ro
      - prometheus-data:/prometheus

    ports:
      - "9090:9090"

  grafana:
    image: grafana/grafana:latest
    container_name: grafana
    restart: unless-stopped

    environment:
      GF_SECURITY_ADMIN_USER: admin
      GF_SECURITY_ADMIN_PASSWORD: change-me

    volumes:
      - grafana-data:/var/lib/grafana

    depends_on:
      - prometheus

    ports:
      - "3000:3000"


volumes:
  prometheus-data:
  grafana-data:
```

I'd keep the model files **outside the containers**:

```text
project/
├── docker-compose.yml
├── models/
│   ├── llama-3.1-8b-q4.gguf
│   └── qwen2.5-coder-14b-q4.gguf
│
├── mcp/
│   ├── Dockerfile
│   ├── server.py
│   └── benchmark.py
│
└── prometheus/
    └── prometheus.yml
```

That makes swapping models considerably easier.

---

# 2. Prometheus

The interesting part is getting llama.cpp measurements into Prometheus.

I'd configure:

```yaml
global:
  scrape_interval: 5s

scrape_configs:

  - job_name: llama
    static_configs:
      - targets:
          - llama:8080

  - job_name: mcp
    static_configs:
      - targets:
          - mcp:8000
```

There is an important architectural detail here, though:

**Don't assume every llama.cpp statistic you want is already exposed in Prometheus format.**

Instead, I'd make the MCP/benchmark service maintain a small `/metrics` endpoint and push normalized benchmark results into it.

For example:

```text
llama_request_tokens_total
llama_generated_tokens_total

llama_generation_tokens_per_second
llama_prompt_tokens_per_second

llama_request_duration_seconds
llama_time_to_first_token_seconds

llama_prompt_tokens
llama_completion_tokens

llama_model_info
```

Then Grafana doesn't need to understand llama.cpp's internal response format.

---

# 3. MCP server

This is where I'd make the project interesting.

Expose MCP tools along these lines:

```text
models()
```

Returns:

```json
[
  {
    "name": "llama-8b-q4",
    "path": "/models/llama-3.1-8b-q4.gguf"
  },
  {
    "name": "qwen-coder-14b-q4",
    "path": "/models/qwen2.5-coder-14b-q4.gguf"
  }
]
```

Then:

```text
benchmark(
    model="llama-8b-q4",
    suite="coding",
    iterations=10
)
```

Could return:

```json
{
  "model": "llama-8b-q4",
  "iterations": 10,
  "avg_ttft_ms": 183,
  "avg_generation_tok_s": 86.2,
  "avg_prompt_tok_s": 1240,
  "p95_latency_ms": 2410
}
```

And:

```text
compare_models(
    models=["llama-8b-q4", "qwen-coder-14b-q4"],
    suite="coding"
)
```

Now you have an interface where an MCP client can essentially say:

> Run my coding benchmark against the two models.

---

# 4. Benchmark runner

I'd make the benchmark runner deliberately boring.

Something like:

```python
for model in models:

    for test in suite:

        start = time.monotonic()

        response = call_llama(
            model=model,
            prompt=test.prompt
        )

        elapsed = time.monotonic() - start

        record_metrics(
            model=model,
            test=test,
            elapsed=elapsed,
            prompt_tokens=response.prompt_tokens,
            completion_tokens=response.completion_tokens
        )
```

The important thing is that every result gets metadata:

```text
model
quantization
context_length
gpu_layers
batch_size
test_suite
test_case
timestamp
```

That lets Grafana answer questions like:

**"How did Q4 vs Q5 perform?"**

or:

**"What happened to throughput when I increased context from 8K to 32K?"**

---

# 5. Grafana dashboard

I'd build four panels initially.

### Overview

```text
┌──────────────────┬──────────────────┬──────────────────┐
│ Generation       │ TTFT             │ VRAM             │
│ 86.2 tok/s       │ 183 ms           │ 7.2 GB           │
├──────────────────┼──────────────────┼──────────────────┤
│ Prompt           │ Requests         │ Error rate       │
│ 1,240 tok/s      │ 142             │ 0.7%             │
└──────────────────┴──────────────────┴──────────────────┘
```

### Throughput

Graph:

```text
tokens/sec
 100 ┤       ╭──╮
  80 ┤  ╭────╯  ╰────╮
  60 ┤──╯             ╰──
  40 ┤
     └────────────────────
       time
```

### Model comparison

Use Grafana variables:

```text
Model:
[ llama-8b-q4 ▼ ]

Quantization:
[ Q4_K_M ▼ ]

Context:
[ 8192 ▼ ]
```

Then graph:

```text
                 tok/s
Llama 8B Q4       86
Llama 8B Q5       72
Qwen 14B Q4       51
Qwen 14B Q5       43
```

### Hardware

Track:

```text
GPU utilization
GPU memory
GPU temperature
GPU power
CPU utilization
RAM
```

That last dashboard is particularly useful because a model benchmark can otherwise give misleading results.

---

# 6. The really useful bit: benchmark history

I'd give every benchmark run an ID:

```text
benchmark_id = 2026-10-01T14:32:18Z
```

and record:

```text
model = qwen2.5-coder-14b
quantization = Q4_K_M
context = 8192
gpu_layers = 99
benchmark = coding-v1
```

Then you can see:

```text
                    Generation tok/s

90 ┤ ●
80 ┤   ●
70 ┤      ●
60 ┤         ●
50 ┤             ●
   └────────────────────────────
     Q4     Q5     Q6     Q8
```

This becomes much more valuable than a one-off `llama-bench` invocation because you're effectively building a **local inference performance history**.

---

## 7. I'd add one more component

For GPU metrics, I'd add **NVIDIA DCGM Exporter** if you're running NVIDIA hardware:

```text
                         ┌───────────────┐
                         │ DCGM exporter │
                         └───────┬───────┘
                                 │
                                 ▼
                           Prometheus
                                 │
                                 ▼
                             Grafana
```

Then you can correlate:

```text
            llama.cpp                GPU

       90 tok/s ──────────────── 92% utilization
       87 tok/s ──────────────── 89%
       73 tok/s ──────────────── 71%
       51 tok/s ──────────────── 48%
```

That can tell you whether you're **compute-bound, memory-bound, or simply not utilizing the GPU properly**.

---

## One architectural change I'd make

I wouldn't make MCP directly responsible for Prometheus.

Instead:

```text
                 MCP
                  │
             benchmark API
                  │
                  ▼
             llama.cpp
                  │
                  ├──────────────┐
                  │              │
                  ▼              ▼
              metrics         benchmark
                  │              │
                  └──────┬───────┘
                         ▼
                    Prometheus
                         │
                         ▼
                      Grafana
```

**MCP should be the interface/control plane. Prometheus should be the observability plane.**

That separation will make the system much easier to extend later.

And once this is working, you can do some genuinely interesting things with it: **automatically benchmark every new GGUF you drop into `models/`, compare it against previous runs, and have MCP report the results conversationally while Grafana keeps the historical performance data.**
