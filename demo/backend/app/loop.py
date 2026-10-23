"""One loop for every question. The graph selects the tools and the neighborhood."""

from rdflib import URIRef

from app.calculator import compute
from app.grounding import Grounder
from app.llm import decide
from app.ns import HOUSEHOLD
from app.policy import search
from app.ranker import Ranker
from app.store import Store
from app.tools import project, select_tools
from app.walk import expand, neighborhood, subproperty_members


class Engine:
    def __init__(self, store: Store | None = None) -> None:
        self.store = store or Store()
        self.ranker = Ranker()
        self.grounder = Grounder(self.store.graph, self.ranker)
        from app.policy import load_passages

        self.passages = load_passages()

    def run(self, question: str) -> list[dict]:
        events = []
        grounded = self.grounder.match(question)
        events.append({"id": "ground", "type": "ground", "payload": grounded})
        classes = {URIRef(iri) for iri in grounded["classIris"]}
        tools = select_tools(self.store.graph, classes)
        events.append({"id": "tools", "type": "tools", "payload": {"tools": tools}})
        payloads = []
        for tool in tools:
            payload = project(self.store.graph, URIRef(tool["toolIri"]), self.store.source_file)
            payloads.append(payload)
            events.append({"id": f"tool-{tool['tool']}", "type": "tool_result", "payload": payload})
        events.append({"id": "merge", "type": "merge", "payload": _merge(payloads)})
        seeds = [URIRef(iri) for iri in grounded["individualIris"]]
        walked = neighborhood(self.store.graph, seeds)
        events.append({"id": "walk", "type": "walk", "payload": {"triples": walked["triples"], "frontier": walked["frontier"]}})
        if HOUSEHOLD in seeds:
            events.append({
                "id": "inference",
                "type": "inference",
                "payload": subproperty_members(self.store.graph, HOUSEHOLD),
            })
        found = search(self.ranker, question, self.passages)
        events.append({"id": "policy", "type": "policy", "payload": found})
        calc = compute(walked["triples"], question)
        events.append({"id": "calculator", "type": "calculator", "payload": calc})
        nodes = set(walked["nodes"])
        first = decide(question, walked["triples"], walked["frontier"], calc, found["passages"], False)
        events.append({"id": "model-1", "type": "model", "payload": {"call": 1, "response": first, "prompt": first.get("prompt", "")}})
        final = first
        if first.get("status") == "expand" and first.get("expand"):
            results = []
            added = []
            for pair in first["expand"]:
                result = expand(self.store.graph, nodes, pair.get("subject", ""), pair.get("property", ""))
                results.append(result)
                added.extend(result["triples"])
            events.append({"id": "expand", "type": "expand", "payload": {"results": results}})
            walked["triples"].extend(added)
            calc = compute(walked["triples"], question)
            second = decide(question, walked["triples"], walked["frontier"], calc, found["passages"], True)
            events.append({"id": "model-2", "type": "model", "payload": {"call": 2, "response": second, "prompt": second.get("prompt", "")}})
            final = second
        events.append({
            "id": "final",
            "type": "final",
            "payload": {"answer": final.get("answer", ""), "citations": final.get("citations", [])},
        })
        return events


def _merge(payloads: list[dict]) -> dict:
    defined: dict[str, str] = {}
    for payload in payloads:
        for iri in payload["subjectIris"]:
            defined.setdefault(iri, payload["tool"])
    links = []
    seen = set()
    for payload in payloads:
        for item in payload["unresolved"]:
            owner = defined.get(item["objectIri"])
            if not owner or owner == payload["tool"]:
                continue
            key = (item["objectIri"], payload["tool"])
            if key in seen:
                continue
            seen.add(key)
            links.append({
                "iri": item["objectIri"],
                "id": item["object"],
                "referencedBy": payload["tool"],
                "definedBy": owner,
            })
    return {"links": links}
