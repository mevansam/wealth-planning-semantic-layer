import os

os.environ["RANKER"] = "lexical"

from rdflib import URIRef

from app.calculator import compute
from app.loop import Engine
from app.ns import BRIDGE, DAVID, FIDELITY, FWP, SCHWAB, VANGUARD
from app.store import Store
from app.tools import project
from app.walk import expand, neighborhood

WITHDRAWAL = [
    "I need $50,000 for an unexpected expense. Should I take it from the Schwab account or the Vanguard account?",
    "Where should I pull fifty thousand dollars, Charles Schwab or the Roth at Vanguard?",
    "If I have to raise 50000 in cash, which is the better source, the joint brokerage or the Vanguard IRA?",
]


def _subjects(payload):
    return set(payload["subjects"])


def test_tool_partitions_keep_cross_links_as_iris():
    store = Store()
    profile = project(store.graph, FWP.CustomerProfileTool, store.source_file)
    planning = project(store.graph, FWP.WealthPlanningTool, store.source_file)
    accounts = project(store.graph, FWP.AccountDataTool, store.source_file)
    assert "household_miller" in profile["subjects"]
    assert "person_david_miller" in profile["subjects"]
    assert "account_taxable_brokerage" not in profile["subjects"]
    assert any(item["predicate"] == "hasWealthPlan" for item in profile["unresolved"])
    assert "plan_miller_core" in planning["subjects"]
    assert "goal_early_retirement" in planning["subjects"]
    assert "account_taxable_brokerage" not in planning["subjects"]
    assert "holding_schwab_equity" in accounts["subjects"]
    assert "Taxable" in accounts["subjects"]
    assert accounts["subjectSources"]["Taxable"] == "sdi_wealth_schema_fixed.ttl"
    assert "goal_early_retirement" not in accounts["subjects"]
    assert any(item["predicate"] == "fundsGoal" for item in accounts["unresolved"])
    assert any(item["predicate"] == "isPlayedBy" for item in accounts["unresolved"])


def test_withdrawal_seeds_exclude_fidelity_description():
    engine = Engine()
    seed_sets = []
    for question in WITHDRAWAL:
        events = {event["id"]: event for event in engine.run(question)}
        seeds = set(events["ground"]["payload"]["individualIris"])
        seed_sets.append(seeds)
        assert str(SCHWAB) in seeds
        assert str(VANGUARD) in seeds
        described = {
            row["subjectIri"]
            for row in events["walk"]["payload"]["triples"]
            if row["predicate"] in {"balance", "institutionName", "holdingName"}
        }
        assert str(FIDELITY) not in described
        formulas = {row["formula"] for row in events["calculator"]["payload"]["outputs"]}
        assert "traditional-pretax" not in formulas
        assert all("penalty" not in formula for formula in formulas)
    shared = set.intersection(*seed_sets)
    assert str(SCHWAB) in shared and str(VANGUARD) in shared


def test_member_path_returns_david():
    engine = Engine()
    events = {event["id"]: event for event in engine.run("Is the head of household also a member?")}
    members = {row["memberIri"] for row in events["inference"]["payload"]["results"]}
    assert str(DAVID) in members
    assert any(row["property"] == "hasHeadOfHousehold" for row in events["inference"]["payload"]["results"])


def test_calculator_matches_the_contract():
    engine = Engine()
    events = {event["id"]: event for event in engine.run(WITHDRAWAL[0])}
    outputs = {row["formula"]: row for row in events["calculator"]["payload"]["outputs"]}
    lot = outputs["taxable-lot"]
    assert lot["gainRatio"] == "0.40"
    assert lot["gain"] == "20000.00"
    assert lot["tax"] == "3760.00"
    assert lot["net"] == "46240.00"
    assert lot["proceedsToNetAmount"] == "54065.74"
    assert outputs["roth-earnings"]["earnings"] == "300000.00"
    shortfalls = [row for row in events["calculator"]["payload"]["outputs"] if row["formula"] == "shortfall"]
    assert any(row["shortfall"] == "300000.00" and row["subjectIri"] == str(BRIDGE) for row in shortfalls)
    ages = [row for row in events["calculator"]["payload"]["outputs"] if row["formula"] == "age"]
    david = next(row for row in ages if row["subjectIri"] == str(DAVID))
    assert david["age"] == 47
    assert david["age59Half"] == "2038-12-15"
    assert outputs["holding-period"]["longTerm"] is True
    bare = compute([], "How much is the 10 percent penalty?")
    assert bare["outputs"] == []


def test_unknown_property_expansion_is_dropped():
    store = Store()
    walked = neighborhood(store.graph, [SCHWAB])
    result = expand(store.graph, set(walked["nodes"]), str(SCHWAB), str(FWP.notAProperty))
    assert result["accepted"] is False
    assert result["triples"] == []
