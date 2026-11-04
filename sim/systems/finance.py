"""Taxes, wages, sentiment (docs/logic/finance.md, sentiment.md; simplified)."""
from . import index


def month_end(g):
    c = g.city
    # monthly taxes 0x00488250 (finance.md 3.2): t = pop*col18*2 summed per class (common < level 9 <= elite),
    # tax = ((rate*t)/100)*50/100 per class in integer division; coverage % = taxed people / all people
    base = [0, 0]
    taxed = people = 0
    for b in index.of(g, "house"):
        if b.kind == "house" and b.occupants:
            people += b.occupants
            if b.tax_days > 0:
                taxed += b.occupants
                # x4 once after a blessed office's collector (+0x84). (+0x86, x1.1: no store to it in the exe
                # was found, so it is always 0)
                k = 8 if b.misc.pop("tax_blessed", None) else 2
                base[b.level >= 9] += b.occupants * g.cat.houses[b.level]["tax_multiplier"] * k
    tax = sum(c.tax_rate * t // 100 * 50 // 100 for t in base)
    c.tax_coverage = taxed * 100 // people if people else 0
    wages = c.wage_rate * c.employed // 120
    c.treasury += tax - wages
    c.ledger["taxes"] = c.ledger.get("taxes", 0) + tax
    c.ledger["wages"] = c.ledger.get("wages", 0) - wages
    c.months_in_debt = c.months_in_debt + 1 if c.treasury < 0 else 0
    if c.months_in_debt == 12:
        g.message("the city has been in debt for a year")
    c.last_ledger = dict(c.ledger)
    c.ledger = {}
    g.history.append(dict(date=g.date(), treasury=c.treasury, population=c.population,
                          sentiment=c.sentiment, employed=c.employed, workforce=c.workforce,
                          taxes=tax, wages=wages, immigrants=c.immigrants_month,
                          emigrants=c.emigrants_month,
                          levels=_levels(g),
                          # for the advisors (live.advisor): the closed month, its ledger, crime totals so far
                          mi=g.month_index - 1, ledger=dict(c.last_ledger), thefts=getattr(c, "thefts", 0),
                          muggings=getattr(c, "muggings", 0), vandalisms=getattr(c, "vandalisms", 0)))
    c.immigrants_month = c.emigrants_month = 0


def _levels(g):
    out = {}
    for b in index.of(g, "house"):
        if b.kind == "house" and b.occupants:
            name = g.cat.houses[b.level]["name"]
            out[name] = out.get(name, 0) + 1
    return out


def _nearest(levels, value):
    return min(range(len(levels)), key=lambda i: (abs(value - levels[i]), i))


def sentiment_parts(g, update_hunger=False):
    """Components (docs/logic/sentiment.md). Negative tax/wage/unemployment/food parts count as 0
    until the city has reached 350 people (small-city clip)."""
    c = g.city
    clip = lambda v: 0 if v < 0 and not c.reached_350 else v
    levels = g.rules["tax_levels"]
    i = _nearest([lv["rate"] for lv in levels], c.tax_rate)
    if getattr(c, "tax_coverage", 0) < 11:        # sentiment_taxes 0x00567120: very low coverage uses row 0
        i = 0
    taxes = clip(levels[i]["sentiment"])
    wages = clip([-10, -5, -2, 0, 2, 4][_nearest([0, 20, 26, 30, 34, 40], c.wage_rate)])
    u = c.unemployed * 100 // c.workforce if c.workforce else 0
    unemp = 1 if u < 5 else clip(0 if u < 11 else -1 if u < 18 else -2 if u < 26 else -3)
    total = n = 0
    for b in index.of(g, "house"):
        if b.kind != "house" or not b.occupants:
            continue
        hunger = b.hunger
        if update_hunger:
            hunger = 0 if b.fed else min(3, b.hunger + 1)
            b.hunger = hunger
        total += 2 if hunger == 0 else -hunger
        n += 1
    food = 0
    if n:                                          # 0x00566F20: trunc, then round half away from 0 (strictly >)
        food = int(total / n)
        if abs(total) % n > n // 2:
            food += -1 if total < 0 else 1
        food = clip(food)
    debt = -2 if c.treasury < 0 else 0
    debt += sum(-v for y, v in ((0, 2), (1, 3), (2, 4)) if c.months_in_debt // 12 > y)
    from .. import military                        # 0x00566E70: mobilized companies in peacetime (not clipped)
    return dict(taxes=taxes, wages=wages, unemployment=unemp, food=food, debt=debt, military=military.sentiment(g))


CAUSES = ("food", "unemployment", "taxes", "wages", "debt", "military")   # cause codes 1..6, text 61:39..44


def worst_cause(parts):
    """sentiment_update 0x005671A0: the most negative part, ties to the earlier in CAUSES (strict <); 0 = none."""
    cause, worst = 0, 0
    for i, k in enumerate(CAUSES):
        if parts.get(k, 0) < worst:
            cause, worst = i + 1, parts[k]
    return cause


def sentiment(g):
    """Twice a month: move by the sum of the parts, damped toward the 41..60 band."""
    c = g.city
    if c.population >= 350:
        c.reached_350 = True
    total = sum(sentiment_parts(g, update_hunger=True).values())
    s = c.sentiment
    r = 4 if s < 11 else 3 if s < 21 else 2 if s < 31 else 1 if s < 41 else 0 if s < 61 \
        else -1 if s < 71 else -2 if s < 81 else -3 if s < 91 else -4
    if s < 41 and total < 0:
        total = min(total + r, 0)
    elif s >= 61 and total >= 0:
        total = max(total + r, 0)
    c.sentiment = max(0, min(100, s + total))
