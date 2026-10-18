"""The 13 keyword groups, and the revenue rule that every labeler shares.

Revenue is not a label. Code derives it from the direction of the money, the group and the
business/personal flag, so neither the keyword engine nor the model can set it directly.
"""

NONE = "none"

GROUPS = [
    "not_avg_revenue",       # money in that is not sales: loan proceeds, refunds received, owner money
    "revenue_verification",  # payout from a card processor or marketplace
    "nsf",                   # NSF fee, or a payment returned unpaid (ACH return R01/R09)
    "overdraft",             # overdraft fee or charge
    "internal_transfer",     # money between the business's own accounts
    "ucc",                   # UCC filing or search fee
    "active_advance",        # another funder: advance or loan proceeds, or its fixed repayments
    "auto_deposit",          # deposit with no named counterparty (branch, ATM, mobile check)
    "hr_gambling",
    "hr_bankruptcy",
    "hr_debt_settlement",
    "hr_garnishment",
    "hr_other",              # crypto exchanges, pawn shops, bail bonds
]
ALL_LABELS = GROUPS + [NONE]
HIGH_RISK = {"hr_gambling", "hr_bankruptcy", "hr_debt_settlement", "hr_garnishment", "hr_other"}
RISK_GROUPS = HIGH_RISK | {"active_advance", "nsf", "overdraft"}  # groups that lower an offer or flag risk

# A business credit is revenue only in one of these groups.
REVENUE_ELIGIBLE = {NONE, "revenue_verification", "auto_deposit"}

# The directions where each group is possible. Code rejects a model reply that breaks this.
DIRECTIONS = {
    "not_avg_revenue": {"credit"},
    "revenue_verification": {"credit"},
    "auto_deposit": {"credit"},
    "nsf": {"debit", "credit"},              # credit = a returned payment, with no fee
    "overdraft": {"debit"},
    "internal_transfer": {"debit", "credit"},
    "ucc": {"debit"},
    "active_advance": {"debit", "credit"},   # credit = funding, debit = repayment
    "hr_gambling": {"debit", "credit"},
    "hr_bankruptcy": {"debit"},
    "hr_debt_settlement": {"debit"},
    "hr_garnishment": {"debit"},
    "hr_other": {"debit", "credit"},
    NONE: {"debit", "credit"},
}


def direction(plaid_amount):
    """Plaid sign convention: a positive amount is money out of the account."""
    return "debit" if plaid_amount > 0 else "credit"


def is_revenue(dirn, group, is_business):
    return dirn == "credit" and is_business and group in REVENUE_ELIGIBLE
