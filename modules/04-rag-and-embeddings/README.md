# 04 — RAG & Embeddings

The "grounded in domain data" part of the mental model. The model's weights know
a compressed snapshot of the public internet as of its training date. They know
*nothing* about HomeShield's policy terms, your company's handbook, yesterday's
ticket, or the customer's contract. The context window is the only door into the
model — and it's finite. **RAG (Retrieval-Augmented Generation) is the machinery
that decides which few thousand tokens of your domain data deserve to walk
through that door for this particular question.**

## Embeddings: meaning as geometry

The enabling trick. An embedding model maps text to a point in high-dimensional
space (our local model: 384 numbers), trained so that *texts that mean similar
things land close together* — even with zero words in common:

```
"my basement flooded from a busted pipe"
"sudden and accidental discharge of water from plumbing"   <- close (≈0.5)
"I like turtles"                                           <- far   (≈0.0)
```

Closeness is measured with **cosine similarity** (for unit-length vectors, just
the dot product). That's the entire magic: search becomes geometry, so a
paraphrase finds the right document where keyword search (`grep`, SQL `LIKE`,
classic BM25 alone) would miss it.

Note the asymmetry that trips people up: Claude does not produce embeddings.
Embedding models are separate, small, cheap models (Voyage, OpenAI
`text-embedding-*`, open-source `sentence-transformers`). Companies run BOTH:
an embedding model for retrieval, an LLM for generation.

## The pipeline

```
 INGEST (offline, once per document)          QUERY (per question)
 ┌──────────┐   ┌───────┐   ┌───────┐         ┌────────┐   ┌──────────┐
 │ documents│──▶│ chunk │──▶│ embed │──▶┐  ┌──│ embed  │◀──│ question │
 └──────────┘   └───────┘   └───────┘  ▼  ▼   └────────┘   └──────────┘
                                 ┌──────────────┐
                                 │ vector index │  top-k by cosine
                                 └──────┬───────┘
                                        ▼
                    ┌───────────────────────────────────────┐
                    │ prompt = question + the k best chunks │──▶ LLM ──▶ cited answer
                    └───────────────────────────────────────┘
```

**Chunking is where quality lives.** Whole documents dilute the signal; single
sentences lose context. Real systems chunk by structure (headings, paragraphs —
what we do here), add overlap between chunks, and prepend metadata like the
source filename and section title so the chunk is self-explanatory. Bad chunking
is the #1 cause of "our RAG doesn't work."

**Citations are not decoration.** Grounded answers cite their chunks so (a) the
human can verify, and (b) the system can detect when an answer cites nothing —
a hallucination tripwire. In regulated verticals the citation IS the product
(module 03's coverage-check step must point at the policy clause).

## Pipeline RAG vs agentic RAG

The pipeline above retrieves **once**, blindly, before the model sees anything.
That fails on multi-hop questions ("how much will I actually be paid?" needs
the coverage clause AND the deductible clause AND the documentation rules).

**Agentic RAG** hands retrieval to the agent as a tool (module 02's loop +
a `search_docs` tool): the model reads, notices what it still doesn't know,
reformulates, and searches again. This is the direction the industry moved —
retrieval as a tool call, not a fixed pipeline stage. The tradeoff: more
LLM calls, more latency, more cost — so support bots often keep the cheap
one-shot pipeline for easy questions and escalate to the agentic loop.

## What production adds (that we deliberately skip)

| Upgrade | What it is |
|---|---|
| Vector DB | pgvector / Pinecone / Weaviate / Chroma — persistence, millions of vectors, metadata filters ("only THIS customer's docs" — critical for multi-tenant) |
| Hybrid search | combine vector similarity with keyword BM25 — exact IDs and part numbers embed poorly |
| Reranker | a second, better model re-sorts the top ~50 candidates down to the best 5 |
| Retrieval evals | measure recall@k on a golden set of (question, right-chunk) pairs — separately from answer quality |
| Freshness pipeline | re-chunk and re-embed when the source docs change |

We use a numpy array and a dot product instead, because at learning scale a
vector DB is three lines of numpy — and knowing that is itself the lesson:
the moat is never "they have a vector database."

## Vocabulary

| Term | Meaning |
|---|---|
| embedding | vector representing a text's meaning |
| cosine similarity | closeness measure between vectors (dot product when normalized) |
| chunk | the unit of retrieval — a slice of a document |
| top-k | keep the k most similar chunks |
| BM25 / hybrid | keyword scoring; combined with vectors in production |
| reranker | model that re-sorts candidates for relevance |
| grounding | forcing answers to come from retrieved text, with citations |
| recall@k | eval metric: how often the right chunk is in the top k |

## Run it

```bash
uv sync   # picks up numpy + sentence-transformers (first run downloads an ~80MB model)
uv run modules/04-rag-and-embeddings/example.py
```

Four demos over a small HomeShield policy corpus (`docs/`): embedding intuition,
retrieval with zero keyword overlap, one-shot pipeline RAG with citations (vs.
the ungrounded answer), and an agentic multi-hop payout question.
