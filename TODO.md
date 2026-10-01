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

- [ ] KV cache usage: this llama-server build exports no `kv_cache_*` metrics. Use `/slots` (below) or `llamacpp:n_tokens_max` vs `-c` instead
- [ ] Speculative decoding acceptance rate panel (`spec_decode_num_accepted_tokens_total / spec_decode_num_draft_tokens_total`), if used
- [ ] Prompt cache hit rate (`prompt_tokens_cached_total` vs `prompt_tokens_total`)
- [ ] Deferred requests as a distinct signal (`requests_deferred > 0`)
- [ ] Prompt vs. generation share of busy time, to guide `-b`/`-ub` and `-ngl` tuning
- [ ] Pull `/slots` and `/props` into Prometheus (script or `json_exporter`)
  - [ ] Per-slot state, context fill, prompt cache hits

## 3. Correlation

- [x] "Where is the time going" row (KV usage still to add)
- [ ] `llamacpp_config_info{model,quant,ngl,ctx,build} 1` info metric so runs can be compared by label
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

## 6. Optional

- [ ] LLM proxy/tracing (LiteLLM or Langfuse) for time-to-first-token and per-caller latency. Only worth it if more than one client uses the server.

## Housekeeping

- [ ] VRAM was ~15.5 of 16 GB at idle with `-ngl 30 -c 64000`: check whether that is the model + KV cache or a leak, and re-tune `-ngl`/`-c`
- [ ] Update README (layout, dashboard table, "Possible next steps") as items land
- [ ] Pin image tags instead of `:latest`
- [ ] Change the default Grafana admin password
