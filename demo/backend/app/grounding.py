"""Match a question to labels, comments, literals, and local names."""

from __future__ import annotations

import re

from rdflib import Literal, URIRef
from rdflib.namespace import OWL, RDF, RDFS

from app.ns import HOUSEHOLD
from app.ranker import Ranker, _words

_CAMEL = re.compile(r"([a-z])([A-Z])")
_MIN_SCORE = 0.45


def _local(iri: URIRef) -> str:
    text = str(iri)
    leaf = text.rsplit("#", 1)[-1] if "#" in text else text.rstrip("/").rsplit("/", 1)[-1]
    return _CAMEL.sub(r"\1 \2", leaf).replace("_", " ")


def _kind(graph, iri: URIRef) -> str:
    types = set(graph.objects(iri, RDF.type))
    if OWL.Class in types or RDFS.Class in types:
        return "class"
    if OWL.ObjectProperty in types or OWL.DatatypeProperty in types:
        return "property"
    if types:
        return "individual"
    return "term"


class Grounder:
    def __init__(self, graph, ranker: Ranker) -> None:
        self.graph = graph
        self.ranker = ranker
        self.entries: list[tuple[str, URIRef, str]] = []
        seen = set()
        df: dict[str, int] = {}
        for iri in set(graph.subjects()) | set(graph.objects()):
            if not isinstance(iri, URIRef):
                continue
            texts = {_local(iri)}
            for pred in (RDFS.label, RDFS.comment):
                for value in graph.objects(iri, pred):
                    if isinstance(value, Literal):
                        texts.add(str(value))
            for pred, value in graph.predicate_objects(iri):
                if isinstance(value, Literal) and pred not in (RDFS.label, RDFS.comment):
                    texts.add(str(value))
            for text in texts:
                key = (text.lower(), str(iri))
                if key in seen or len(text.strip()) < 4:
                    continue
                seen.add(key)
                self.entries.append((text, iri, _kind(graph, iri)))
                for word in set(_words(text)):
                    df[word] = df.get(word, 0) + 1
        self.df = df

    def match(self, question: str) -> dict:
        best: dict[str, dict] = {}
        for text, iri, kind in self.entries:
            score = self.ranker.score(question, text, self.df)
            if score < _MIN_SCORE:
                continue
            current = best.get(str(iri))
            if current is None or score > current["score"]:
                best[str(iri)] = {
                    "phrase": text,
                    "iri": str(iri),
                    "id": _local(iri),
                    "kind": kind,
                    "score": round(score, 3),
                }
        chip = {
            "phrase": "household chip",
            "iri": str(HOUSEHOLD),
            "id": "household_miller",
            "kind": "individual",
            "score": 1.0,
        }
        best[str(HOUSEHOLD)] = chip
        matches = sorted(best.values(), key=lambda row: (-row["score"], row["id"]))
        individuals = [URIRef(row["iri"]) for row in matches if row["kind"] == "individual"]
        classes = {URIRef(row["iri"]) for row in matches if row["kind"] == "class"}
        for row in matches:
            if row["kind"] != "property":
                continue
            prop = URIRef(row["iri"])
            for pred in (RDFS.domain, RDFS.range):
                for node in self.graph.objects(prop, pred):
                    if isinstance(node, URIRef):
                        classes.add(node)
                    else:
                        for item in self.graph.items(node):
                            if isinstance(item, URIRef):
                                classes.add(item)
        for iri in individuals:
            for typ in self.graph.objects(iri, RDF.type):
                if isinstance(typ, URIRef):
                    classes.add(typ)
                    parent = typ
                    while parent is not None:
                        nxt = self.graph.value(parent, RDFS.subClassOf)
                        if isinstance(nxt, URIRef):
                            classes.add(nxt)
                            parent = nxt
                        else:
                            break
        return {
            "ranker": self.ranker.mode,
            "matches": matches,
            "individualIris": [str(iri) for iri in individuals],
            "classIris": [str(iri) for iri in classes],
        }
