"""Cost at a scale anyone actually runs, from OUR measured token counts and
Bright Data's published rates. Every input is stated so the arithmetic can be
disagreed with.
"""
import json
t = json.load(open("data/token_cost.json"))

SKUS_PER_DAY = 100_000
DAYS = 30
UNLOCKER_PAYG = 1.5 / 1000          # $/request, published pay-as-you-go
SCALE_FEE, SCALE_INC, SCALE_RATE = 499.0, 383_000, 1.3 / 1000
IN_TOK_PER_M = 3.00                 # a mid-tier model's input rate, $/M tokens

md_median = t["markdown_tokens_median"]
md_amazon = t["by_retailer_median"]["amazon"]
struct_per_row = t["structured_answer_tokens"] / 41

def fetch_month(reqs):
    payg = reqs * UNLOCKER_PAYG
    over = max(0, reqs - SCALE_INC)
    return payg, SCALE_FEE + over * SCALE_RATE

reqs = SKUS_PER_DAY * DAYS
payg, scale = fetch_month(reqs)

def read_month(tok_per_page):
    return SKUS_PER_DAY * DAYS * tok_per_page / 1_000_000 * IN_TOK_PER_M

rows = [
    ("markdown, our median page", md_median, read_month(md_median)),
    ("markdown, Amazon-weighted", md_amazon, read_month(md_amazon)),
    ("structured JSON", struct_per_row, read_month(struct_per_row)),
]
print(f"assumptions: {SKUS_PER_DAY:,} pages/day, {DAYS} days, model input ${IN_TOK_PER_M}/M tokens")
print(f"fetch, {reqs:,} requests/month: pay-as-you-go ${payg:,.0f}   Scale plan ${scale:,.0f}\n")
print(f"{'what the agent reads':30} {'tokens/page':>12} {'model cost/month':>18} {'vs fetch':>10}")
for label, tpp, cost in rows:
    print(f"{label:30} {tpp:>12,.0f} {'$'+format(cost,',.0f'):>18} {cost/scale:>9.1f}x")
print()
print(f"markdown -> structured saves ${read_month(md_median)-read_month(struct_per_row):,.0f}/month at the median page,")
print(f"and ${read_month(md_amazon)-read_month(struct_per_row):,.0f}/month if your catalogue is Amazon-heavy.")
json.dump({"skus_per_day": SKUS_PER_DAY, "days": DAYS, "fetch_payg": round(payg),
           "fetch_scale": round(scale), "model_input_per_m": IN_TOK_PER_M,
           "read_cost": {l: round(c) for l, _, c in rows},
           "tokens_per_page": {l: round(v) for l, v, _ in rows}},
          open("data/cost_model.json", "w"), indent=2)
