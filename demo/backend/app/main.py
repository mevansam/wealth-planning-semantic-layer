"""Trace stream for the demo page."""

import json

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.loop import Engine

app = FastAPI(title="Wealth retrieval demo")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)
engine = Engine()


class Ask(BaseModel):
    question: str


@app.get("/api/health")
def health() -> dict:
    return {"ok": True, "ranker": engine.ranker.mode}


@app.post("/api/ask")
def ask(body: Ask) -> StreamingResponse:
    def stream():
        for event in engine.run(body.question):
            yield f"data: {json.dumps(event)}\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream")
