# create_topic.py
from kafka.admin import KafkaAdminClient, NewTopic
admin = KafkaAdminClient(bootstrap_servers="127.0.0.1:9092", client_id='memelab-admin')
topic = NewTopic(name="memelab.requests", num_partitions=1, replication_factor=1)
try:
    admin.create_topics([topic])
    print("Created topic memelab.requests")
except Exception as e:
    print("Create topics error (maybe exists):", e)
finally:
    admin.close()
