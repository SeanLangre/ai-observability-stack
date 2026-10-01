# TODO

Goal: make the stack better at identifying bottlenecks and suggesting improvements, not just showing that the server is slow.

Context: single user, one RTX 5060 Ti (16 GB), one llama-server. Generation is CPU-bound with the GPU mostly idle, and the speed dips line up with major page faults. Tuning matters more than alerting.

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

- [ ] A/B `--no-mmap` (or `--mlock`): do the page-fault spikes and the ~9 tok/s dips go away?
- [ ] `-ngl 99 --n-cpu-moe N` (or `-ot` for expert tensors) instead of `-ngl 30`: keep attention on the GPU, experts on the CPU
- [ ] Check whether generation slowdown follows context growth (now visible via `llamacpp_context_used_ratio`)
- [ ] Re-tune `-c` and `-ngl` given VRAM headroom; try `-b`/`-ub`, threads, flash attention, KV cache quant
- [ ] Record the winning config and numbers in the README

## 2. Cheap observability gaps (PromQL-only, no new components)

- [ ] GPU clocks / throttle reasons panel (`nvidia_smi_clocks_*`, `clocks_event_reasons_*`)
- [ ] Prompt cache hit rate (`prompt_tokens_cached_total` vs `prompt_tokens_total`)
- [ ] Prompt vs. generation share of busy time (to guide `-b`/`-ub`)
- [ ] Deferred requests as a distinct signal (`requests_deferred > 0`)
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

- [ ] Update README as items land: layout (`slots-exporter/`), dashboard panels, new metrics, "Possible next steps", and the Grafana password note (`admin/admin` is only the default)
- [ ] `run.sh` still says log in with `admin/admin`

## Won't do for now

Revisit only if the setup changes (unattended server, more clients, more GPUs).

- Process exporter for the llama-server PID: redundant with node_exporter and GPU metrics for a single server
- Speculative decoding acceptance panel: only if speculative decoding is enabled
- Alerts on tok/s below baseline, sustained deferrals, KV above 90%, GPU temp/throttling: you see these on the dashboard while using the model, and VRAM and temperature are stable
- Recording rules: only if dashboards get slow at 30d retention
- LLM proxy/tracing (LiteLLM or Langfuse): only worth it with more than one client
