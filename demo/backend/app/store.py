"""Load the Turtle TBox and the JSON-LD household into one graph."""

from pathlib import Path

from rdflib import Graph

ROOT = Path(__file__).resolve().parents[3]
SCHEMA_PATH = ROOT / "sdi_wealth_schema_fixed.ttl"
HOUSEHOLD_PATH = ROOT / "sdi_household_instance.jsonld"


class Store:
    def __init__(self) -> None:
        self.schema = Graph()
        self.schema.parse(SCHEMA_PATH, format="turtle")
        self.household = Graph()
        self.household.parse(HOUSEHOLD_PATH, format="json-ld")
        self.graph = Graph()
        self.graph += self.schema
        self.graph += self.household

    def source_file(self, iri) -> str:
        if any(True for _ in self.household.triples((iri, None, None))):
            return HOUSEHOLD_PATH.name
        return SCHEMA_PATH.name
