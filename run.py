"""Run the pipeline: data -> keyword engine -> reviewer -> evaluation -> credit impact -> gate.

  python3 run.py --offline                          # every committed run, from the cache; no key, no network
  python3 run.py --provider haiku --split dev       # one run; cache misses call the model
  python3 run.py --provider sonnet --split holdout --offline

Each run writes runs/<provider>/<split>/. --all (the default with --offline and no --provider) also writes
runs/summary.md, runs/sensitivity.md and one gate report per candidate in runs/gate/.
"""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path

import gate
from fundo import credit, engine, evaluate, generate, reviewer
from fundo.llm import CACHE_PATH, LLM, PROVIDERS, display

INCUMBENT = "haiku"
CANDIDATES = ["sonnet", "deepseek", "deepseek-think"]
SPLITS = ["dev", "holdout"]
SAMPLES = [1, 2]  # extra replies per model and split, beyond the committed run (sample 0)


def money(x):
    return f"${x:,.0f}"


def pct(x):
    return f"{100 * x:.1f}%"


def rounded(x):
    """6 decimals, so float sums print the same on every Python version."""
    if isinstance(x, float):
        return round(x, 6)
    if isinstance(x, dict):
        return {k: rounded(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [rounded(v) for v in x]
    return x


def sha(obj):
    blob = obj if isinstance(obj, bytes) else json.dumps(obj, sort_keys=True).encode()
    return hashlib.sha256(blob).hexdigest()[:16]


_SPLITS = {}


def load_split(split):
    """Generate a split once per process; every run of that split shares it."""
    if split not in _SPLITS:
        _SPLITS[split] = _load_split(split)
    return _SPLITS[split]


def _load_split(split):
    businesses, gt = generate.write(split)
    dataset = []
    for b in businesses:
        plaid = json.loads(Path(f"data/{split}/plaid/{b['business_id']}.json").read_text())
        b.update(credit.history(plaid["transactions"]))
        dataset.append((b, plaid))
    return businesses, dataset, gt


def review_split(dataset, llm):
    legacy = {}
    for _, plaid in dataset:
        legacy.update(engine.label_all(plaid["transactions"]))
    return reviewer.review(dataset, legacy, llm)


def features(dataset, decisions, gt):
    labels = lambda key: {tid: {"group": r[key]["group"], "is_business": r[key]["is_business"]}
                          for tid, r in decisions.items()}
    truth_labels = {tid: {"group": g["group"], "is_business": g["is_business"]} for tid, g in gt.items()}
    # Estimate, not measured: every pattern in the underwriter queue resolved to its true label.
    resolved = {tid: truth_labels[tid] if r["action"] in evaluate.TO_HUMAN else lab
                for (tid, r), lab in zip(decisions.items(), labels("final").values())}
    return {b["business_id"]: {name: credit.features(p["transactions"], lab, b) for name, lab in
                               (("legacy", labels("legacy")), ("reviewed", labels("final")),
                                ("queue_resolved", resolved), ("truth", truth_labels))}
            for b, p in dataset}


def run_one(provider, split, offline, out_root="runs"):
    businesses, dataset, gt = load_split(split)
    llm = LLM(provider, offline=offline)
    decisions, calls = review_split(dataset, llm)
    ev = evaluate.evaluate(decisions, calls, gt, businesses)
    feats = features(dataset, decisions, gt)
    used = sorted({c["key"] for c in calls})
    manifest = {  # what a replay needs to rebuild every decision of this run
        "run": {"provider": provider, "model": llm.model, "split": split,
                "served_models": sorted({c["served_model"] for c in calls})},
        "inputs_sha": {b["business_id"]: sha(Path(f"data/{split}/plaid/{b['business_id']}.json").read_bytes())
                       for b in businesses},
        "keyword_engine_sha": sha([engine.KEYWORDS, engine.PRECEDENCE, engine.PERSONAL]),
        "prompt_sha": sha(reviewer.SYSTEM), "schema_sha": sha(reviewer.SCHEMA), "policy": reviewer.POLICY,
        "cache_entries_used": len(used), "replies_sha": sha([[k, llm.cache[k]["content"]] for k in used]),
    }
    out = Path(out_root) / provider / split
    write(out, businesses, decisions, calls, ev, feats, manifest)
    h = ev["headline"]
    print(f"{provider:>8} {split:<7} Q1 {h['Q1_legacy_pp']:.1f} -> {h['Q1_gross_revenue_error_pp']:.1f} pp, "
          f"queue {h['U2_queue_per_app']:.1f}/app, false flags {h['U1_false_flags_per_app']:.1f}/app, "
          f"hard rules {ev['hard_rules']}, calls {len(calls)}")
    return ev, feats, manifest


def write(out, businesses, decisions, calls, ev, feats, manifest):
    out.mkdir(parents=True, exist_ok=True)
    dump = lambda rows: "".join(json.dumps(rounded(r), sort_keys=True) + "\n" for r in rows)
    (out / "decisions.jsonl").write_text(dump(decisions[t] for t in sorted(decisions)))
    (out / "calls.jsonl").write_text(dump(sorted(calls, key=lambda c: (c["pattern_id"], c["key"]))))
    (out / "patterns.jsonl").write_text(dump(ev["pattern_rows"]))
    metrics = {k: v for k, v in ev.items() if k not in ("final_wrong", "pattern_rows")}
    metrics.update(features=feats, **manifest)
    (out / "metrics.json").write_text(json.dumps(rounded(metrics), indent=1, sort_keys=True) + "\n")
    (out / "report.md").write_text(report(businesses, ev, feats, manifest))
    (out / "errors.md").write_text(errors_page(ev["final_wrong"]))


def offers(feats):
    kinds = ("legacy", "reviewed", "queue_resolved")
    over = {w: sum(max(0, f[w]["offer"] - f["truth"]["offer"]) for f in feats.values()) for w in kinds}
    under = {w: sum(max(0, f["truth"]["offer"] - f[w]["offer"]) for f in feats.values()) for w in kinds}
    return over, under


def report(businesses, ev, feats, manifest):
    names = {b["business_id"]: b["name"] for b in businesses}
    h, f, hr = ev["headline"], ev["flags"], ev["hard_rules"]
    run = manifest["run"]
    L = [f"# {display(run['provider'])} on {run['split']} (generated by run.py; do not edit)", "",
         f"Served model(s): {', '.join(run['served_models']) or 'none'}. Metric ids are defined in EVAL.md.", "",
         "## Headline", "", "| metric | keyword labels | after review |", "|---|---:|---:|",
         f"| Q1 gross revenue error | {h['Q1_legacy_pp']:.1f} pp | {h['Q1_gross_revenue_error_pp']:.1f} pp |",
         f"| Q2 risk-label recall | {h['Q2_legacy_pp']:.1f} pp | {h['Q2_risk_label_recall_pp']:.1f} pp |",
         f"| wrong labels | {f['legacy_wrong']} ({money(f['legacy_wrong_usd'])}) | {f['final_wrong']} "
         f"({money(f['final_wrong_usd'])}) |", "",
         f"- U1 false flags per application: {h['U1_false_flags_per_app']:.2f}. U2 queue per application: "
         f"{h['U2_queue_per_app']:.2f} patterns ({f['queued_transactions']} transactions).",
         f"- L1 p95 model time per pattern: {h['L1_p95_latency_s']:.2f} s. Model cost per application: "
         f"USD {h['model_usd_per_app']:.4f}. C1 cost per application with underwriter time: USD {h['C1_cost_per_app_usd']:.3f}.",
         f"- Hard rules: H1 PII leaks {hr['H1_pii_leaks']}; H2 injection handled {hr['H2_injection_ok']}/"
         f"{hr['H2_injection_total']}; H3 failed replies {hr['H3_failed_replies']}; H4 wrong offer-raising changes "
         f"{hr['H4_wrong_offer_raising_applied']}.",
         f"- {f['transactions']} transactions in {f['patterns']} patterns, {f['model_calls']} model calls. Reply status: "
         f"{f['statuses']}.",
         f"- Flags: {f['flagged']} transactions, precision {pct(f['flag_precision'])}, recall {pct(f['flag_recall'])}. "
         f"Auto-applied: {f['applied']}, correct {f['applied_correct']}.",
         f"- Hard negatives (look wrong, keyword label is right): {f['hard_negatives']}; flagged "
         f"{f['hard_negatives_flagged']}; changed to a wrong label {f['hard_negatives_changed_wrongly']}.", "",
         "## Text written by the counterparty", "",
         "| pattern | pushes | code saw it | model saw it | model suggestion | followed | action | final correct |",
         "|---|---|---|---|---|---|---|---|"]
    for i in ev["injection"]:
        L.append(f"| `{i['pattern_id'][:60]}` | {i['pushes']} | {i['code_detected']} | {i['model_detected']} | "
                 f"{i['suggestion']} | {i['followed']} | {i['action']} | {i['final_correct']} |")
    L += ["", "## Monthly revenue per business", "",
          "Gross error = dollars per month on the wrong side of the revenue line.", "",
          "| business | true revenue / month | keyword gross error | reviewed gross error |", "|---|---:|---:|---:|"]
    for b, r in ev["revenue_by_business"].items():
        L.append(f"| {b} {names[b]} | {money(r['rev_true'])} | {money(r['rev_wrong_legacy'])} | "
                 f"{money(r['rev_wrong_final'])} |")
    L += ["", "## Credit features and offer", "",
          "Offer = 1.2 x average monthly revenue - 20 x other funders' daily payment; 0 if NSF count > 5.", "",
          "| business | labels | monthly revenue | revenue / deposits | NSF | OD | high-risk / debits | funder $/day | offer |",
          "|---|---|---:|---:|---:|---:|---:|---:|---:|"]
    for b, fs in feats.items():
        for which in ("legacy", "reviewed", "truth"):
            x = fs[which]
            L.append(f"| {b if which == 'legacy' else ''} | {which} | {money(x['avg_monthly_revenue'])} | "
                     f"{pct(x['revenue_share_of_deposits'])} | {x['nsf_count']} | {x['overdraft_count']} | "
                     f"{pct(x['high_risk_share_of_debits'])} | {money(x['funder_daily_payment'])} | **{money(x['offer'])}** |")
    over, under = offers(feats)
    L += ["", f"Over-offer against true labels: keyword {money(over['legacy'])}, reviewed {money(over['reviewed'])}, "
          f"queue resolved {money(over['queue_resolved'])} (*estimate*). Under-offer: keyword {money(under['legacy'])}, "
          f"reviewed {money(under['reviewed'])}, queue resolved {money(under['queue_resolved'])} (*estimate*).", "",
          "## By scenario", "", "| scenario | n | keyword correct | final correct | flagged | to a person |",
          "|---|---:|---:|---:|---:|---:|"]
    for sc, v in ev["by_scenario"].items():
        L.append(f"| {sc} | {v['n']} | {v.get('legacy_ok', 0)} | {v.get('final_ok', 0)} | {v.get('flagged', 0)} | "
                 f"{v.get('to_person', 0)} |")
    return "\n".join(L) + "\n"


def errors_page(final_wrong):
    by = {}
    for r in final_wrong:
        by.setdefault(r["pattern_id"], []).append(r)
    L = ["# Labels still wrong after review (generated)", "",
         "| pattern | n | $ | keyword label | action | model suggestion (confidence) | model reason |",
         "|---|---:|---:|---|---|---|---|"]
    for pid, rs in sorted(by.items(), key=lambda kv: -sum(abs(r["amount"]) for r in kv[1])):
        r, s = rs[0], rs[0]["suggestion"] or {}
        lab = lambda x: x["group"] + ("" if x["is_business"] else " (personal)")
        L.append(f"| `{pid}` | {len(rs)} | {money(sum(abs(x['amount']) for x in rs))} | {lab(r['legacy'])} | "
                 f"{r['action']} | {lab(s) if s else ''} ({s.get('confidence', '')}) | "
                 f"{s.get('reason', '').replace('|', '/')} |")
    return "\n".join(L) + "\n"


def sensitivity_page():
    businesses, dataset, gt = load_split("dev")
    truth_labels = {tid: {"group": g["group"], "is_business": g["is_business"]} for tid, g in gt.items()}
    rows = credit.sensitivity([(b, p["transactions"]) for b, p in dataset], truth_labels)
    naive = {b["business_id"]: credit.features(p["transactions"], truth_labels, b, months_divisor=3)
             for b, p in dataset if b["history_days"] < 85}
    L = ["# Mislabel sensitivity (generated by run.py; dev set, true labels)", "",
         "Each eligible transaction of one error type is flipped with probability = rate. 200 trials x 10 businesses.", "",
         "| error type | rate | mean offer change | mean abs offer change | offer change per mislabelled txn | "
         "mean NSF change | mean high-risk share change (pp) | decisions flipped |", "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for s in rows:
        L.append(f"| {s['kind']} | {pct(s['rate'])} | {money(s['mean_offer_change'])} | {money(s['mean_abs_offer_change'])} | "
                 f"{money(s['offer_change_per_mislabel'])} | {s['mean_nsf_change']:+.2f} | "
                 f"{100 * s['mean_high_risk_share_change']:+.2f} | {pct(s['decision_flip_rate'])} |")
    for bid, x in naive.items():
        L += ["", f"Short history ({bid}): dividing by 3 months instead of observed days gives monthly revenue "
              f"{money(x['avg_monthly_revenue'])} and offer {money(x['offer'])}."]
    return "\n".join(L) + "\n"


def repeat_cache(provider):
    return Path("cache/repeats") / f"{provider}.jsonl"


def run_sample(provider, split, offline, sample):
    """The same prompts, a new reply. Sample 0 is the committed run in runs/<provider>/<split>/."""
    businesses, dataset, gt = load_split(split)
    llm = LLM(provider, offline=offline, sample=sample,
              cache_path=CACHE_PATH if sample == 0 else repeat_cache(provider))
    decisions, calls = review_split(dataset, llm)
    ev = evaluate.evaluate(decisions, calls, gt, businesses)
    over, _ = offers(features(dataset, decisions, gt))
    finals = {r["pattern_id"]: (r["action"], r["final"]["group"], r["final"]["is_business"]) for r in decisions.values()}
    return {"headline": ev["headline"], "hard_rules": ev["hard_rules"], "over_offer": over["reviewed"],
            "statuses": ev["flags"]["statuses"], "finals": finals}


def repeats_page(offline):
    L = ["# Run-to-run spread (generated by run.py; do not edit)", "",
         "Each model answers the same prompts again (samples 1 and 2; sample 0 is the committed run). The bootstrap "
         "in the gate resamples patterns; it does not see this spread.", "",
         "| model | split | sample | Q1 pp | Q2 pp | U2 queue/app | L1 p95 s | C1 USD/app | H2 | over-offer | "
         "patterns with a new action or label vs sample 0 |", "|---|---|---:|---:|---:|---:|---:|---:|---|---:|---:|"]
    spread = []
    for provider in [INCUMBENT] + CANDIDATES:
        for split in SPLITS:
            rows = [run_sample(provider, split, offline, k) for k in [0] + SAMPLES]
            for k, r in zip([0] + SAMPLES, rows):
                h, hr = r["headline"], r["hard_rules"]
                moved = sum(r["finals"][pid] != f for pid, f in rows[0]["finals"].items())
                L.append(f"| {display(provider)} | {split} | {k} | {h['Q1_gross_revenue_error_pp']:.1f} | "
                         f"{h['Q2_risk_label_recall_pp']:.1f} | {h['U2_queue_per_app']:.2f} | {h['L1_p95_latency_s']:.2f} | "
                         f"{h['C1_cost_per_app_usd']:.3f} | {hr['H2_injection_ok']}/{hr['H2_injection_total']} | "
                         f"{money(r['over_offer'])} | {moved} of {len(r['finals'])} |")
            q1 = [r["headline"]["Q1_gross_revenue_error_pp"] for r in rows]
            c1 = [r["headline"]["C1_cost_per_app_usd"] for r in rows]
            spread.append(f"| {display(provider)} | {split} | {min(q1):.1f} to {max(q1):.1f} | "
                          f"{math.fsum(q1) / len(q1):.1f} | {min(c1):.3f} to {max(c1):.3f} |")
    L += ["", "## Range over the three samples", "", "| model | split | Q1 pp | Q1 mean | C1 USD/app |",
          "|---|---|---|---:|---|"] + spread
    return "\n".join(L) + "\n"


def run_all(offline):
    results = {}
    for provider in [INCUMBENT] + CANDIDATES:
        for split in SPLITS:
            results[(provider, split)] = run_one(provider, split, offline)
    Path("runs/sensitivity.md").write_text(sensitivity_page())
    Path("runs/gate").mkdir(exist_ok=True)
    verdicts = {}
    for c in CANDIDATES:
        status, text = gate.gate(f"runs/{INCUMBENT}/dev", f"runs/{c}/dev", f"runs/{INCUMBENT}/holdout",
                                 f"runs/{c}/holdout")
        verdicts[c] = status
        Path(f"runs/gate/{c}_vs_{INCUMBENT}.md").write_text(text)
        print(f"gate {c} vs {INCUMBENT}: {status}")
    Path("runs/summary.md").write_text(summary(results, verdicts))
    Path("runs/repeats.md").write_text(repeats_page(offline))


def summary(results, verdicts):
    L = ["# All runs (generated by run.py; do not edit)", "",
         "| model | split | Q1 keyword | Q1 reviewed | Q2 keyword | Q2 reviewed | U1 false flags/app | U2 queue/app | "
         "L1 p95 s | model USD/app | C1 USD/app | H1-H4 | over-offer kw -> rev | under-offer kw -> rev | gate |",
         "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|---|---|"]
    for (p, s), (ev, feats, man) in results.items():
        h, hr = ev["headline"], ev["hard_rules"]
        over, under = offers(feats)
        hard = (f"{hr['H1_pii_leaks']}/{hr['H2_injection_ok']}of{hr['H2_injection_total']}/{hr['H3_failed_replies']}/"
                f"{hr['H4_wrong_offer_raising_applied']}")
        L.append(f"| {display(p)} | {s} | {h['Q1_legacy_pp']:.1f} | {h['Q1_gross_revenue_error_pp']:.1f} | "
                 f"{h['Q2_legacy_pp']:.1f} | {h['Q2_risk_label_recall_pp']:.1f} | {h['U1_false_flags_per_app']:.2f} | "
                 f"{h['U2_queue_per_app']:.2f} | {h['L1_p95_latency_s']:.2f} | {h['model_usd_per_app']:.4f} | "
                 f"{h['C1_cost_per_app_usd']:.3f} | {hard} | {money(over['legacy'])} -> {money(over['reviewed'])} | "
                 f"{money(under['legacy'])} -> {money(under['reviewed'])} | "
                 f"{'incumbent' if p == INCUMBENT else verdicts.get(p, '') if s == 'dev' else ''} |")
    cache = [json.loads(line) for line in CACHE_PATH.read_text().splitlines()]
    L += ["", "H1-H4 = PII leaks / injections handled of total / failed replies / wrong offer-raising changes.", "",
          "## Model spend (every entry in the committed cache, every iteration included)", "",
          "| model | calls | tokens in | tokens out | USD |", "|---|---:|---:|---:|---:|"]
    for prov in sorted({r["provider"] for r in cache}):
        rs = [r for r in cache if r["provider"] == prov]
        L.append(f"| {display(prov)} | {len(rs)} | {sum(r['tokens_in'] for r in rs):,} | {sum(r['tokens_out'] for r in rs):,} | "
                 f"{math.fsum(r['usd'] for r in rs):.4f} |")
    L += ["", "USD for Claude models is the list-price equivalent that the Claude Code CLI reports; I paid through a "
          "subscription. USD for DeepSeek is computed from its token counts at the peak-hour list price (fundo/llm.py)."]
    return "\n".join(L) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true", help="never call a model; a cache miss acts like an outage")
    ap.add_argument("--provider", choices=list(PROVIDERS), help="one run only (default: every committed run)")
    ap.add_argument("--split", choices=SPLITS, default="dev")
    ap.add_argument("--repeats", action="store_true", help="ask for samples 1 and 2 on both splits (cache/repeats/)")
    args = ap.parse_args()
    os.chdir(Path(__file__).resolve().parent)  # data/, runs/ and cache/ are relative to the repository
    if args.repeats:
        for provider in [args.provider] if args.provider else [INCUMBENT] + CANDIDATES:
            for split in SPLITS:
                for k in SAMPLES:
                    r = run_sample(provider, split, args.offline, k)
                    print(f"{provider} {split} sample {k}: Q1 {r['headline']['Q1_gross_revenue_error_pp']:.1f} pp, "
                          f"statuses {r['statuses']}")
    elif args.provider:
        run_one(args.provider, args.split, args.offline)
    else:
        run_all(args.offline)


if __name__ == "__main__":
    main()
