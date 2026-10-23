"""Policy passages that are outside the ontology."""

from pathlib import Path

from app.ranker import Ranker

POLICY_DIR = Path(__file__).resolve().parents[1] / "policy"
_CUTOFF = 0.34


def load_passages() -> list[dict]:
    passages = []
    for path in sorted(POLICY_DIR.glob("*.md")):
        raw = path.read_text()
        lines = raw.splitlines()
        ident = path.stem
        body = []
        for line in lines:
            if line.startswith("id:"):
                ident = line.split(":", 1)[1].strip()
            elif line.strip() == "---":
                continue
            else:
                body.append(line)
        passages.append({"id": ident, "text": "\n".join(body).strip()})
    return passages


def search(ranker: Ranker, question: str, passages: list[dict]) -> dict:
    scored = []
    for passage in passages:
        score = ranker.score(question, passage["text"])
        if score >= _CUTOFF:
            scored.append({"id": passage["id"], "text": passage["text"], "score": round(score, 3)})
    scored.sort(key=lambda row: -row["score"])
    return {"ranker": ranker.mode, "passages": scored[:4]}
