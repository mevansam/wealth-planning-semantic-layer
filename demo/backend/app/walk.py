"""Neighborhood of the grounded individuals. One hop, literals on the neighbor."""

from rdflib import Literal, URIRef
from rdflib.namespace import RDF

from app.tools import _short

_SKIP = {RDF.type}


def _show(node) -> str:
    if isinstance(node, Literal):
        return str(node)
    return _short(node)


def neighborhood(graph, seeds: list[URIRef]) -> dict:
    seed_set = set(seeds)
    triples = []
    nodes = set(seed_set)

    def add(subject, pred, obj, described: bool) -> None:
        triples.append({
            "subject": _short(subject),
            "subjectIri": str(subject),
            "predicate": _short(pred),
            "predicateIri": str(pred),
            "object": _show(obj),
            "objectIri": str(obj) if isinstance(obj, URIRef) else None,
            "literal": isinstance(obj, Literal),
            "described": described,
        })

    for seed in seeds:
        for pred, obj in graph.predicate_objects(seed):
            if pred in _SKIP:
                continue
            if isinstance(obj, Literal):
                add(seed, pred, obj, True)
                continue
            if not isinstance(obj, URIRef) or obj == seed:
                continue
            add(seed, pred, obj, True)
            nodes.add(obj)
            _literals(graph, obj, add, nodes)
        for subject, pred in graph.subject_predicates(seed):
            if pred in _SKIP or not isinstance(subject, URIRef) or subject == seed:
                continue
            add(subject, pred, seed, True)
            nodes.add(subject)
            _literals(graph, subject, add, nodes)

    frontier = []
    seen = set()
    for node in sorted(nodes - seed_set, key=str):
        for pred, obj in graph.predicate_objects(node):
            if not isinstance(obj, URIRef) or pred in _SKIP:
                continue
            key = (str(node), str(pred), str(obj))
            if key in seen:
                continue
            if any(row["subjectIri"] == str(node) and row["predicateIri"] == str(pred) and row["objectIri"] == str(obj) for row in triples):
                continue
            seen.add(key)
            frontier.append({
                "subject": _short(node),
                "subjectIri": str(node),
                "predicate": _short(pred),
                "predicateIri": str(pred),
                "object": _short(obj),
                "objectIri": str(obj),
            })
    return {"triples": triples, "frontier": frontier, "nodes": sorted(str(n) for n in nodes)}


def _literals(graph, node: URIRef, add, nodes) -> None:
    nodes.add(node)
    for pred, obj in graph.predicate_objects(node):
        if isinstance(obj, Literal):
            add(node, pred, obj, True)
        elif pred == RDF.type and isinstance(obj, URIRef):
            add(node, pred, obj, True)


def subproperty_members(graph, household: URIRef) -> dict:
    query = """
    PREFIX fwp: <http://example.org/ontology/fwp#>
    PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
    SELECT ?property ?member WHERE {
      ?property rdfs:subPropertyOf* fwp:hasMember .
      ?household ?property ?member .
    }
    """
    rows = []
    for prop, member in graph.query(query, initBindings={"household": household}):
        rows.append({"property": _short(prop), "member": _short(member), "memberIri": str(member)})
    return {
        "query": "household hasMember, following rdfs:subPropertyOf*",
        "results": rows,
    }


def expand(graph, nodes: set[str], subject: str, prop: str) -> dict:
    from app.tools import object_property

    subject_ref = URIRef(subject)
    prop_ref = URIRef(prop)
    if subject not in nodes:
        return {"accepted": False, "reason": "subject is not in the neighborhood", "triples": []}
    if not object_property(graph, prop_ref):
        return {"accepted": False, "reason": "property is not in the graph", "triples": []}
    triples = []
    for obj in graph.objects(subject_ref, prop_ref):
        triples.append({
            "subject": _short(subject_ref),
            "subjectIri": subject,
            "predicate": _short(prop_ref),
            "predicateIri": prop,
            "object": _show(obj),
            "objectIri": str(obj) if isinstance(obj, URIRef) else None,
            "literal": isinstance(obj, Literal),
            "described": True,
        })
        if isinstance(obj, URIRef):
            nodes.add(str(obj))
            for pred, lit in graph.predicate_objects(obj):
                if isinstance(lit, Literal) or pred == RDF.type:
                    triples.append({
                        "subject": _short(obj),
                        "subjectIri": str(obj),
                        "predicate": _short(pred),
                        "predicateIri": str(pred),
                        "object": _show(lit),
                        "objectIri": str(lit) if isinstance(lit, URIRef) else None,
                        "literal": isinstance(lit, Literal),
                        "described": True,
                    })
    return {"accepted": True, "reason": "expanded", "triples": triples, "subject": _short(subject_ref), "predicate": _short(prop_ref)}
