from rdflib import Namespace

FWP = Namespace("http://example.org/ontology/fwp#")
FIBO_PPL = Namespace("https://spec.edmcouncil.org/fibo/ontology/FND/AgentsAndPeople/People/")
FIBO_CAA = Namespace("https://spec.edmcouncil.org/fibo/ontology/FBC/ProductsAndServices/ClientsAndAccounts/")
CMNS = Namespace("https://www.omg.org/spec/Commons/RolesAndCompositions/")

HOUSEHOLD = FWP.household_miller
SCHWAB = FWP.account_taxable_brokerage
VANGUARD = FWP.account_roth_ira
FIDELITY = FWP.account_traditional_ira
BRIDGE = FWP.goal_early_retirement
DAVID = FWP.person_david_miller
ELENA = FWP.person_elena_miller
