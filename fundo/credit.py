"""Part 2: features, the offer rule, and mislabel sensitivity."""
import random
from datetime import date, timedelta

from .evaluate import p95
from .taxonomy import HIGH_RISK, NONE, direction, is_revenue


def business_days(start, end):
    d0, d1 = date.fromisoformat(start), date.fromisoformat(end)
    return sum(1 for i in range((d1 - d0).days + 1) if (d0 + timedelta(days=i)).weekday() < 5)


def history(txns):
    """The one place history length comes from: first and last transaction date in the file.
    run.py and review.py both use it; application metadata does not carry it."""
    dates = sorted(t["date"] for t in txns)
    days = (date.fromisoformat(dates[-1]) - date.fromisoformat(dates[0])).days + 1
    return {"start": dates[0], "end": dates[-1], "history_days": days}


def features(txns, labels, biz, months_divisor=None):
    """labels: transaction_id -> {group, is_business}. Revenue is re-derived here.

    months_divisor=None uses the observed history (days / 30); pass 3 to see the
    naive 'every file is 90 days' calculation.
    """
    dep = rev = debits = hr = funder = 0.0
    nsf = od = 0
    for t in txns:
        lab = labels[t["transaction_id"]]
        amt, dirn, g = abs(t["amount"]), direction(t["amount"]), lab["group"]
        if dirn == "credit":
            dep += amt
            if is_revenue(dirn, g, lab["is_business"]):
                rev += amt
        else:
            debits += amt
            hr += amt if g in HIGH_RISK else 0
            funder += amt if g == "active_advance" else 0
        nsf += g == "nsf"
        od += g == "overdraft"
    months = months_divisor or biz["history_days"] / 30.0
    amr = rev / months
    daily_funder = funder / max(1, business_days(biz["start"], biz["end"]))  # a weekend-only file has 0 weekdays
    return {"avg_monthly_revenue": amr, "revenue_share_of_deposits": rev / dep if dep else 0.0,
            "nsf_count": nsf, "overdraft_count": od, "high_risk_share_of_debits": hr / debits if debits else 0.0,
            "funder_daily_payment": daily_funder, "offer": offer(amr, daily_funder, nsf)}


def offer(avg_monthly_revenue, funder_daily_payment, nsf_count):
    """The rule from the brief, unchanged: 1.2 x monthly revenue - 20 x other funders' daily payments,
    zero if more than 5 NSFs. Floored at zero."""
    if nsf_count > 5:
        return 0.0
    return max(0.0, 1.2 * avg_monthly_revenue - 20 * funder_daily_payment)


# ---------------------------------------------------------------------------
# Sensitivity: inject random mislabels of one type into the TRUE labels.
# ---------------------------------------------------------------------------
def _eligible(kind, t, lab):
    dirn, g = direction(t["amount"]), lab["group"]
    rev = is_revenue(dirn, g, lab["is_business"])
    return {
        "missed_revenue": dirn == "credit" and rev,
        "false_revenue": dirn == "credit" and not rev,
        "missed_advance": dirn == "debit" and g == "active_advance",
        "false_advance": dirn == "debit" and g == NONE,
        "missed_nsf": g == "nsf",
        "false_nsf": dirn == "debit" and g == NONE,
        "missed_high_risk": g in HIGH_RISK,
        "false_high_risk": dirn == "debit" and g == NONE,
    }[kind]


_FLIP = {"missed_revenue": {"group": "internal_transfer"}, "false_revenue": {"group": NONE, "is_business": True},
         "missed_advance": {"group": NONE}, "false_advance": {"group": "active_advance"},
         "missed_nsf": {"group": NONE}, "false_nsf": {"group": "nsf"},
         "missed_high_risk": {"group": NONE}, "false_high_risk": {"group": "hr_other"}}
ERROR_KINDS = list(_FLIP)


def sensitivity(dataset, truth_labels, rates=(0.02, 0.05, 0.10), trials=200, seed=7):
    """dataset: list of (biz, txns). Returns rows of mean effects per (kind, rate)."""
    rng = random.Random(seed)
    base = {b["business_id"]: features(txns, truth_labels, b) for b, txns in dataset}
    rows = []
    for kind in ERROR_KINDS:
        for rate in rates:
            d_offer, d_abs, flips, d_rev, d_nsf, d_hr, n_flipped = [], [], 0, [], [], [], 0
            for _ in range(trials):
                for b, txns in dataset:
                    labels = {t["transaction_id"]: truth_labels[t["transaction_id"]] for t in txns}
                    for t in txns:
                        lab = truth_labels[t["transaction_id"]]
                        if _eligible(kind, t, lab) and rng.random() < rate:
                            labels[t["transaction_id"]] = {**lab, **_FLIP[kind]}
                            n_flipped += 1
                    f, f0 = features(txns, labels, b), base[b["business_id"]]
                    d_offer.append(f["offer"] - f0["offer"])
                    d_abs.append(abs(f["offer"] - f0["offer"]))
                    d_rev.append(f["avg_monthly_revenue"] - f0["avg_monthly_revenue"])
                    d_nsf.append(f["nsf_count"] - f0["nsf_count"])
                    d_hr.append(f["high_risk_share_of_debits"] - f0["high_risk_share_of_debits"])
                    flips += (f["offer"] > 0) != (f0["offer"] > 0)
            n = len(d_offer)
            rows.append({"kind": kind, "rate": rate, "mean_offer_change": sum(d_offer) / n,
                         "mean_abs_offer_change": sum(d_abs) / n, "p95_abs_offer_change": p95(d_abs),
                         "offer_change_per_mislabel": sum(d_offer) / n_flipped if n_flipped else 0.0,
                         "mean_revenue_change": sum(d_rev) / n,
                         "mean_nsf_change": sum(d_nsf) / n, "mean_high_risk_share_change": sum(d_hr) / n,
                         "decision_flip_rate": flips / n})
    return rows
