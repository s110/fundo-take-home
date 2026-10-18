"""Model access through a committed response cache.

Cache key = sha256(provider, model, schema, messages). A run with the same prompts reads the cache and
makes no network call. With offline=True a cache miss acts like a provider outage, so the caller falls
back to the keyword label. That is how a clean checkout reproduces the committed output with no key.

Providers:
  deepseek  DeepSeek HTTP API (OpenAI format), JSON mode, thinking off. Needs DEEPSEEK_API_KEY.
  haiku     Claude Haiku through the Claude Code CLI (`claude -p`), with a JSON schema.
  sonnet    Claude Sonnet, the same way.
The CLI path exists because I had a Claude subscription and no Anthropic API key. In production the
same prompt goes to the Messages API. The CLI adds a short preamble of its own to the system prompt,
which the cost and latency figures include.
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

CACHE_PATH = Path("cache/llm_responses.jsonl")

PROVIDERS = {
    # USD per 1M tokens at the PEAK list price (the off-peak price is half), so the cost is an upper bound.
    "deepseek": {"model": "deepseek-flash", "usd_in": 0.30, "usd_in_cached": 0.006, "usd_out": 1.20},
    "haiku": {"model": "claude-haiku-5-5"},
    "sonnet": {"model": "claude-sonnet-5-5"},
}


class ProviderError(Exception):
    pass


class LLM:
    def __init__(self, provider, offline=False, timeout=120):
        self.provider, self.offline, self.timeout = provider, offline, timeout
        self.model = PROVIDERS[provider]["model"]
        self.lock = threading.Lock()
        self.cache = {}
        if CACHE_PATH.exists():
            for line in CACHE_PATH.read_text().splitlines():
                rec = json.loads(line)
                self.cache[rec["key"]] = rec

    def key(self, messages, schema):
        blob = json.dumps({"provider": self.provider, "model": self.model, "schema": schema, "messages": messages},
                          sort_keys=True)
        return hashlib.sha256(blob.encode()).hexdigest()

    def chat(self, messages, schema):
        """Return the cache record of the reply. Raises ProviderError when no reply is available."""
        k = self.key(messages, schema)
        with self.lock:
            if k in self.cache:
                return {**self.cache[k], "from_cache": True}
        if self.offline:
            raise ProviderError("offline and not in the cache")
        t0 = time.time()
        try:
            call = self._deepseek if self.provider == "deepseek" else self._claude_cli
            content, served, tin, tout, usd, api_seconds = call(messages, schema)
        except (OSError, subprocess.SubprocessError, KeyError, ValueError) as e:  # OSError covers URLError, timeouts
            raise ProviderError(f"{type(e).__name__}: {e}") from e
        rec = {"key": k, "provider": self.provider, "model": self.model, "served_model": served,
               "content": content, "tokens_in": tin, "tokens_out": tout, "usd": round(usd, 6),
               "latency_s": round(api_seconds if api_seconds is not None else time.time() - t0, 3),
               "created": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
        with self.lock:
            self.cache[k] = rec
            CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
            with CACHE_PATH.open("a") as f:
                f.write(json.dumps(rec, sort_keys=True) + "\n")
        return {**rec, "from_cache": False}

    def _deepseek(self, messages, schema):
        key = os.environ.get("DEEPSEEK_API_KEY")
        if not key:
            raise ProviderError("DEEPSEEK_API_KEY is not set")
        body = {"model": self.model, "messages": messages, "temperature": 0, "max_tokens": 400,
                "response_format": {"type": "json_object"}, "thinking": {"type": "disabled"}}
        req = urllib.request.Request("https://api.deepseek.com/chat/completions", json.dumps(body).encode(),
                                     {"Content-Type": "application/json", "Authorization": f"Bearer {key}"})
        t0 = time.time()
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            d = json.loads(r.read())
        u, p = d.get("usage", {}), PROVIDERS["deepseek"]
        hit = u.get("prompt_cache_hit_tokens", 0)
        tin, tout = u.get("prompt_tokens", 0), u.get("completion_tokens", 0)
        usd = ((tin - hit) * p["usd_in"] + hit * p["usd_in_cached"] + tout * p["usd_out"]) / 1e6
        return d["choices"][0]["message"]["content"], d.get("model", self.model), tin, tout, usd, time.time() - t0

    def _claude_cli(self, messages, schema):
        system = messages[0]["content"]
        prompt = messages[1]["content"]
        for m in messages[2:]:  # a retry: the CLI takes one prompt, so earlier turns become text
            prompt += f"\n\n[{m['role']}]\n{m['content']}"
        cmd = ["claude", "-p", "--model", self.model, "--output-format", "json", "--system-prompt", system,
               "--json-schema", json.dumps(schema), "--tools", "", "--strict-mcp-config", "--setting-sources", "",
               "--no-session-persistence", "--effort", "low"]
        # An empty working directory, so no project file (CLAUDE.md, settings) reaches the model.
        with tempfile.TemporaryDirectory() as empty:
            p = subprocess.run(cmd, input=prompt, capture_output=True, text=True, cwd=empty, timeout=self.timeout)
        if p.returncode != 0:
            raise ProviderError(f"claude exited {p.returncode}: {p.stderr.strip()[:200]}")
        d = json.loads(p.stdout)
        if d.get("is_error"):
            raise ProviderError(f"claude error: {d.get('result', '')[:200]}")
        out = d.get("structured_output")
        content = json.dumps(out, sort_keys=True) if out is not None else d["result"]
        u = d.get("usage", {})
        tin = u.get("input_tokens", 0) + u.get("cache_creation_input_tokens", 0) + u.get("cache_read_input_tokens", 0)
        served = ",".join(sorted(d.get("modelUsage", {}))) or self.model
        return content, served, tin, u.get("output_tokens", 0), d.get("total_cost_usd", 0.0), d["duration_api_ms"] / 1000
