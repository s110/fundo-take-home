"""Review one Plaid /transactions/get response of your own. Nothing is scored: there is no ground truth.

  python3 review.py their_file.json --name "Acme LLC" --owner "Jane Doe" --industry restaurant
  python3 review.py their_file.json --provider sonnet --offline

Prints every pattern the reviewer changed or sent to a person, and the features and offer before and after.
Writes <file>.review.jsonl next to the input, and keeps the model replies in <file>.cache.jsonl (not in
the committed cache, so a private file never reaches the repository).
"""
import argparse
import json
from pathlib import Path

from fundo import credit, engine, reviewer
from fundo.llm import LLM, PROVIDERS


def load_plaid(path):
    """Read the file and fill the fields the pipeline needs, with a warning for each gap."""
    plaid = json.loads(Path(path).read_text())
    txns = [t for t in plaid.get("transactions") or []
            if t.get("transaction_id") and isinstance(t.get("amount"), (int, float)) and t.get("date")]
    if not txns:
        raise SystemExit(f"no usable transactions in {path}")
    if len(txns) < len(plaid.get("transactions") or []):
        print("WARNING: skipped transactions with no transaction_id, amount or date")
    total = plaid.get("total_transactions")
    if isinstance(total, int) and total > len(txns):
        print(f"WARNING: the file has {len(txns)} of {total} transactions; Plaid paginates. Fetch every page first.")
    for t in txns:
        if not t.get("original_description"):
            t["original_description"] = t.get("name") or t.get("merchant_name") or ""
            print(f"WARNING: {t['transaction_id']} has no original_description; using the cleaned name")
        pfc = t.get("personal_finance_category") or {}
        t["personal_finance_category"] = {"detailed": pfc.get("detailed") or "UNKNOWN",
                                          "confidence_level": pfc.get("confidence_level") or "UNKNOWN"}
        t["account_id"] = t.get("account_id") or "unknown"
    known = {a["account_id"]: a.get("subtype") or a.get("type") or "unknown"
             for a in plaid.get("accounts") or [] if a.get("account_id")}
    for acc in sorted({t["account_id"] for t in txns} - set(known)):
        known[acc] = f"unknown account {acc}"
    plaid["accounts"] = [{"account_id": a, "subtype": s} for a, s in known.items()]
    plaid["transactions"] = txns
    return plaid


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("plaid_json")
    ap.add_argument("--name", default="Unknown business")
    ap.add_argument("--owner", default="unknown")
    ap.add_argument("--industry", default="unknown")
    ap.add_argument("--provider", choices=list(PROVIDERS), default="haiku")
    ap.add_argument("--offline", action="store_true")
    args = ap.parse_args()

    plaid = load_plaid(args.plaid_json)
    txns = plaid["transactions"]
    biz = {"business_id": Path(args.plaid_json).stem, "name": args.name, "owner": args.owner,
           "industry": args.industry, **credit.history(txns)}
    if biz["history_days"] < 85:
        print(f"WARNING: {biz['history_days']} days of history; monthly figures use the observed days")
    legacy = engine.label_all(txns)
    llm = LLM(args.provider, offline=args.offline, cache_path=Path(args.plaid_json).with_suffix(".cache.jsonl"))
    decisions, _ = reviewer.review([(biz, plaid)], legacy, llm)

    out = Path(args.plaid_json).with_suffix(".review.jsonl")
    out.write_text("".join(json.dumps(decisions[t], sort_keys=True) + "\n" for t in sorted(decisions)))
    shown, unreviewed = {}, set()
    for r in decisions.values():
        if r["action"] == "unreviewed":
            unreviewed.add(r["pattern_id"])
        elif r["action"] != "keep":
            shown.setdefault(r["pattern_id"], []).append(r)
    if unreviewed:
        print(f"WARNING: {len(unreviewed)} patterns unreviewed (no model reply); they keep the keyword label")
    for pid, rs in sorted(shown.items()):
        r, s = rs[0], rs[0]["suggestion"]
        print(f"\n{r['action']:<16} {len(rs):>3} txns  {r['legacy']['group']} -> {s['group']} "
              f"(business={s['is_business']}, confidence {s['confidence']})\n  {r['description'][:100]}\n  {s['reason']}")
    for name in ("legacy", "final"):
        labels = {tid: {"group": r[name]["group"], "is_business": r[name]["is_business"]} for tid, r in decisions.items()}
        f = credit.features(txns, labels, biz)
        print(f"\n{name:>8}: " + ", ".join(f"{k}={v:,.2f}" if isinstance(v, float) else f"{k}={v}" for k, v in f.items()))
    print(f"\nwrote {out}")


if __name__ == "__main__":
    main()
