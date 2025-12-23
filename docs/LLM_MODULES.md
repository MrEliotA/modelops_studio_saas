# LLM Modules (Embedding / RAG / Eval / Labeling)

This repo includes lightweight, dependency-free helpers under `modelops.llm`
so teams can wire LLM workflows without requiring external services.

## Embeddings

`modelops.llm.embeddings.HashingEmbedding` provides deterministic, hash-based
embeddings for local demos.

```python
from modelops.llm.embeddings import HashingEmbedding

embedder = HashingEmbedding(dim=384)
vector = embedder.embed_text("hello world")
```

## RAG (Retrieval Augmented Generation)

Use the in-memory index and pipeline to build retrieval context:

```python
from modelops.llm.embeddings import HashingEmbedding
from modelops.llm.rag import Document, InMemoryVectorIndex, RAGPipeline

index = InMemoryVectorIndex(HashingEmbedding())
index.add_documents([
    Document(doc_id="doc-1", text="GPU nodes are monitored with DCGM."),
    Document(doc_id="doc-2", text="Kubeflow Pipelines can be used for training."),
])

rag = RAGPipeline(index)
context = rag.build_context("How do we observe GPUs?")
```

## Evaluation helpers

`evaluate_qa` computes exact match and token-level F1:

```python
from modelops.llm.eval import evaluate_qa

result = evaluate_qa("gpu exporter", "GPU exporter")
print(result.f1)
```

## Labeling helpers

The labeling queue is an in-memory helper for human-in-the-loop flows:

```python
from modelops.llm.labeling import LabelQueue, LabelTask

queue = LabelQueue()
queue.add_tasks([
    LabelTask(task_id="1", input_text="Classify this ticket"),
])

queue.assign("1", labeler="analyst@company")
queue.complete("1", labels={"priority": "high"})
```
