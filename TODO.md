# TODO

Goal: make the stack better at identifying bottlenecks and suggesting improvements, not just showing that the server is slow.

## 1. Host and hardware metrics (highest payoff)

- [x] `node_exporter` (compose service, host networking, localhost only) and scrape job
- [x] `nvidia_gpu_exporter` for the RTX 5060 Ti (host nvidia-smi + devices mounted, no container toolkit needed)
- [x] "Hardware" dashboard row: GPU util/memory bandwidth, VRAM, temp/power, per-core CPU, RAM/swap, major faults/disk reads
- [x] "Where is the time going" overlay panel (tok/s vs GPU vs CPU vs VRAM)
- [ ] Process exporter for the llama-server PID (RSS, CPU time)
- [ ] GPU clocks / throttle reasons panel (`nvidia_smi_clocks_*`, `clocks_event_reasons_*`)

## 2. More from llama-server

- [x] KV cache usage: `llamacpp_context_used_ratio` from `/slots` (active requests only)
- [ ] Speculative decoding acceptance rate panel (`spec_decode_num_accepted_tokens_total / spec_decode_num_draft_tokens_total`), if used
- [ ] Prompt cache hit rate (`prompt_tokens_cached_total` vs `prompt_tokens_total`)
- [ ] Deferred requests as a distinct signal (`requests_deferred > 0`)
- [ ] Prompt vs. generation share of busy time, to guide `-b`/`-ub` and `-ngl` tuning
- [x] Pull `/slots` and `/props` into Prometheus (`slots-exporter/`, port 9840)
  - [x] Per-slot state, context fill, prompt cache hits

## 3. Correlation

- [x] "Where is the time going" row
- [x] Add KV usage to the "Where is the time going" row (needs `/slots`)
- [x] `llamacpp_config_info{model,quant,ngl,ctx,build,...} 1` info metric (flags read from /proc)
- [ ] Grafana annotations for config changes and restarts

## 4. Alerting

- [ ] Prometheus alert rules (`prometheus/alerts.yml`)
  - [ ] Generation tok/s below baseline
  - [ ] Sustained deferrals
  - [ ] KV cache above 90%
  - [ ] GPU temperature / throttling
  - [ ] Scrape target down
- [ ] Recording rules for the tok/s ratios so dashboard queries stay cheap at 30d retention
- [ ] Decide on a notification channel (Grafana contact point)

## 5. Benchmarking

- [ ] Sweep script around `llama-bench` over `-ngl`, `-b`/`-ub`, threads, flash attention, KV cache quant, context size
- [ ] Publish results to Prometheus (Pushgateway or textfile collector), labeled by config
- [ ] Grafana table comparing configs to show the best one for this hardware
- [ ] Quick A/B: restart llama-server with `--no-mmap` (or `--mlock`) to see if the page-fault spikes and the ~9 tok/s dips go away
- [ ] Test `-ngl 99 --n-cpu-moe N` (or `-ot` for experts) instead of `-ngl 30`: generation is CPU-bound with the GPU mostly idle
- [ ] Alert on major page faults / disk reads while generating (model paging)

## 6. Optional

- [ ] LLM proxy/tracing (LiteLLM or Langfuse) for time-to-first-token and per-caller latency. Only worth it if more than one client uses the server.

## 7. Dashboard polish

- [x] Per-core CPU panel: replace 12 lines with avg/max (or bar gauge/heatmap)
- [x] GPU temperature / power: put power on a right-hand axis
- [x] Page faults / disk read: separate axes (disk read is invisible today)
- [x] Token throughput: give generation its own axis/panel so prompt spikes don't flatten it
- [x] One color per concept across panels (prompt, generation, power, memory bandwidth)
- [ ] Thresholds on the stat tiles (currently always green) once baselines exist

## Housekeeping

- [x] VRAM ~15.4 of 16 GB: not a leak (flat 15.44-15.50 GB over 7d; llama-server holds 13.9 GB, the rest is desktop/other processes). Re-tuning `-ngl`/`-c` is left for the benchmark sweep
- [ ] Update README (layout, dashboard table, "Possible next steps") as items land
- [x] Pin image tags instead of `:latest`
- [x] Change the default Grafana admin password
