import { useState } from "react";
import { PHRASINGS } from "./questions";

type TraceEvent = {
  id: string;
  type: string;
  payload: Record<string, unknown>;
};

type Citation = { stepId: string; iri: string; note: string };

export function App() {
  const [question, setQuestion] = useState(PHRASINGS[0]);
  const [open, setOpen] = useState(false);
  const [events, setEvents] = useState<TraceEvent[]>([]);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState("");

  async function run() {
    setRunning(true);
    setError("");
    setEvents([]);
    try {
      const response = await fetch("/api/ask", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question }),
      });
      if (!response.ok || !response.body) {
        throw new Error(`Request failed (${response.status})`);
      }
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      for (;;) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const chunks = buffer.split("\n\n");
        buffer = chunks.pop() ?? "";
        for (const chunk of chunks) {
          const line = chunk.split("\n").find((item) => item.startsWith("data: "));
          if (!line) continue;
          const event = JSON.parse(line.slice(6)) as TraceEvent;
          setEvents((current) => [...current, event]);
        }
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "The trace stopped.");
    } finally {
      setRunning(false);
    }
  }

  const finalEvent = [...events].reverse().find((event) => event.type === "final");
  const answer = String(finalEvent?.payload.answer ?? "");
  const citations = (finalEvent?.payload.citations as Citation[] | undefined) ?? [];

  return (
    <div className="page">
      <header>
        <p className="eyebrow">Retrieval demonstration</p>
        <h1>Which account should fund this withdrawal?</h1>
        <p className="notice">This is a retrieval demonstration. It is not tax, legal, or investment advice.</p>
      </header>
      <section className="ask">
        <div className="picker">
          <span id="question-label">Question</span>
          <button
            type="button"
            className="picker-value"
            aria-expanded={open}
            aria-controls="question-menu"
            onClick={() => setOpen((current) => !current)}
          >
            {question}
          </button>
          {open ? (
            <ul id="question-menu" className="picker-menu" role="listbox" aria-labelledby="question-label">
              {PHRASINGS.map((phrasing) => (
                <li key={phrasing}>
                  <button
                    type="button"
                    role="option"
                    aria-selected={phrasing === question}
                    onClick={() => {
                      setQuestion(phrasing);
                      setOpen(false);
                    }}
                  >
                    {phrasing}
                  </button>
                </li>
              ))}
            </ul>
          ) : null}
        </div>
        <div className="row">
          <span className="chip">fwp:household_miller</span>
          <button type="button" onClick={run} disabled={running}>
            {running ? "Running" : "Run"}
          </button>
        </div>
      </section>
      {error ? <p className="error">{error}</p> : null}
      <ol className="timeline">
        {events.filter((event) => event.type !== "final").map((event) => (
          <li key={event.id} id={`card-${event.id}`}>
            <Card event={event} />
          </li>
        ))}
      </ol>
      {finalEvent ? (
        <section className="answer" id="card-final">
          <h2>Answer</h2>
          <p>{answer}</p>
          <div className="citations">
            {citations.map((citation, index) => (
              <a key={`${citation.stepId}-${index}`} href={`#card-${citation.stepId}`}>
                {citation.stepId}
                {citation.note ? ` · ${citation.note}` : ""}
              </a>
            ))}
          </div>
        </section>
      ) : null}
    </div>
  );
}

function Card({ event }: { event: TraceEvent }) {
  return (
    <article>
      <h2>{title(event)}</h2>
      <Body event={event} />
    </article>
  );
}

function title(event: TraceEvent) {
  if (event.type === "model") return `Model call ${String(event.payload.call)}`;
  return event.type.replaceAll("_", " ");
}

function Body({ event }: { event: TraceEvent }) {
  const payload = event.payload;
  if (event.type === "ground") {
    const matches = payload.matches as { phrase: string; kind: string; id: string; iri: string; score: number }[];
    return (
      <ul>
        {matches.map((match) => (
          <li key={match.iri ?? match.id}>
            <code>{match.id}</code> · {match.kind} · “{match.phrase}” · {match.score}
          </li>
        ))}
      </ul>
    );
  }
  if (event.type === "tools") {
    const tools = payload.tools as { tool: string; endpoint: string; classes: string[] }[];
    return (
      <ul>
        {tools.map((tool) => (
          <li key={tool.tool}>
            <strong>{tool.tool}</strong> · {tool.classes.join(", ")}
            <div className="muted">{tool.endpoint}</div>
          </li>
        ))}
      </ul>
    );
  }
  if (event.type === "tool_result") {
    return (
      <div>
        <p>
          {String(payload.tool)} from {((payload.sourceFiles as string[]) ?? []).join(", ")}
        </p>
        <p>Subjects: {((payload.subjects as string[]) ?? []).join(", ")}</p>
        <TripleList rows={(payload.unresolved as Row[]) ?? []} empty="No unresolved IRIs." label="Unresolved" />
      </div>
    );
  }
  if (event.type === "merge") {
    const links = payload.links as { id: string; referencedBy: string; definedBy: string }[];
    if (!links?.length) return <p>No cross-tool IRIs to resolve.</p>;
    return (
      <ul>
        {links.map((link) => (
          <li key={`${link.id}-${link.referencedBy}`}>
            {link.id} referenced by {link.referencedBy}, defined by {link.definedBy}
          </li>
        ))}
      </ul>
    );
  }
  if (event.type === "walk") {
    return (
      <div>
        <TripleList rows={(payload.triples as Row[]) ?? []} empty="No triples." label="Neighborhood" />
        <TripleList rows={(payload.frontier as Row[]) ?? []} empty="No further edges." label="Unresolved edges" />
      </div>
    );
  }
  if (event.type === "inference") {
    const results = payload.results as { property: string; member: string }[];
    return (
      <div>
        <p>{String(payload.query)}</p>
        <ul>
          {results.map((row) => (
            <li key={`${row.property}-${row.member}`}>
              {row.property} → {row.member}
            </li>
          ))}
        </ul>
      </div>
    );
  }
  if (event.type === "policy") {
    const passages = payload.passages as { id: string; score: number; text: string }[];
    return (
      <div>
        <p>Ranker: {String(payload.ranker)}</p>
        {passages.map((passage) => (
          <blockquote key={passage.id}>
            <strong>{passage.id}</strong> · {passage.score}
            <p>{passage.text}</p>
          </blockquote>
        ))}
      </div>
    );
  }
  if (event.type === "calculator") {
    return <pre>{JSON.stringify(payload.outputs, null, 2)}</pre>;
  }
  if (event.type === "model") {
    return (
      <div>
        <p>Source: {String((payload.response as { source?: string })?.source ?? "")}</p>
        <pre>{JSON.stringify(payload.response, null, 2)}</pre>
        {payload.prompt ? (
          <details>
            <summary>Prompt</summary>
            <pre>{String(payload.prompt)}</pre>
          </details>
        ) : null}
      </div>
    );
  }
  if (event.type === "expand") {
    const results = payload.results as { accepted: boolean; reason: string; predicate?: string; subject?: string }[];
    return (
      <ul>
        {results.map((result, index) => (
          <li key={index}>
            {result.accepted ? "Accepted" : "Dropped"} {result.subject} {result.predicate} · {result.reason}
          </li>
        ))}
      </ul>
    );
  }
  return <pre>{JSON.stringify(payload, null, 2)}</pre>;
}

type Row = { subject?: string; predicate?: string; object?: string; predicateIri?: string };

function TripleList({ rows, empty, label }: { rows: Row[]; empty: string; label: string }) {
  return (
    <div>
      <h3>{label}</h3>
      {rows.length === 0 ? (
        <p>{empty}</p>
      ) : (
        <ul>
          {rows.slice(0, 40).map((row, index) => (
            <li key={index}>
              {row.subject} {row.predicate} {row.object}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
