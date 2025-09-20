# call_gemini.py
import os
import json
import time

from typing import Dict, Any

# try to load .env (optional)
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
MODEL_NAME = os.environ.get("MODEL_NAME", "gemini-1.5-mini")  # change if needed

def _use_google_client(prompt: str, max_tokens: int = 512) -> Dict[str, Any]:
    """
    Use google-generative-ai python client if available.
    """
    import google.generativeai as genai  # installed from google-generative-ai
    genai.configure(api_key=GEMINI_API_KEY)
    # Using the text generation helper (name differs by client version; adapt if needed)
    response = genai.generate_text(
        model=MODEL_NAME,
        prompt=prompt,
        max_output_tokens=max_tokens
    )
    # response shape varies by client; try to extract text robustly
    text = ""
    # new client: response.candidates[0].output or response.output[0].content
    if hasattr(response, "candidates") and response.candidates:
        text = response.candidates[0].content if hasattr(response.candidates[0], "content") else str(response.candidates[0])
    elif hasattr(response, "output") and response.output:
        # Sometimes nested
        text = response.output[0].content if isinstance(response.output, list) else str(response.output)
    else:
        # fallback: stringify
        text = str(response)
    return {"raw": response, "text": text}


def _use_rest(prompt: str, max_tokens: int = 512) -> Dict[str, Any]:
    """
    Fallback: call Google Generative Language REST endpoint using API KEY.
    Works with Gemini 1.5+ models.
    """
    import requests
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY not set in environment")

    endpoint = f"https://generativelanguage.googleapis.com/v1/models/{MODEL_NAME}:generateContent"
    headers = {
        "Content-Type": "application/json",
        "x-goog-api-key": GEMINI_API_KEY,
    }
    payload = {
        "contents": [
            {"parts": [{"text": prompt}]}
        ]
    }

    r = requests.post(endpoint, headers=headers, json=payload, timeout=30)
    r.raise_for_status()
    resp = r.json()

    # Extract text from response
    text = ""
    try:
        text = resp["candidates"][0]["content"]["parts"][0]["text"]
    except Exception:
        text = json.dumps(resp)

    return {"raw": resp, "text": text}

def call_gemini(prompt: str, max_tokens: int = 512) -> str:
    """
    Unified helper: attempt client, then fallback to REST.
    Returns extracted text string.
    """
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY environment variable not set.")
    # Try the google client first
    try:
        # lazy import so it fails gracefully if not installed
        return _use_google_client(prompt, max_tokens)["text"]
    except Exception as e:
        # print debug info (optional)
        # print("google client failed:", e)
        try:
            return _use_rest(prompt, max_tokens)["text"]
        except Exception as e2:
            # both failed: surface both errors
            raise RuntimeError(f"Both client and REST calls failed. client err: {e}; rest err: {e2}")

if __name__ == "__main__":
    # quick standalone test: read prompt from env VAR or stdin/arg
    import sys
    prompt = ""
    if len(sys.argv) > 1:
        prompt = " ".join(sys.argv[1:])
    else:
        try:
            # read from stdin if available
            prompt = sys.stdin.read().strip()
        except Exception:
            prompt = ""
    if not prompt:
        prompt = "Write a short joke about programming."

    print("PROMPT:", prompt)
    out = call_gemini(prompt, max_tokens=200)
    print("RESULT:\n", out)
