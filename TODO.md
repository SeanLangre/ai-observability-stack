# TODO

Goal: make the stack better at identifying bottlenecks and suggesting improvements, not just showing that the server is slow.

Context: single user, one card (16 GB), one llama-server. Tuning matters more than alerting.

Baseline (`-ngl 30 -c 64000`): ~9.9 tok/s generation, ~419 tok/s prompt, GPU mostly idle, CPU-bound.
Current (`-ngl 99 --n-cpu-moe 10 -c 64000`, ~10 min of real use): ~47.8 tok/s generation (min 40, max 52), ~623 tok/s prompt, GPU util ~59%, VRAM ~0.5 GiB free.

## Done

- [x] `node_exporter` and `nvidia_gpu_exporter` (host networking, localhost only) with scrape jobs
- [x] Hardware dashboard row: GPU util/memory bandwidth, VRAM, temp/power, CPU, RAM/swap, page faults/disk reads
- [x] "Where is the time going" overlay panel (tok/s vs GPU vs CPU vs VRAM vs context used)
- [x] `slots-exporter/` (port 9840): per-slot state, context in use (`llamacpp_context_used_ratio`), prompt cache, `llamacpp_config_info` (launch flags read from /proc), server start time
- [x] Dashboard polish: per-core CPU replaced by avg/max, separate axes for temp/power and faults/disk, one color per concept
- [x] VRAM check: ~15.4 of 16 GB is flat over 7d (llama-server holds 13.9 GB, the rest is desktop), not a leak
- [x] Pinned image tags, changed the Grafana admin password

## 1. Tuning experiments (next, highest payoff)

Change one thing at a time and compare runs by the `llamacpp_config_info` labels.

- [x] `-ngl 99 --n-cpu-moe 10`: ~4.8x faster generation (9.9 to 47.8 tok/s) at about the same VRAM, and it held ~48 tok/s at 30-50k context
- [x] Update `run.sh` and the README to the new flags
- [x] Check whether generation slowdown follows context growth: no, speed stayed ~48 tok/s at 30-50k context on the new config, so the earlier decline was the CPU-bound layers, not context
- [ ] Try `--n-cpu-moe 8`/`9` (less on the CPU) if VRAM allows; only ~0.5 GiB is free, so watch for out-of-memory
- [ ] A/B `--no-mmap`: low priority, little paging seen (about 1.35 GB read and ~7k major faults per hour with the old config). `--mlock` is not usable with the 8 MiB `ulimit -l`
- [ ] Re-tune `-c` and `-ngl` given VRAM headroom; try `-b`/`-ub`, threads, flash attention, KV cache quant
- [ ] Record the winning config and numbers in the README

## 2. Cheap observability gaps (PromQL-only, no new components)

- [x] Prompt cache hit rate (`prompt_tokens_cached_total` vs `prompt_tokens_total`)
- [x] Prompt vs. generation share of busy time (to guide `-b`/`-ub`)
- [x] Deferred requests as a distinct signal (`requests_deferred > 0`)
- [ ] GPU clocks / throttle reasons panel (`nvidia_smi_clocks_*`, `clocks_event_reasons_*`)
- [ ] Grafana annotations for restarts and config changes (from `llamacpp_server_start_time_seconds` / `llamacpp_config_info`), so A/B runs are marked on the graphs
- [ ] Stat tile thresholds (currently always green) once baselines are known from the experiments
- [ ] Page faults / disk read: color threshold on the panel to flag model paging

## 3. Minimal alerting

Only what is useful when not watching the dashboard.

- [ ] `prometheus/alerts.yml`: scrape target down, and major page faults while generating
- [ ] Decide whether a notification channel is worth it at all (Grafana contact point). Skip if alerts only show in the UI

## 4. Benchmark sweep (after the manual experiments show what is worth sweeping)

- [ ] Sweep script around `llama-bench` over the settings that mattered in section 1
- [ ] Publish results to Prometheus (Pushgateway or textfile collector), labeled by config
- [ ] Grafana table comparing configs to show the best one for this hardware

## Housekeeping

- [ ] Keep the README up to date as items land (layout, dashboard panels, metrics done as of the slots exporter)

## Won't do for now

Revisit only if the setup changes (unattended server, more clients, more GPUs).

- Process exporter for the llama-server PID: redundant with node_exporter and GPU metrics for a single server
- Speculative decoding acceptance panel: only if speculative decoding is enabled
- Alerts on tok/s below baseline, sustained deferrals, KV above 90%, GPU temp/throttling: you see these on the dashboard while using the model, and VRAM and temperature are stable
- Recording rules: only if dashboards get slow at 30d retention
- LLM proxy/tracing (LiteLLM or Langfuse): only worth it with more than one client
