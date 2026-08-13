"""Module 04 — RAG & Embeddings.

A complete retrieval system over the HomeShield policy docs in ./docs:
  1. Embeddings intuition — meaning as geometry
  2. Chunk + index + retrieve (numpy IS the vector database)
  3. Pipeline RAG — one-shot retrieve-then-answer, with citations
  4. Agentic RAG — retrieval as a TOOL in the module-02 loop (multi-hop)

Run from the repo root:  uv run modules/04-rag-and-embeddings/example.py
(first run downloads the ~80MB embedding model)
"""

import json
from pathlib import Path
from typing import cast

import numpy as np
from anthropic import Anthropic
from anthropic.types import MessageParam, ToolParam
from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer

load_dotenv()

MODEL = "claude-opus-5"
DOCS_DIR = Path(__file__).parent / "docs"
client = Anthropic()

# The embedding model is a SEPARATE, tiny, local model — Claude generates,
# it does not embed. In production this would be Voyage/OpenAI embeddings.
embedder = SentenceTransformer("all-MiniLM-L6-v2")


def embed(texts: list[str]) -> np.ndarray:
    # normalize_embeddings=True -> unit length -> cosine similarity == dot product
    return np.asarray(embedder.encode(texts, normalize_embeddings=True))


# ---------------------------------------------------------------------------
# DEMO 1: embeddings turn meaning into geometry
# ---------------------------------------------------------------------------


def demo_1_embeddings() -> None:
    print("=" * 70)
    print("DEMO 1: embeddings — texts with similar MEANING land close together")
    print("=" * 70)

    sentences = [
        "my basement flooded from a busted pipe",
        "sudden accidental discharge of water from plumbing",
        "how do I cancel my insurance policy",
        "I like turtles",
    ]
    vecs = embed(sentences)
    print(f"\nEach sentence -> a vector of {vecs.shape[1]} numbers. Similarities:\n")

    sims = vecs @ vecs.T  # all pairwise cosine similarities at once
    for i, s in enumerate(sentences):
        print(f'  "{s}"')
        for j in range(len(sentences)):
            if j != i:
                print(f"      {sims[i, j]:+.2f}  vs  \"{sentences[j]}\"")
        print()
    print("Note: 'flooded/busted pipe' vs 'discharge of water from plumbing'\n"
          "share almost no words — the geometry knows they mean the same thing.")


# ---------------------------------------------------------------------------
# DEMO 2: chunk the corpus, build the index, retrieve.
# The "vector database" is one numpy array + one dot product.
# ---------------------------------------------------------------------------

# Chunking by document structure: one chunk per '## ' section, tagged with
# its source. Bad chunking is the #1 cause of bad RAG.
CHUNKS: list[dict] = []
for doc in sorted(DOCS_DIR.glob("*.md")):
    title, *sections = doc.read_text().split("\n## ")
    for section in sections:
        heading, _, body = section.partition("\n")
        CHUNKS.append({
            "source": f"{doc.name} > {heading.strip()}",
            "text": body.strip(),
        })

INDEX = embed([f"{c['source']}\n{c['text']}" for c in CHUNKS])  # (n_chunks, 384)


def search_docs(query: str, k: int = 3) -> list[dict]:
    """The retrieval function — used by BOTH pipeline RAG and agentic RAG."""
    sims = INDEX @ embed([query])[0]
    return [
        {"score": float(sims[i]), **CHUNKS[i]}
        for i in np.argsort(sims)[::-1][:k]
    ]


def demo_2_retrieval() -> None:
    print("\n" + "=" * 70)
    print(f"DEMO 2: the index — {len(CHUNKS)} chunks from "
          f"{len(list(DOCS_DIR.glob('*.md')))} docs, one numpy array")
    print("=" * 70)

    query = "the pipes behind my washer burst and wrecked the floor, am I covered?"
    print(f'\nQuery: "{query}"\n\nTop 3 chunks by cosine similarity:')
    for hit in search_docs(query):
        print(f"  {hit['score']:.2f}  {hit['source']}")
    print("\nThe right clause ranks first despite ~zero keyword overlap.")


# ---------------------------------------------------------------------------
# DEMO 3: pipeline RAG — retrieve once, stuff the prompt, answer with citations
# ---------------------------------------------------------------------------


def get_text(response) -> str:
    text = "".join(b.text for b in response.content if b.type == "text")
    return text or f"(no text — stop_reason={response.stop_reason!r})"


def ask(question: str, context_chunks: list[dict] | None = None) -> str:
    if context_chunks is None:
        system = "You are a support agent for HomeShield Insurance."
        user = question
    else:
        numbered = "\n\n".join(
            f"[{i}] ({c['source']})\n{c['text']}" for i, c in enumerate(context_chunks, 1)
        )
        system = (
            "You are a support agent for HomeShield Insurance. Answer ONLY from "
            "the provided policy excerpts, citing them like [1]. If the excerpts "
            "don't contain the answer, say so — do not guess."
        )
        user = f"Policy excerpts:\n\n{numbered}\n\nCustomer question: {question}"
    response = client.messages.create(
        model=MODEL, max_tokens=4000, system=system,
        messages=[{"role": "user", "content": user}],
    )
    return get_text(response)


def demo_3_pipeline_rag() -> None:
    print("\n" + "=" * 70)
    print("DEMO 3: pipeline RAG — same question, without and with retrieval")
    print("=" * 70)

    question = "A pipe burst and soaked my laundry room floor. Am I covered?"

    print(f"\nQ: {question}")
    print(f"\n--- WITHOUT retrieval (ungrounded) ---\n{ask(question)}")

    chunks = search_docs(question)
    print(f"\n--- WITH retrieval (grounded, cited) ---\n{ask(question, chunks)}")
    print("\nThe grounded answer speaks from YOUR policy and cites clauses a\n"
          "human can check. The ungrounded one can only speak in generalities.")


# ---------------------------------------------------------------------------
# DEMO 4: agentic RAG — retrieval becomes a tool inside the agent loop.
# One search can't answer this question; watch the model search repeatedly.
# ---------------------------------------------------------------------------

SEARCH_TOOL: ToolParam = {
    "name": "search_docs",
    "description": (
        "Search HomeShield's policy documents and internal handbook. Returns the "
        "3 most relevant sections. Search as many times as you need with "
        "different queries to gather all the facts before answering."
    ),
    "input_schema": {
        "type": "object",
        "properties": {"query": {"type": "string"}},
        "required": ["query"],
    },
}

MULTI_HOP_QUESTION = (
    "A pipe burst in my laundry room on July 3rd (I reported it today, Aug 11). "
    "The plumber's written estimate is $2,400 and a rug I bought for $300 was "
    "ruined. How much will HomeShield actually pay me, and is there anything "
    "that could hold up my claim?"
)


def demo_4_agentic_rag() -> None:
    print("\n" + "=" * 70)
    print("DEMO 4: agentic RAG — the model drives retrieval (multi-hop)")
    print("=" * 70)
    print(f"\nQ: {MULTI_HOP_QUESTION}\n")

    messages: list[MessageParam] = [{"role": "user", "content": MULTI_HOP_QUESTION}]
    for iteration in range(1, 9):
        response = client.messages.create(
            model=MODEL,
            max_tokens=4000,
            system=(
                "You are a claims support agent for HomeShield Insurance. Ground "
                "every fact in the policy docs via search_docs; cite section "
                "names. Compute the actual payout math."
            ),
            tools=[SEARCH_TOOL],
            messages=messages,
        )
        if response.stop_reason != "tool_use":
            print(f"\nagent: {get_text(response)}")
            print(f"\n--- done after {iteration} rounds ---")
            return

        messages.append({"role": "assistant", "content": response.content})
        results = []
        for block in response.content:
            if block.type == "tool_use":
                query = cast(dict, block.input)["query"]
                hits = search_docs(query)
                print(f"[{iteration}] search_docs({json.dumps(query)})")
                for h in hits:
                    print(f"      {h['score']:.2f}  {h['source']}")
                results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": json.dumps(hits),
                })
        messages.append({"role": "user", "content": results})


if __name__ == "__main__":
    demo_1_embeddings()
    demo_2_retrieval()
    demo_3_pipeline_rag()
    demo_4_agentic_rag()
