"""Formulas that run only when every operand is already in the neighborhood."""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from app.ns import FWP

_MONEY = re.compile(r"\$?\s*([0-9]{1,3}(?:,[0-9]{3})+|[0-9]+(?:\.[0-9]+)?)")
_CENTS = Decimal("0.01")
_RATIO = Decimal("0.01")


def _q(value: Decimal, places: Decimal = _CENTS) -> str:
    return str(value.quantize(places, rounding=ROUND_HALF_UP))


def _dec(text: str) -> Decimal:
    return Decimal(text.replace(",", ""))


def parse_amount(question: str) -> Decimal | None:
    if re.search(r"fifty\s+thousand", question, re.I):
        return Decimal("50000")
    for match in _MONEY.finditer(question):
        raw = match.group(0)
        number = match.group(1)
        digits = number.replace(".", "")
        if "$" in raw or "," in number or len(digits) >= 4:
            return _dec(number)
    return None


def _by_pred(triples: list[dict]) -> dict[str, dict[str, str]]:
    table: dict[str, dict[str, str]] = {}
    for row in triples:
        if not row.get("literal"):
            continue
        table.setdefault(row["subjectIri"], {})[row["predicate"]] = row["object"]
    return table


def _links(triples: list[dict], predicate: str) -> list[tuple[str, str]]:
    return [
        (row["subjectIri"], row["objectIri"])
        for row in triples
        if row["predicate"] == predicate and row.get("objectIri")
    ]


def _date(text: str) -> date:
    year, month, day = (int(part) for part in text[:10].split("-"))
    return date(year, month, day)


def compute(triples: list[dict], question: str) -> dict:
    values = _by_pred(triples)
    amount = parse_amount(question)
    outputs = []
    inputs = []

    def has(iri: str, *names: str) -> bool:
        return iri in values and all(name in values[iri] for name in names)

    household = str(FWP.household_miller)
    as_of = values.get(household, {}).get("asOfDate")
    ordinary = values.get(household, {}).get("marginalOrdinaryRate")
    ltcg = values.get(household, {}).get("longTermCapitalGainsRate")
    niit = values.get(household, {}).get("netInvestmentIncomeTaxRate")

    if amount is not None and ltcg and niit:
        for holding, props in values.items():
            if "costBasis" not in props or "marketValue" not in props:
                continue
            market = _dec(props["marketValue"])
            basis = _dec(props["costBasis"])
            ratio = (market - basis) / market
            gain = amount * ratio
            rate = _dec(ltcg) + _dec(niit)
            tax = gain * rate
            net = amount - tax
            proceeds = amount / (Decimal("1") - ratio * rate)
            inputs.append({"costBasis": str(basis), "marketValue": str(market), "amount": str(amount), "longTermCapitalGainsRate": ltcg, "netInvestmentIncomeTaxRate": niit})
            outputs.append({
                "formula": "taxable-lot",
                "subjectIri": holding,
                "gainRatio": _q(ratio, _RATIO),
                "gain": _q(gain),
                "tax": _q(tax),
                "net": _q(net),
                "proceedsToNetAmount": _q(proceeds),
            })

    for account, goal in _links(triples, "fundsGoal"):
        if has(account, "balance") and has(goal, "targetAmount"):
            balance = _dec(values[account]["balance"])
            target = _dec(values[goal]["targetAmount"])
            inputs.append({"balance": str(balance), "targetAmount": str(target)})
            outputs.append({
                "formula": "shortfall",
                "subjectIri": goal,
                "accountIri": account,
                "goalName": values[goal].get("goalName", ""),
                "shortfall": _q(target - balance),
            })

    for iri, props in values.items():
        if "rothContributionBasis" in props and "balance" in props:
            balance = _dec(props["balance"])
            basis = _dec(props["rothContributionBasis"])
            inputs.append({"balance": str(balance), "rothContributionBasis": str(basis)})
            outputs.append({"formula": "roth-earnings", "subjectIri": iri, "earnings": _q(balance - basis)})
        if props.get("iraNondeductibleBasis") == "0.00" or props.get("iraNondeductibleBasis") == "0":
            if amount is not None and ordinary:
                tax = amount * _dec(ordinary)
                inputs.append({"iraNondeductibleBasis": props["iraNondeductibleBasis"], "marginalOrdinaryRate": ordinary, "amount": str(amount)})
                outputs.append({"formula": "traditional-pretax", "subjectIri": iri, "tax": _q(tax)})

    if as_of:
        for iri, props in values.items():
            if "dateOfBirth" not in props:
                continue
            born = _date(props["dateOfBirth"])
            today = _date(as_of)
            age = today.year - born.year - ((today.month, today.day) < (born.month, born.day))
            half = date(born.year + 59, born.month, born.day)
            month = half.month + 6
            year = half.year + (month - 1) // 12
            month = (month - 1) % 12 + 1
            inputs.append({"dateOfBirth": props["dateOfBirth"], "asOfDate": as_of})
            outputs.append({
                "formula": "age",
                "subjectIri": iri,
                "name": props.get("hasPersonName", ""),
                "age": age,
                "age59Half": date(year, month, half.day).isoformat(),
            })
        for iri, props in values.items():
            if "acquiredOn" not in props:
                continue
            acquired = _date(props["acquiredOn"])
            today = _date(as_of)
            long_term = (today - acquired).days > 365
            inputs.append({"acquiredOn": props["acquiredOn"], "asOfDate": as_of})
            outputs.append({
                "formula": "holding-period",
                "subjectIri": iri,
                "longTerm": long_term,
                "passageId": "holding-period",
            })

    return {"amount": str(amount) if amount is not None else None, "inputs": inputs, "outputs": outputs}
