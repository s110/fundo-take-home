"""Model access through a committed response cache.

Cache key = sha256(provider, model, schema, messages). A run with the same prompts reads the cache and
makes no network call. With offline=True a cache miss acts like a provider outage, so the caller falls
back to the keyword label. That is how a clean checkout reproduces the committed output with no key.

The models are Claude Haiku and Claude Sonnet, called through the Claude Code CLI (`claude -p`) with a
JSON schema for the reply. With ANTHROPIC_API_KEY set, the CLI runs in --bare mode and bills that key.
Without it, the CLI uses the logged-in Claude account; I ran it that way, on a subscription. The CLI adds
a short preamble of its own to the system prompt, and the cost and latency figures include it. In
production the same prompt and schema go to the Messages API directly.

DeepSeek is a cheaper challenger, in two modes of one model: thinking off and thinking on. It is called over
its OpenAI-compatible HTTP API with DEEPSEEK_API_KEY, with the standard library only. Its JSON mode does
not enforce the schema, so validate() and the retry in reviewer.py do that work. The API returns tokens, not
dollars; the price below is the peak-hour list price (off-peak is half), so the cost figures are an upper bound.
"""
import hashlib
import json
import os
import subprocess
import tempfile
import threading
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

CACHE_PATH = Path(__file__).resolve().parent.parent / "cache" / "llm_responses.jsonl"
_CACHES = {}  # path -> {key: record}; each cache file is read once per process
PROVIDERS = {"haiku": {"model": "claude-haiku-5-5"}, "sonnet": {"model": "claude-sonnet-5-5"},
             "deepseek": {"model": "deepseek-flash", "thinking": False},
             "deepseek-think": {"model": "deepseek-flash", "thinking": True}}
DEEPSEEK_URL = "https://api.deepseek.com/v1/chat/completions"
DEEPSEEK_USD_PER_M = {"cache_hit": 0.006, "cache_miss": 0.30, "output": 1.20}  # api-docs.deepseek.com, 2026-10-21


def display(provider):
    """The model name, plus the mode where one model runs in two modes."""
    m = PROVIDERS.get(provider, {"model": provider})
    return m["model"] + {True: " (thinking)", False: " (no thinking)"}.get(m.get("thinking"), "")


class ProviderError(Exception):
    pass


class LLM:
    def __init__(self, provider, offline=False, timeout=180, cache_path=CACHE_PATH, sample=0):
        """cache_path: review.py passes its own file, so replies about a user's file stay out of the committed cache.
        sample: 0 is the committed run. 1, 2, ... ask the same prompts again for a new reply, to measure how much
        a second run of the same model changes the result."""
        self.provider, self.offline, self.timeout, self.sample = provider, offline, timeout, sample
        self.model = PROVIDERS[provider]["model"]
        self.lock = threading.Lock()
        self.cache_path = Path(cache_path)
        if self.cache_path not in _CACHES:
            lines = self.cache_path.read_text().splitlines() if self.cache_path.exists() else []
            _CACHES[self.cache_path] = {rec["key"]: rec for rec in map(json.loads, lines)}
        self.cache = _CACHES[self.cache_path]

    def key(self, messages, schema):
        d = {"provider": self.provider, "model": self.model, "schema": schema, "messages": messages}
        if self.sample:  # sample 0 keeps the keys of the committed cache
            d["sample"] = self.sample
        blob = json.dumps(d, sort_keys=True)
        return hashlib.sha256(blob.encode()).hexdigest()

    def chat(self, messages, schema):
        """Return the cache record of the reply. Raises ProviderError when no reply is available."""
        k = self.key(messages, schema)
        with self.lock:
            if k in self.cache:
                return self.cache[k]
        if self.offline:
            raise ProviderError("offline and not in the cache")
        try:
            call = self._deepseek if self.provider.startswith("deepseek") else self._claude_cli
            content, served, tin, tout, usd, seconds = call(messages, schema)
        except (OSError, subprocess.SubprocessError, KeyError, ValueError, TypeError, AttributeError) as e:
            # OSError: no CLI or a timeout; the others: a reply whose JSON does not have the expected shape
            raise ProviderError(f"{type(e).__name__}: {e}") from e
        rec = {"key": k, "provider": self.provider, "model": self.model, "served_model": served,
               "content": content, "tokens_in": tin, "tokens_out": tout, "usd": round(usd, 6),
               "latency_s": round(seconds, 3), "created": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
        with self.lock:
            self.cache[k] = rec
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            with self.cache_path.open("a") as f:
                f.write(json.dumps(rec, sort_keys=True) + "\n")
        return rec

    def _deepseek(self, messages, schema):
        """schema is not sent: JSON mode takes no schema. It is still in the cache key, like for Claude."""
        thinking = "enabled" if PROVIDERS[self.provider]["thinking"] else "disabled"
        body = {"model": self.model, "messages": messages, "response_format": {"type": "json_object"},
                "thinking": {"type": thinking}, "max_tokens": 4000}
        req = urllib.request.Request(DEEPSEEK_URL, data=json.dumps(body).encode(), headers={
            "Authorization": "Bearer " + os.environ["DEEPSEEK_API_KEY"], "Content-Type": "application/json"})
        start = time.monotonic()
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            d = json.loads(resp.read())
        seconds = time.monotonic() - start  # wall time of the HTTP call, network included
        u = d["usage"]
        hit = u.get("prompt_cache_hit_tokens") or 0
        usd = (hit * DEEPSEEK_USD_PER_M["cache_hit"] + (u["prompt_tokens"] - hit) * DEEPSEEK_USD_PER_M["cache_miss"]
               + u["completion_tokens"] * DEEPSEEK_USD_PER_M["output"]) / 1e6
        return d["choices"][0]["message"]["content"], d["model"], u["prompt_tokens"], u["completion_tokens"], usd, seconds

    def _claude_cli(self, messages, schema):
        system, prompt = messages[0]["content"], messages[1]["content"]
        for m in messages[2:]:  # a retry: the CLI takes one prompt, so the earlier turns become text
            prompt += f"\n\n[{m['role']}]\n{m['content']}"
        cmd = ["claude", "-p", "--model", self.model, "--output-format", "json", "--system-prompt", system,
               "--json-schema", json.dumps(schema), "--tools", "", "--strict-mcp-config", "--setting-sources", "",
               "--no-session-persistence", "--effort", "low"]
        if os.environ.get("ANTHROPIC_API_KEY"):
            cmd.insert(1, "--bare")
        # An empty working directory, so no project file (CLAUDE.md, settings) reaches the model.
        with tempfile.TemporaryDirectory() as empty:
            p = subprocess.run(cmd, input=prompt, capture_output=True, text=True, cwd=empty, timeout=self.timeout)
        if p.returncode != 0:
            raise ProviderError(f"claude exited {p.returncode}: {p.stderr.strip()[:200]}")
        d = json.loads(p.stdout)
        if d.get("is_error"):
            raise ProviderError(f"claude error: {str(d.get('result'))[:200]}")
        out = d.get("structured_output")
        content = json.dumps(out, sort_keys=True) if out is not None else d["result"]
        u = d.get("usage") or {}
        tin = sum(u.get(k) or 0 for k in ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens"))
        served = ",".join(sorted(d.get("modelUsage") or {})) or self.model
        return (content, served, tin, u.get("output_tokens") or 0, d.get("total_cost_usd") or 0.0,
                d["duration_api_ms"] / 1000)
