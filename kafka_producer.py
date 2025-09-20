# kafka_producer.py
import json
import time
from kafka import KafkaProducer

BOOTSTRAP = "host.docker.internal:9092"
TOPIC = "memelab.requests"

def make_producer():
    return KafkaProducer(
        bootstrap_servers=BOOTSTRAP,
        value_serializer=lambda v: json.dumps(v, ensure_ascii=False).encode("utf-8"),
        retries=3,
        linger_ms=10,
    )

def send_request(producer, user, prompt, tone="neutral", extra=None, timeout=10):
    payload = {
        "user": user,
        "prompt": prompt,
        "tone": tone,
        "meta": extra or {}
    }
    try:
        future = producer.send(TOPIC, value=payload)
        record_metadata = future.get(timeout=timeout)
        print(f"[producer] sent -> topic={record_metadata.topic} partition={record_metadata.partition} offset={record_metadata.offset}")
        return {"ok": True, "topic": record_metadata.topic, "partition": record_metadata.partition, "offset": record_metadata.offset}
    except Exception as e:
        print("[producer] failed to send:", e)
        return {"ok": False, "error": str(e)}

if __name__ == "__main__":
    p = make_producer()
    print(f"[producer] bootstrap={BOOTSTRAP} topic={TOPIC}")
    # Example demo message (change as needed)
    resp = send_request(
        p,
        user="tester",
        prompt="Make a meme about AI art lawsuits",
        tone="deadpan",
        extra={"source": "manual-test"}
    )
    # tiny pause then flush
    time.sleep(0.2)
    p.flush()
    print("[producer] finished:", resp)
