import json
import os
import threading
import time
import uuid

import redis
from flask import Flask, jsonify, request

from llm.factory import get_llm_provider

app = Flask(__name__)

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
QUEUE_KEY = "llm:queue"
RESULT_PREFIX = "llm:result:"
RESULT_TTL = int(os.getenv("LLM_RESULT_TTL", "3600"))


def get_redis():
    return redis.from_url(REDIS_URL, decode_responses=True)


@app.route("/health-check")
def health_check():
    return jsonify({"status": "ok"})


@app.route("/jobs", methods=["POST"])
def submit_job():
    payload = request.get_json(force=True)
    job_id = str(uuid.uuid4())
    job = {
        "job_id": job_id,
        "type": payload.get("type"),
        "model": payload.get("model"),
        "payload": payload.get("payload", {}),
        "status": "pending",
        "submitted_at": time.time(),
    }
    r = get_redis()
    r.set(f"{RESULT_PREFIX}{job_id}", json.dumps(job), ex=RESULT_TTL)
    r.rpush(QUEUE_KEY, job_id)
    return jsonify({"job_id": job_id, "status": "pending"}), 202


@app.route("/jobs/<job_id>")
def get_job(job_id):
    r = get_redis()
    raw = r.get(f"{RESULT_PREFIX}{job_id}")
    if not raw:
        return jsonify({"error": "Job not found"}), 404
    return jsonify(json.loads(raw))


def process_job(job_id: str, job: dict):
    provider = get_llm_provider()
    job_type = job.get("type")
    payload = job.get("payload", {})
    try:
        if job_type == "complete_json":
            result = provider.complete_json(
                payload.get("system", ""),
                payload.get("user", ""),
                schema=payload.get("schema"),
            )
        elif job_type == "complete_text":
            result = provider.complete_text(payload.get("system", ""), payload.get("user", ""))
        elif job_type == "complete_vision":
            result = provider.complete_vision(payload.get("prompt", ""), payload.get("image_b64", ""))
        else:
            raise ValueError(f"Unknown job type: {job_type}")

        job["status"] = "complete"
        job["result"] = result
    except Exception as exc:
        job["status"] = "failed"
        job["error"] = str(exc)
    job["completed_at"] = time.time()
    get_redis().set(f"{RESULT_PREFIX}{job_id}", json.dumps(job), ex=RESULT_TTL)


def worker_loop():
    r = get_redis()
    print("Inference gateway worker started")
    while True:
        item = r.blpop(QUEUE_KEY, timeout=5)
        if not item:
            continue
        _, job_id = item
        raw = r.get(f"{RESULT_PREFIX}{job_id}")
        if not raw:
            continue
        job = json.loads(raw)
        job["status"] = "processing"
        r.set(f"{RESULT_PREFIX}{job_id}", json.dumps(job), ex=RESULT_TTL)
        process_job(job_id, job)


def start_worker():
    thread = threading.Thread(target=worker_loop, daemon=True)
    thread.start()


if __name__ == "__main__":
    start_worker()
    app.run(host="0.0.0.0", port=int(os.getenv("GATEWAY_PORT", "8090")))
