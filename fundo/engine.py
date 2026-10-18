"""The legacy keyword engine. It stands in for the production labeler and is imperfect on purpose:

* keywords match whole words in a normalized description (upper case, punctuation -> space), but the
  keyword lists are not normalized, so a keyword with punctuation ("FORWARD-FINANCING") never matches;
* a counterparty that shares a word with a group collides (SQUARE INC vs SQUARE CAPITAL, a customer that
  is a CASINO, a supplier named LEVY, an employee's GARNISHMENT that the business only remits);
* the lists are incomplete (XFER, CH13, PRIZEPICKS, new funders, returned-item credits);
* every P2P credit except Venmo counts as business.
The keyword lists were written once, before any model run, and are never tuned.
"""
import re

from .taxonomy import DIRECTIONS, NONE, direction, is_revenue

KEYWORDS = {
    "nsf": ["NSF", "INSUFFICIENT FUNDS FEE", "RETURNED ITEM FEE"],
    "overdraft": ["OVERDRAFT", "OD FEE", "OD ITEM FEE"],
    "active_advance": ["PEARL CAPITAL", "LIBERTAS", "YELLOWSTONE", "FORWARD-FINANCING", "ONDECK", "CREDIBLY",
                       "KAPITUS", "MCA"],
    "revenue_verification": ["SQUARE", "SQ", "STRIPE", "SHOPIFY", "TOAST", "CLOVER", "PAYPAL"],
    "internal_transfer": ["TRANSFER", "TRSF"],
    "ucc": ["UCC"],
    "hr_gambling": ["CASINO", "DRAFTKINGS", "FANDUEL", "BETMGM", "LOTTERY"],
    "hr_bankruptcy": ["BANKRUPTCY", "CHAPTER 13", "CH 13 TRUSTEE"],
    "hr_debt_settlement": ["DEBT SETTLEMENT", "NATIONAL DEBT RELIEF"],
    "hr_garnishment": ["GARNISHMENT", "GARNISH", "LEVY"],
    "hr_other": ["COINBASE", "PAWN", "BAIL BOND", "CRYPTO"],
    "not_avg_revenue": ["LOAN", "SBA", "TAX REF", "IRS TREAS", "REFUND", "REVERSAL"],
    "auto_deposit": ["DEPOSIT", "MOBILE DEPOSIT", "ATM DEPOSIT", "BRANCH DEPOSIT"],
}
# When several groups match, the first one in this order wins.
PRECEDENCE = ["nsf", "overdraft", "active_advance", "revenue_verification", "internal_transfer", "ucc",
              "hr_gambling", "hr_bankruptcy", "hr_debt_settlement", "hr_garnishment", "hr_other",
              "not_avg_revenue", "auto_deposit"]
PERSONAL = ["NETFLIX", "SPOTIFY", "TARGET", "DRAFTKINGS", "FANDUEL", "VENMO", "COINBASE"]


def normalize(desc):
    return " " + re.sub(r"[^A-Z0-9]+", " ", desc.upper()).strip() + " "


def label(txn):
    norm = normalize(txn["original_description"])
    dirn = direction(txn["amount"])
    matched = {g: [k for k in KEYWORDS[g] if f" {k} " in norm] for g in PRECEDENCE}
    matched = {g: ks for g, ks in matched.items() if ks and dirn in DIRECTIONS[g]}
    group = next((g for g in PRECEDENCE if g in matched), NONE)
    is_business = not any(f" {k} " in norm for k in PERSONAL)
    return {"group": group, "is_business": is_business, "is_revenue": is_revenue(dirn, group, is_business),
            "matched": matched}


def label_all(txns):
    return {t["transaction_id"]: label(t) for t in txns}
