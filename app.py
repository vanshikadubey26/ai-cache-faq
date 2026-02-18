import time
import hashlib
from fastapi import FastAPI
from pydantic import BaseModel
from collections import OrderedDict
from difflib import SequenceMatcher

# ---------------- CONFIG ----------------
CACHE_LIMIT = 1500
TTL_SECONDS = 24 * 3600
MODEL_COST_PER_1M = 0.50
TOKENS_PER_REQ = 500
BASELINE_COST = 3.21

app = FastAPI()

exact_cache = OrderedDict()
semantic_cache = []

total_requests = 0
cache_hits = 0
cache_misses = 0


def normalize(q):
    return q.strip().lower()


def md5_key(q):
    return hashlib.md5(q.encode()).hexdigest()


def similarity(a, b):
    return SequenceMatcher(None, a, b).ratio()


def llm_call(query):
    time.sleep(0.8)  # simulate API latency
    return f"Answer for: {query}"


def cleanup_cache():
    now = time.time()
    expired = [k for k, v in exact_cache.items() if now - v["created"] > TTL_SECONDS]
    for k in expired:
        del exact_cache[k]


class Query(BaseModel):
    query: str
    application: str


@app.post("/")
def ask(q: Query):
    global total_requests, cache_hits, cache_misses

    start = time.time()
    total_requests += 1

    qn = normalize(q.query)
    key = md5_key(qn)

    cleanup_cache()

    # Exact cache
    if key in exact_cache:
        cache_hits += 1
        exact_cache.move_to_end(key)
        return {
            "answer": exact_cache[key]["answer"],
            "cached": True,
            "latency": int((time.time() - start) * 1000),
            "cacheKey": key
        }

    # Semantic cache
    for e in semantic_cache:
        if similarity(qn, e["query"]) > 0.95:
            cache_hits += 1
            return {
                "answer": e["answer"],
                "cached": True,
                "latency": int((time.time() - start) * 1000),
                "cacheKey": "semantic"
            }

    # Miss → fake LLM
    cache_misses += 1
    ans = llm_call(q.query)

    exact_cache[key] = {"answer": ans, "created": time.time()}
    if len(exact_cache) > CACHE_LIMIT:
        exact_cache.popitem(last=False)

    semantic_cache.append({"query": qn, "answer": ans})

    return {
        "answer": ans,
        "cached": False,
        "latency": int((time.time() - start) * 1000),
        "cacheKey": key
    }


@app.get("/analytics")
def analytics():
    hit_rate = cache_hits / total_requests if total_requests else 0
    actual_tokens = cache_misses * TOKENS_PER_REQ
    actual_cost = (actual_tokens / 1_000_000) * MODEL_COST_PER_1M
    savings = BASELINE_COST - actual_cost
    savings_percent = (savings / BASELINE_COST) * 100 if BASELINE_COST else 0

    return {
        "hitRate": round(hit_rate, 2),
        "totalRequests": total_requests,
        "cacheHits": cache_hits,
        "cacheMisses": cache_misses,
        "cacheSize": len(exact_cache),
        "costSavings": round(savings, 2),
        "savingsPercent": int(savings_percent),
        "strategies": [
            "exact match",
            "semantic similarity",
            "LRU eviction",
            "TTL expiration"
        ]
    }
