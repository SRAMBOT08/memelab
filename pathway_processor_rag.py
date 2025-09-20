# pathway_processor_rag.py
"""
RAG-enabled pathway processor:
- builds/loads FAISS index of text docs (./docs/*.txt by default)
- retrieves top-k contexts for each prompt
- constructs an augmented prompt and calls Gemini (GenAI Python client)
"""

import os
import glob
import json
from typing import List
from sentence_transformers import SentenceTransformer
import numpy as np

# faiss import is optional if installed
try:
    import faiss
    _HAS_FAISS = True
except Exception:
    faiss = None
    _HAS_FAISS = False

# Gemini client (user-provided snippet)
try:
    from google import genai
except Exception:
    genai = None

# Config
DOCS_GLOB = "./docs/*.txt"        # put your documents here (one file per doc)
INDEX_FILE = "./rag_index.npz"    # simple save/load for embeddings + metadata (no faiss) fallback
FAISS_INDEX_FILE = "./rag_index.faiss"  # if using faiss
EMBED_MODEL_NAME = "all-MiniLM-L6-v2"   # sentence-transformers embedding model
GEMINI_MODEL = os.environ.get("MODEL_NAME", "gemini-2.5-flash")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", None)

if GEMINI_API_KEY is None:
    print("Warning: GEMINI_API_KEY not set in env. Set $GEMINI_API_KEY before generating.")

# Load embedding model once
embed_model = SentenceTransformer(EMBED_MODEL_NAME)


def load_documents(glob_pattern: str = DOCS_GLOB) -> List[str]:
    docs = []
    for path in glob.glob(glob_pattern):
        try:
            with open(path, "r", encoding="utf-8") as f:
                text = f.read().strip()
                if text:
                    docs.append({"id": os.path.basename(path), "text": text})
        except Exception:
            continue
    return docs


def build_index(docs: List[dict], use_faiss: bool = _HAS_FAISS):
    texts = [d["text"] for d in docs]
    ids = [d["id"] for d in docs]
    embeddings = embed_model.encode(texts, show_progress_bar=True, convert_to_numpy=True)

    if use_faiss:
        dim = embeddings.shape[1]
        index = faiss.IndexFlatL2(dim)
        index.add(embeddings)
        faiss.write_index(index, FAISS_INDEX_FILE)
        # save metadata separately
        np.savez(INDEX_FILE, ids=np.array(ids), embeddings=embeddings)
        return {"type": "faiss", "index": index, "ids": ids, "embeddings": embeddings}
    else:
        # fallback: store embeddings + ids in an .npz file for nearest search via numpy
        np.savez(INDEX_FILE, ids=np.array(ids), embeddings=embeddings)
        return {"type": "np", "ids": ids, "embeddings": embeddings}


def load_index():
    if _HAS_FAISS and os.path.exists(FAISS_INDEX_FILE) and os.path.exists(INDEX_FILE):
        index = faiss.read_index(FAISS_INDEX_FILE)
        meta = np.load(INDEX_FILE, allow_pickle=True)
        ids = meta["ids"].tolist()
        embeddings = meta["embeddings"]
        return {"type": "faiss", "index": index, "ids": ids, "embeddings": embeddings}
    elif os.path.exists(INDEX_FILE):
        meta = np.load(INDEX_FILE, allow_pickle=True)
        return {"type": "np", "ids": meta["ids"].tolist(), "embeddings": meta["embeddings"]}
    else:
        return None


def retrieve(query: str, index_obj, top_k: int = 3):
    q_emb = embed_model.encode([query], convert_to_numpy=True)[0]
    if index_obj["type"] == "faiss":
        D, I = index_obj["index"].search(np.array([q_emb]), top_k)
        hits = []
        for idx in I[0]:
            if idx < len(index_obj["ids"]):
                hits.append({
                    "id": index_obj["ids"][idx],
                    "text": index_obj["embeddings"][idx]  # placeholders; we'll replace with actual doc text if we kept it
                })
        # We didn't store full texts in the faiss metadata above; re-load docs to map ids to text
        # simple mapping:
        docs_map = {d["id"]: d["text"] for d in load_documents()}
        results = []
        for i in I[0]:
            if i < len(index_obj["ids"]):
                doc_id = index_obj["ids"][i]
                results.append({"id": doc_id, "text": docs_map.get(doc_id, "")})
        return results
    else:
        # numpy fallback: compute dot-product / L2 distances
        embeddings = index_obj["embeddings"]
        # L2 distances:
        dists = np.linalg.norm(embeddings - q_emb, axis=1)
        idxs = np.argsort(dists)[:top_k]
        docs_map = {d["id"]: d["text"] for d in load_documents()}
        return [{"id": index_obj["ids"][int(i)], "text": docs_map.get(index_obj["ids"][int(i)], "")} for i in idxs]


def make_augmented_prompt(user_prompt: str, retrieved: List[dict]) -> str:
    # Simple prompt template: include retrieved passages labeled "CONTEXT"
    parts = ["You are a witty meme writer that uses the context below to make a short meme caption."]
    parts.append("CONTEXT:")
    for r in retrieved:
        parts.append(f"- {r['id']}: {r['text'][:500]}")  # truncate passage
    parts.append("USER PROMPT:")
    parts.append(user_prompt)
    parts.append("\nProduce a JSON object with captions and rationale, do not hallucinate.")
    return "\n\n".join(parts)


def generate_with_gemini(prompt_text: str, max_output_tokens: int = 512):
    if genai is None:
        raise RuntimeError("google.genai library not available; pip install google-genai")

    client = genai.Client(api_key=GEMINI_API_KEY)
    # using method names from the snippet you provided earlier:
    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt_text,
    )
    # response.text might contain the generated string
    return response.text


def ensure_index():
    idx = load_index()
    if idx is not None:
        return idx
    docs = load_documents()
    if not docs:
        print("No docs found under ./docs. RAG will still work but without external context.")
        return {"type": "empty", "ids": [], "embeddings": np.empty((0, embed_model.get_sentence_embedding_dimension()))}
    print(f"Building index for {len(docs)} documents...")
    return build_index(docs)


# High-level entry point: given a request dict, returns generated JSON (string)
def process_request(request: dict, top_k: int = 3):
    """
    request example:
      {"user":"tester", "prompt":"Make a funny meme about AI art lawsuits","tone":"deadpan"}
    """
    user_prompt = request.get("prompt", "")
    if not user_prompt:
        raise ValueError("No prompt provided in request")

    index_obj = ensure_index()
    # retrieve top-k passages
    if index_obj["type"] == "empty":
        retrieved = []
    else:
        retrieved = retrieve(user_prompt, index_obj, top_k=top_k)

    augmented = make_augmented_prompt(user_prompt, retrieved)
    # call Gemini
    out_text = generate_with_gemini(augmented)
    # Gemeni might return a JSON string; try to parse
    try:
        parsed = json.loads(out_text)
    except Exception:
        # fallback: wrap in simple JSON
        parsed = {"raw_output": out_text}
    return parsed


# For quick manual test
if __name__ == "__main__":
    # Example usage from CLI
    sample = {"user": "tester", "prompt": "Make a funny meme about AI art lawsuits", "tone": "deadpan"}
    print("Processing sample request (RAG -> Gemini)...")
    result = process_request(sample, top_k=3)
    print(json.dumps(result, indent=2, ensure_ascii=False))
