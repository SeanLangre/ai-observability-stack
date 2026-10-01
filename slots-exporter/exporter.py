#!/usr/bin/env python3
"""Prometheus exporter for llama-server's /slots and /props endpoints.

llama-server's own /metrics has no KV cache or per-slot data in this build, and
/props does not expose launch flags. This fills both gaps:
  - /slots   -> per-slot state and tokens held by active requests
  - /props   -> model, quant, slot count, build
  - /proc    -> launch flags (-ngl, -c, -b, ...) and process start time

Stdlib only. Config via env: LLAMA_URL, LISTEN_ADDR, LISTEN_PORT.
"""
import json
import os
import re
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer

LLAMA_URL = os.environ.get("LLAMA_URL", "http://127.0.0.1:8080")
LISTEN_ADDR = os.environ.get("LISTEN_ADDR", "127.0.0.1")
LISTEN_PORT = int(os.environ.get("LISTEN_PORT", "9840"))

# flag -> label name; value is the token after the flag
FLAGS = {
    "-ngl": "ngl", "--n-gpu-layers": "ngl",
    "-c": "ctx", "--ctx-size": "ctx",
    "-b": "batch", "--batch-size": "batch",
    "-ub": "ubatch", "--ubatch-size": "ubatch",
    "-t": "threads", "--threads": "threads",
    "-np": "parallel", "--parallel": "parallel",
    "-ctk": "cache_type_k", "--cache-type-k": "cache_type_k",
    "-ctv": "cache_type_v", "--cache-type-v": "cache_type_v",
    "-fa": "flash_attn", "--flash-attn": "flash_attn",
    "--n-cpu-moe": "n_cpu_moe", "-ncmoe": "n_cpu_moe",
}
BOOL_FLAGS = {"--no-mmap": "no_mmap", "--mlock": "mlock"}


def get_json(path):
    with urllib.request.urlopen(LLAMA_URL + path, timeout=3) as r:
        return json.load(r)


def find_server_cmdline():
    """Return (argv, start_time_epoch) of the llama-server process, or (None, None)."""
    try:
        for pid in filter(str.isdigit, os.listdir("/proc")):
            try:
                with open(f"/proc/{pid}/cmdline", "rb") as f:
                    argv = f.read().decode(errors="replace").split("\0")
            except OSError:
                continue
            if argv and os.path.basename(argv[0]) == "llama-server":
                with open(f"/proc/{pid}/stat") as f:
                    # field 22 (starttime, clock ticks since boot); comm may contain spaces
                    start_ticks = int(f.read().rsplit(")", 1)[1].split()[19])
                with open("/proc/stat") as f:
                    btime = next(int(l.split()[1]) for l in f if l.startswith("btime"))
                return argv, btime + start_ticks / os.sysconf("SC_CLK_TCK")
    except OSError:
        pass
    return None, None


def parse_flags(argv):
    labels = {}
    for i, a in enumerate(argv or []):
        if a in FLAGS and i + 1 < len(argv):
            labels[FLAGS[a]] = argv[i + 1]
        elif a in BOOL_FLAGS:
            labels[BOOL_FLAGS[a]] = "true"
    return labels


def esc(v):
    return str(v).replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")


def fmt(name, value, labels=None):
    if labels:
        lab = ",".join(f'{k}="{esc(v)}"' for k, v in sorted(labels.items()))
        return f"{name}{{{lab}}} {value}"
    return f"{name} {value}"


def collect():
    out = []

    def meta(name, help_, typ="gauge"):
        out.append(f"# HELP {name} {help_}")
        out.append(f"# TYPE {name} {typ}")

    try:
        slots = get_json("/slots")
        props = get_json("/props")
        up = 1
    except Exception:
        slots, props, up = [], {}, 0
    meta("llamacpp_exporter_up", "1 if /slots and /props were readable")
    out.append(fmt("llamacpp_exporter_up", up))
    if not up:
        return "\n".join(out) + "\n"

    n_ctx = max((s.get("n_ctx", 0) for s in slots), default=0)
    used = 0
    meta("llamacpp_slots_total", "Number of server slots")
    out.append(fmt("llamacpp_slots_total", props.get("total_slots", len(slots))))
    meta("llamacpp_context_size_tokens", "Context size (-c). Shared across slots when KV is unified")
    out.append(fmt("llamacpp_context_size_tokens", n_ctx))

    meta("llamacpp_slot_busy", "1 if the slot is processing a request")
    meta("llamacpp_slot_context_tokens", "Prompt + generated tokens held by the slot's active request (0 when idle)")
    meta("llamacpp_slot_prompt_cache_tokens", "Prompt tokens of the active request reused from cache")
    meta("llamacpp_slot_prompt_processed_tokens", "Prompt tokens of the active request processed so far")
    meta("llamacpp_slot_decoded_tokens", "Tokens generated so far by the slot's active request")
    meta("llamacpp_slot_remaining_tokens", "Generation budget left for the slot's active request")
    busy_slots = 0
    for s in slots:
        lab = {"slot": s.get("id", "?")}
        busy = 1 if s.get("is_processing") else 0
        busy_slots += busy
        nt = (s.get("next_token") or [{}])[0]
        decoded = nt.get("n_decoded", 0) if busy else 0
        ctx = (s.get("n_prompt_tokens", 0) + decoded) if busy else 0
        used += ctx
        out.append(fmt("llamacpp_slot_busy", busy, lab))
        out.append(fmt("llamacpp_slot_context_tokens", ctx, lab))
        out.append(fmt("llamacpp_slot_prompt_cache_tokens", s.get("n_prompt_tokens_cache", 0) if busy else 0, lab))
        out.append(fmt("llamacpp_slot_prompt_processed_tokens", s.get("n_prompt_tokens_processed", 0) if busy else 0, lab))
        out.append(fmt("llamacpp_slot_decoded_tokens", decoded, lab))
        out.append(fmt("llamacpp_slot_remaining_tokens", nt.get("n_remain", 0) if busy else 0, lab))

    meta("llamacpp_slots_busy", "Number of busy slots")
    out.append(fmt("llamacpp_slots_busy", busy_slots))
    meta("llamacpp_context_used_tokens", "Sum of context tokens across active requests (idle cached context is not visible)")
    out.append(fmt("llamacpp_context_used_tokens", used))
    meta("llamacpp_context_used_ratio", "Active-request context tokens / context size")
    out.append(fmt("llamacpp_context_used_ratio", round(used / n_ctx, 6) if n_ctx else 0))

    argv, started = find_server_cmdline()
    info = {
        "model": os.path.basename(props.get("model_path", "")),
        "quant": props.get("model_ftype", ""),
        "build": props.get("build_info", ""),
        "slots": props.get("total_slots", ""),
        "ctx": n_ctx,
    }
    info.update(parse_flags(argv))
    meta("llamacpp_config_info", "Always 1; labels describe the running llama-server config")
    out.append(fmt("llamacpp_config_info", 1, info))
    if started:
        meta("llamacpp_server_start_time_seconds", "Unix start time of the llama-server process")
        out.append(fmt("llamacpp_server_start_time_seconds", f"{started:.0f}"))
    return "\n".join(out) + "\n"


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path != "/metrics":
            self.send_response(404)
            self.end_headers()
            return
        body = collect().encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; version=0.0.4")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    HTTPServer((LISTEN_ADDR, LISTEN_PORT), Handler).serve_forever()
