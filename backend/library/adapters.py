"""External ports. The HTTP API and MQTT consumer share the same ingestion service."""
import json
import os
import uuid
from paho.mqtt.client import Client, CallbackAPIVersion


def mqtt_client(client_id):
    client = Client(CallbackAPIVersion.VERSION2, client_id=client_id)
    if os.getenv('MQTT_USERNAME'):
        client.username_pw_set(os.environ['MQTT_USERNAME'], os.environ['MQTT_PASSWORD'])
    if os.getenv('MQTT_TLS', '0') == '1':
        client.tls_set()
    return client


def connect(client):
    client.connect(os.getenv('MQTT_HOST', 'localhost'), int(os.getenv('MQTT_PORT', '1883')), 60)


def event_envelope(kind, payload):
    return {'event_id': str(uuid.uuid4()), 'kind': kind, 'payload': payload}
