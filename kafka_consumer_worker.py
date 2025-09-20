#!/usr/bin/env python3
"""
kafka_consumer_worker.py

Robust Kafka consumer for the memelab pipeline.

- Listens to topic (default "memelab.requests")
- Safely deserializes messages (skips malformed/empty ones)
- Forwards parsed JSON payloads to an ingest HTTP endpoint
- Prints/logs outcomes so you can demo the pipeline
"""

import os
import json
import time
import logging
from typing import Any, Dict, Optional

import requests
from kafka import KafkaConsumer

# Configuration via env (easy to change per-machine)
KAFKA_BOOTSTRAP = os.environ.get("KAFKA_BOOTSTRAP", "localhost:9092")
KAFKA_TOPIC = os.environ.get("KAFKA_TOPIC", "memelab.requests")
KAFKA_GROUP = os.environ.get("KAFKA_GROUP", "memelab-consumer")
INGEST_URL = os.environ.get("INGEST_URL", "http://127.0.0.1:5000/ingest")
POLL_TIMEOUT_SECONDS = float(os.environ.get("POLL_TIMEOUT_SECONDS", "1.0"))

# Logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("kafka_consumer_worker")


def safe_deserialize(value: Optional[bytes]) -> Optional[Any]:
    """Attempt to turn Kafka message bytes into JSON object or a fallback string.
    Returns None for empty input, JSON object for valid JSON, string fallback otherwise.
    """
    if value is None:
        return None
    if isinstance(value, dict):
        # already deserialized by some callers
        return value
    try:
        text = value.decode("utf-8")
    except Exception:
        # cannot decode bytes
        try:
            return value.decode("utf-8", errors="replace")
        except Exception:
            # ultimately return raw bytes
            return value

    text = text.strip()
    if not text:
        return None

    # If message is plain JSON -> return object
    try:
        return json.loads(text)
    except Exception:
        # not JSON, return raw text
        return text


def forward_to_ingest(payload: Dict[str, Any]) -> Dict[str, Any]:
    """POST JSON payload to the ingest service and return parsed result or error info."""
    try:
        resp = requests.post(INGEST_URL, json=payload, timeout=30)
    except Exception as exc:
        logger.error("Failed to POST to ingest URL %s: %s", INGEST_URL, exc)
        return {"ok": False, "error": str(exc)}

    result: Dict[str, Any] = {"ok": resp.ok, "status_code": resp.status_code}
    try:
        # prefer JSON response
        result["body"] = resp.json()
    except Exception:
        result["body_text"] = resp.text
    return result


def make_consumer() -> KafkaConsumer:
    """Create a KafkaConsumer that returns raw bytes (we handle deserialization ourselves)."""
    consumer = KafkaConsumer(
        KAFKA_TOPIC,
        bootstrap_servers=KAFKA_BOOTSTRAP,
        group_id=KAFKA_GROUP,
        auto_offset_reset="earliest",
        enable_auto_commit=True,
        # Keep raw bytes so we can avoid library-side decode exceptions
        value_deserializer=lambda v: v,
    )
    return consumer


def run():
    logger.info("Starting consumer: topic=%s bootstrap=%s group=%s", KAFKA_TOPIC, KAFKA_BOOTSTRAP, KAFKA_GROUP)
    consumer = make_consumer()
    print(f"[consumer] listening to topic={KAFKA_TOPIC} (bootstrap={KAFKA_BOOTSTRAP}) -> posting to {INGEST_URL}")

    try:
        for msg in consumer:
            # msg.value is raw bytes (or whatever producer sent)
            raw = msg.value
            if raw is None:
                logger.info("[consumer] skipping empty message (None)")
                continue

            parsed = safe_deserialize(raw)
            if parsed is None:
                logger.info("[consumer] skipping empty/whitespace message")
                continue

            # If parsed is JSON object -> good; if it's a string, try to parse as JSON
            payload: Optional[Dict[str, Any]] = None
            if isinstance(parsed, dict):
                payload = parsed
            elif isinstance(parsed, str):
                # maybe producer sent stringified JSON
                try:
                    payload = json.loads(parsed)
                except Exception:
                    # Not JSON: we will wrap the text into a minimal payload so ingest gets something meaningful
                    payload = {"user": "unknown", "prompt": parsed, "meta": {"raw": True}}
            else:
                # bytes fallback or unexpected type
                try:
                    payload = {"user": "unknown", "prompt": str(parsed)}
                except Exception:
                    payload = {"user": "unknown", "prompt": "<unserializable payload>"}

            logger.info("[consumer] received payload: %s", str(payload)[:400])
            print(f"[consumer] received: {payload}")

            # Forward to ingest (and print result). This is where your pathway processor / flask ingest handles it.
            result = forward_to_ingest(payload)
            logger.info("[consumer] ingest result: %s", str(result)[:500])
            print(f"[consumer] ingest result: {result}")

            # small sleep to keep output stable during demo
            time.sleep(0.05)

    except KeyboardInterrupt:
        print("[consumer] stopped by user")
    except Exception as e:
        logger.exception("Consumer encountered an error: %s", e)
    finally:
        try:
            consumer.close()
        except Exception:
            pass
        logger.info("Consumer shutdown complete.")


if __name__ == "__main__":
    run()
