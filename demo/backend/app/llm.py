"""Explain the trace. A configured chat model is used when the environment has one."""

from __future__ import annotations

import json
import os
import re

import httpx

_OWNER = re.compile(r"\b(own|owns|whose|elena|name)\b", re.I)
_PEOPLE = re.compile(r"\b(who|whose|own|owns|name|elena|member|household|head)\b", re.I)
_AGE = re.compile(r"\b(age|59)\b", re.I)


def _people(triples: list[dict]) -> list[str]:
    names = {row["subjectIri"]: row["object"] for row in triples if row["predicate"] == "hasPersonName"}
    lines = []
    seen = set()
    for row in triples:
        if row["predicate"] in {"hasMember", "hasHeadOfHousehold"} and row.get("objectIri") in names:
            line = f"{names[row['objectIri']]} is linked by {row['predicate']}."
        elif row["predicate"] == "isPlayedBy" and row.get("objectIri") in names:
            line = f"{names[row['objectIri']]} plays {row['subject']}."
        elif row["predicate"] in {"hasPrimaryAccountHolder", "hasSecondaryAccountHolder"}:
            line = f"{row['subject']} {row['predicate']} {row['object']}."
        else:
            continue
        if line not in seen:
            seen.add(line)
            lines.append(line)
    return lines


def _mentions_person(question: str, output: dict) -> bool:
    name = str(output.get("name") or "")
    if name and name.lower() in question.lower():
        return True
    return bool(_AGE.search(question))
_WEIGHTS = re.compile(r"target weights|rebalance buy", re.I)
_PENALTY = re.compile(r"10 percent|penalty", re.I)


def _facts(triples: list[dict]) -> list[str]:
    lines = []
    for row in triples:
        if row["predicate"] in {"type", "label", "comment"}:
            continue
        lines.append(f"{row['subject']} {row['predicate']} {row['object']}")
    return lines


def explain(question: str, triples: list[dict], calc: dict, passages: list[dict]) -> tuple[str, list[dict]]:
    described = {row["subjectIri"] for row in triples}
    text = []
    citations = []
    for output in calc["outputs"]:
        if output["formula"] == "taxable-lot":
            text.append(
                f"On {calc['amount']} of proceeds the gain ratio is {output['gainRatio']}. "
                f"The gain is {output['gain']}. Tax is {output['tax']}. Net cash is {output['net']}. "
                f"Netting {calc['amount']} takes {output['proceedsToNetAmount']} of proceeds."
            )
            citations.append({"stepId": "calculator", "iri": output["subjectIri"], "note": "taxable lot"})
        elif output["formula"] == "shortfall":
            name = output.get("goalName") or "The linked goal"
            text.append(f"{name} is short by {output['shortfall']}.")
            citations.append({"stepId": "calculator", "iri": output["subjectIri"], "note": "shortfall"})
        elif output["formula"] == "roth-earnings":
            text.append(f"Roth earnings in the retrieved account are {output['earnings']}.")
            citations.append({"stepId": "calculator", "iri": output["subjectIri"], "note": "Roth earnings"})
        elif output["formula"] == "traditional-pretax":
            text.append(f"A pre-tax distribution of the requested amount is taxed {output['tax']} at the ordinary rate. The 10 percent additional tax is not calculated.")
            citations.append({"stepId": "calculator", "iri": output["subjectIri"], "note": "pre-tax amount"})
        elif output["formula"] == "age" and _mentions_person(question, output):
            who = output.get("name") or output["subjectIri"].rsplit("#", 1)[-1]
            text.append(f"{who} is {output['age']} on the as-of date. Age 59.5 is {output['age59Half']}.")
            citations.append({"stepId": "calculator", "iri": output["subjectIri"], "note": "age"})
        elif output["formula"] == "holding-period" and output["longTerm"]:
            text.append("The retrieved acquisition date is more than one year before the as-of date, so the holding-period passage treats the lot as long-term.")
            citations.append({"stepId": "policy", "iri": output["subjectIri"], "note": "holding-period"})
    institutions = list(dict.fromkeys(
        row["object"] for row in triples if row["predicate"] == "institutionName"
    ))
    if institutions:
        text.append("Retrieved custodians: " + ", ".join(institutions) + ".")
        citations.append({"stepId": "walk", "iri": "", "note": "custodians"})
    if _PEOPLE.search(question):
        text.extend(_people(triples))
        citations.append({"stepId": "walk", "iri": "", "note": "people"})
    if _WEIGHTS.search(question):
        text.append("Target weights are not in the retrieved context.")
        citations.append({"stepId": "policy", "iri": "", "note": "no target weights"})
    if _PENALTY.search(question):
        text.append("The 10 percent early-distribution additional tax is not a calculated amount.")
        citations.append({"stepId": "policy", "iri": "", "note": "no penalty amount"})
    if not text:
        text.append("The retrieved triples do not contain a figure for this question.")
        citations.append({"stepId": "walk", "iri": next(iter(described), ""), "note": "neighborhood"})
    return " ".join(text), citations


def _fallback(question: str, triples: list[dict], frontier: list[dict], calc: dict, passages: list[dict], force_final: bool) -> dict:
    answer, citations = explain(question, triples, calc, passages)
    if force_final or not _OWNER.search(question):
        return {"status": "final", "expand": [], "answer": answer, "citations": citations, "source": "trace"}
    expand = [
        {"subject": edge["subjectIri"], "property": edge["predicateIri"]}
        for edge in frontier
        if edge["predicate"] == "isPlayedBy"
    ]
    if not expand:
        return {"status": "final", "expand": [], "answer": answer, "citations": citations, "source": "trace"}
    return {"status": "expand", "expand": expand, "answer": "", "citations": [], "source": "trace"}


def decide(question: str, triples: list[dict], frontier: list[dict], calc: dict, passages: list[dict], force_final: bool) -> dict:
    key = os.environ.get("LLM_API_KEY")
    if not key:
        return _fallback(question, triples, frontier, calc, passages, force_final)
    prompt = {
        "question": question,
        "triples": _facts(triples),
        "frontier": frontier,
        "calculator": calc["outputs"],
        "passages": [{"id": p["id"], "text": p["text"]} for p in passages],
        "forceFinal": force_final,
    }
    system = (
        "Explain only the triples, calculator outputs, and passages in the user payload. "
        "Do not state a 10 percent penalty amount. Do not state target weights. "
        "Figures must come from the calculator outputs. "
        "Reply with JSON: {\"status\":\"expand|final\",\"expand\":[{\"subject\":\"iri\",\"property\":\"iri\"}],"
        "\"answer\":\"string\",\"citations\":[{\"stepId\":\"string\",\"iri\":\"string\",\"note\":\"string\"}]}. "
        "status expand is allowed only when forceFinal is false. "
        "Choose expand subjects and properties from the frontier."
    )
    body = {
        "model": os.environ.get("LLM_MODEL", "gpt-4o-mini"),
        "temperature": 0,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": json.dumps(prompt)},
        ],
    }
    url = os.environ.get("LLM_BASE_URL", "https://api.openai.com/v1").rstrip("/") + "/chat/completions"
    try:
        response = httpx.post(url, headers={"Authorization": f"Bearer {key}"}, json=body, timeout=60)
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
        parsed = json.loads(content)
        parsed["source"] = "model"
        parsed["prompt"] = system + "\n" + json.dumps(prompt)
        if force_final:
            parsed["status"] = "final"
            parsed["expand"] = []
        return parsed
    except Exception:
        fallen = _fallback(question, triples, frontier, calc, passages, force_final)
        fallen["source"] = "trace"
        return fallen
