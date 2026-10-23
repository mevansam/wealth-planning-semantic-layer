# Self-Directed Investor Wealth Planning — OntologyRAG and GraphRAG Use Case

This example shows how a small wealth-planning ontology and one household graph answer a question that ordinary chunk retrieval cannot answer on its own: which account to draw from, given tax treatment and the goal that account is funding.

It is a technical demonstration of retrieval. It is not tax, legal, or investment advice.

## Artifacts

| File | Role |
| --- | --- |
| `sdi_wealth_schema_fixed.ttl` | TBox. Classes, properties, tax-bucket individuals, and the three data-source tools. |
| `sdi_household_instance.jsonld` | ABox. The merged household graph after the three tool responses are aligned. |

Both files are RDF. Turtle is a schema syntax, and JSON-LD is an instance syntax. Either store can load either file. The split is terminological knowledge versus asserted facts, not "graph database versus vector database."

## What the demonstration has to prove

A self-directed investor asks:

> I need $50,000 for an unexpected expense. Should I take it from the Schwab account or the Vanguard account?

A useful answer has to follow links that do not sit in one sentence:

`Account —hasPrimaryAccountHolder / hasSecondaryAccountHolder→ SelfDirectedAccountHolder —isPlayedBy→ Person`

`Account —hasTaxTreatment→ TaxBucket`

`WealthPlan —includesAccount→ Account —hasHolding→ Holding`

`Account —fundsGoal→ FinancialGoal`

and then apply withdrawal rules that are written down somewhere outside the model weights. Those rules are not implied by the words "Taxable" and "Tax-Free."

The example is built around these domain facts:

1. A household is the filing unit. David Miller is the head and a member. Elena Miller is his spouse and a member. Married filing jointly needs both of them. The plan records a quarterly rebalancing cadence and does not hold accounts.
2. David and Elena are `fwp:SelfDirectedInvestor`s, a subclass of `fibo-fnd-aap-ppl:Person`. Ownership is a FIBO role, not a kind of person. Each investor plays a `fwp:SelfDirectedAccountHolder`, which extends `fibo-fbc-pas-caa:CustomerAccountHolder`. David is the primary holder of all three accounts. Elena is the secondary holder of the joint Schwab brokerage. An IRA still has one owner.
3. Account registration and tax treatment are different facts. Registration is `fwp:accountCategory` (joint taxable brokerage, Roth IRA, traditional IRA). Tax treatment is `fwp:hasTaxTreatment` to `fwp:Taxable`, `fwp:TaxDeferred`, or `fwp:TaxFree`.
4. A holding sits inside one account. The taxable equity lot carries cost basis and an acquisition date. Roth contribution basis sits on the Roth account. The traditional IRA's nondeductible basis is zero, so a withdrawal is pre-tax. Bonds are in the tax-deferred account. Equities are in the taxable account and the Roth.
5. `fwp:fundsGoal` assigns the whole current balance of an account to one goal. The taxable account funds the bridge. The Roth funds later tax-free growth. The traditional IRA funds income after David reaches 59.5. Holdings do not also use `fwp:fundsGoal`.

## OntologyRAG and GraphRAG in this example

The two names describe two indexes over the same facts.

**Graph retrieval (GraphRAG, local).** Load the merged ABox into a graph store. Answer structural questions by walking properties the TBox declares. For the question above, the walk returns the Schwab taxable account, the Vanguard Roth, the Fidelity traditional IRA, each tax bucket, each holder role, each holding, each funded goal, and the balances. This is neighborhood retrieval on an RDF graph. It is not Microsoft GraphRAG's corpus-wide community summaries. Those summaries are a separate pattern and are not part of this example.

**Ontology-guided retrieval (OntologyRAG).** The TBox tells the pipeline what a valid neighborhood is, which words map to which properties, and which inferences are already licensed.

- At ingestion, build one retrieval unit per account neighborhood: the account, its owner, its tax bucket, its holding, the goal it funds, and its balance. A generic token splitter will still cut a JSON object in half. Object boundaries have to be chosen from the schema.
- At query time, ground phrases onto the ontology before searching. "Schwab" grounds to the institution of an account. "Pull money" grounds to a withdrawal over accounts that have a tax treatment and a funded goal. Search is then limited to those properties.
- `fwp:hasHeadOfHousehold` is an `rdfs:subPropertyOf` `fwp:hasMember`. A member query therefore returns the head once a reasoner, or a query that follows subproperties, is in the path. That inference is a concrete OntologyRAG result.
- Put the retrieved subgraph, plus any retrieved policy passages, into the prompt. The model explains those inputs. It does not become deterministic because the chunk contains a prefix.

**Vector retrieval.** Embed the same account neighborhoods, and embed policy passages if a policy corpus is added. Use it to find the neighborhood when the question does not name the account, and to find prose rules (capital-gains treatment, Roth ordering) that are not edges in the household graph.

The graph store holds the TBox, the tax-bucket individuals, the three tool individuals, and the merged household ABox. The vector store holds text projections of ABox neighborhoods and, later, policy documents. Class and property labels may also be embedded so query grounding can match user wording to the vocabulary. The schema is not the only thing in the graph, and the instance is not only a vector document.

```text
Question, already scoped to fwp:household_miller
  ├─ ground terms with the TBox (account, tax bucket, goal, person)
  ├─ ^providesInstancesOf from each grounded class to its DataSourceTool and endpointPath
  ├─ call those tools, align each payload, and resolve cross-tool IRIs
  ├─ graph walk on the merged ABox
  └─ vector search over account neighborhoods and policy text
        └─ prompt = question + subgraph + policy passages
              └─ answer cites the accounts, buckets, goals, and rules it was given
```

### Data source tools

`fwp:DataSourceTool` records which endpoint returns which schema classes. Retrieval follows `^fwp:providesInstancesOf` from each grounded class to that tool. CustomerProfile returns the household and the investors. WealthPlanning returns the plan and the goals. AccountData returns the accounts, holdings, holder roles, and `fwp:fundsGoal`. The endpoints are example paths with no household parameter. This demo is already scoped to `fwp:household_miller`.

Load `sdi_wealth_schema_fixed.ttl` for the TBox, the tax-bucket individuals, and the tool catalog. `sdi_household_instance.jsonld` is the merged household graph after those three responses are aligned. Endpoints, class bindings, and the punning and inverse rules are in [SPEC.md](SPEC.md#data-source-tools).

## Data contract

Classes, diagrams, property tables, household facts, and what the $50,000 question is allowed to conclude are in [SPEC.md](SPEC.md).

## Implementation

The demo application specification is [demo/README.md](demo/README.md). It describes the retrieval loop, the tool queries over the household JSON-LD, and the trace UI. Application code is not written yet.
