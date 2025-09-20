# send_test_message.py
from kafka import KafkaProducer
import json
import time

producer = KafkaProducer(
    bootstrap_servers="localhost:9092",
    value_serializer=lambda v: json.dumps(v).encode("utf-8"),
    retries=5
)

msg = {
    "user": "tester",
    "prompt": "Make a funny meme about AI art lawsuits",
    "tone": "deadpan"
}

producer.send("memelab.requests", msg)
producer.flush()
time.sleep(0.1)
print("Message sent to topic memelab.requests")
producer.close()
