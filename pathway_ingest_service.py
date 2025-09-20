# pathway_ingest_service.py
import json
from flask import Flask, request, jsonify
import logging

# import the processor you created
import pathway_processor

app = Flask(__name__)
app.logger.setLevel(logging.INFO)

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"}), 200

@app.route("/ingest", methods=["POST"])
def ingest():
    # get JSON body
    payload = request.get_json(force=True)

    # log receipt
    app.logger.info("Received payload: %s", json.dumps(payload))

    # --- Call the pathway processor synchronously (simulator or real) ---
    try:
        processed = pathway_processor.process(payload)
        app.logger.info("Processed result: %s", json.dumps(processed))
    except Exception as e:
        app.logger.exception("Pathway processing failed")
        processed = {"status": "processing_failed", "error": str(e)}

    # Return an acceptance + the processed result for debugging
    return jsonify({"status": "accepted", "processing": processed}), 200


if __name__ == "__main__":
    # run on same host/port you used previously
    app.run(host="127.0.0.1", port=5000, debug=False)
