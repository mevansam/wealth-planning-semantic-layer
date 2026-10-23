"""Project each data-source tool to the classes it provides."""

from rdflib import Literal, URIRef
from rdflib.namespace import OWL, RDF, RDFS

from app.ns import FWP

TOOL_ORDER = (
    FWP.CustomerProfileTool,
    FWP.WealthPlanningTool,
    FWP.AccountDataTool,
)


def _short(iri) -> str:
    text = str(iri)
    if "#" in text:
        return text.rsplit("#", 1)[-1]
    return text.rstrip("/").rsplit("/", 1)[-1]


def _classes_for(graph, tool: URIRef) -> set[URIRef]:
    roots = set(graph.objects(tool, FWP.providesInstancesOf))
    found = set(roots)
    changed = True
    while changed:
        changed = False
        for cls in list(graph.subjects(RDFS.subClassOf, None)):
            parent = graph.value(cls, RDFS.subClassOf)
            if parent in found and cls not in found:
                found.add(cls)
                changed = True
    return found


def _individuals(graph, classes: set[URIRef]) -> set[URIRef]:
    people = set()
    for iri in graph.subjects(RDF.type, None):
        if not isinstance(iri, URIRef):
            continue
        types = set(graph.objects(iri, RDF.type))
        if types & classes:
            people.add(iri)
    return people


def _term(node) -> dict:
    if isinstance(node, Literal):
        return {"value": str(node), "datatype": _short(node.datatype) if node.datatype else None}
    return {"iri": str(node), "id": _short(node)}


def project(graph, tool: URIRef, source_for) -> dict:
    classes = _classes_for(graph, tool)
    included = _individuals(graph, classes)
    triples = []
    unresolved = []
    for subject in sorted(included, key=str):
        for pred, obj in graph.predicate_objects(subject):
            if pred == RDF.type and obj not in classes and obj not in included:
                # Keep the asserted type even when it is a superclass outside the binding.
                pass
            row = {
                "subject": _short(subject),
                "subjectIri": str(subject),
                "predicate": _short(pred),
                "predicateIri": str(pred),
                "object": _term(obj),
            }
            triples.append(row)
            if isinstance(obj, URIRef) and obj not in included and pred != RDF.type:
                unresolved.append({"subject": _short(subject), "predicate": _short(pred), "object": _short(obj), "objectIri": str(obj)})
    endpoint = graph.value(tool, FWP.endpointPath)
    name = str(graph.value(tool, FWP.toolName))
    sources = sorted({source_for(iri) for iri in included})
    subject_sources = {_short(iri): source_for(iri) for iri in included}
    return {
        "tool": name,
        "endpoint": str(endpoint) if endpoint else "",
        "classes": sorted(_short(c) for c in classes),
        "subjects": sorted(_short(s) for s in included),
        "subjectIris": sorted(str(s) for s in included),
        "sourceFiles": sources,
        "subjectSources": subject_sources,
        "triples": triples,
        "unresolved": unresolved,
    }


def select_tools(graph, class_iris: set[URIRef]) -> list[dict]:
    chosen = []
    for tool in TOOL_ORDER:
        provided = set(graph.objects(tool, FWP.providesInstancesOf))
        hit = sorted(_short(c) for c in class_iris if c in provided)
        if not hit:
            continue
        chosen.append({
            "tool": str(graph.value(tool, FWP.toolName)),
            "toolIri": str(tool),
            "endpoint": str(graph.value(tool, FWP.endpointPath)),
            "classes": hit,
        })
    return chosen


def object_property(graph, prop: URIRef) -> bool:
    if (prop, RDF.type, OWL.ObjectProperty) in graph:
        return True
    for _s, _p, o in graph.triples((None, prop, None)):
        if isinstance(o, URIRef):
            return True
    return False
