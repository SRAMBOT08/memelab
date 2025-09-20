#!/usr/bin/env python3
"""
run_prompt_sim.py
- Reads JSON from stdin (or --input-file)
- Calls Google Gemini via google-genai if GEMINI_API_KEY is set and MODEL_NAME provided
- Always prints JSON to stdout (fallback JSON on errors)
"""

import os
import sys
import argparse
import json
import traceback
from typing import Dict, Any
from dotenv import load_dotenv
load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
MODEL_NAME = os.getenv("MODEL_NAME", "gemini-1.5-mini")

def read_input(args) -> Dict[str,Any]:
    if args.input_file:
        with open(args.input_file, "r", encoding="utf-8") as f:
            return json.load(f)
    raw = sys.stdin.read()
    if not raw.strip():
        raise ValueError("No input on stdin and --input-file not provided")
    return json.loads(raw)

def fake_output(inp: Dict[str,Any]) -> Dict[str,Any]:
    return {
        "captions": [
            {
                "id": "A",
                "text": f"{inp.get('user','user')}: {inp.get('prompt','(no prompt)')} (tone={inp.get('tone','')})",
                "image_idea": "simple idea"
            }
        ],
        "safety_flag": "none",
        "rationale": "placeholder result from run_prompt_sim"
    }

def call_gemini(prompt_text: str, model_name: str, api_key: str) -> Dict[str,Any]:
    # Uses google-genai client
    try:
        from google import genai
    except Exception as e:
        raise RuntimeError("google-genai client not installed. pip install google-genai") from e

    client = genai.Client(api_key=api_key)
    # Use models.generate_content (client API) — adjust if your client version differs
    resp = client.models.generate_content(model=model_name, contents=prompt_text)
    # Try to extract textual output
    text = ""
    if hasattr(resp, "text"):
        text = resp.text
    else:
        # some client versions return a dict-like structure
        try:
            text = resp.__dict__.get("text", "") or str(resp)
        except Exception:
            text = str(resp)
    return {"raw_text": text, "full_response": resp}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-file", help="Read JSON input from file instead of stdin")
    parser.add_argument("--model-name", help="Override MODEL_NAME env")
    args = parser.parse_args()

    try:
        data = read_input(args)
    except Exception as e:
        out = {"error": "invalid_input", "message": str(e)}
        print(json.dumps(out, ensure_ascii=False))
        sys.exit(1)

    user = data.get("user", "user")
    prompt = data.get("prompt", "")
    tone = data.get("tone", "")
    # Compose a clear prompt for Gemini
    composed = (
        f"User: {user}\n"
        f"Prompt: {prompt}\n"
        f"Tone: {tone}\n\n"
        "Task: produce JSON with keys: captions (array of {id,text,image_idea}), "
        "safety_flag (string), and rationale (one-line). Output only valid JSON."
    )

    # Provider config (we only support Gemini here)
    model_env = args.model_name or os.environ.get("MODEL_NAME", "gemini-1.5-mini")
    api_key = os.environ.get("GEMINI_API_KEY")

    if api_key:
        try:
            model_resp = call_gemini(composed, model_env, api_key)
            raw = model_resp.get("raw_text", "") or ""
            # If model returned valid JSON, parse and output it directly
            try:
                parsed = json.loads(raw)
                print(json.dumps(parsed, ensure_ascii=False))
                return
            except Exception:
                # Not JSON — return fallback but include model raw output in rationale
                out = fake_output(data)
                # clamp long model outputs in rationale
                out["rationale"] = (raw[:800] + "...") if len(raw) > 800 else raw or out["rationale"]
                out["_model_meta"] = {"model": model_env}
                print(json.dumps(out, ensure_ascii=False))
                return
        except Exception as e:
            # On any Gemini call error, return fallback JSON with error details (non-sensitive)
            tb = traceback.format_exc()
            out = fake_output(data)
            out["error"] = str(e)
            out["traceback"] = tb.splitlines()[-6:]
            print(json.dumps(out, ensure_ascii=False))
            return
    else:
        # no GEMINI key set — fallback local output (keeps pipeline sane)
        out = fake_output(data)
        out["rationale"] = "GEMINI_API_KEY not set; returning placeholder."
        print(json.dumps(out, ensure_ascii=False))
        return

if __name__ == "__main__":
    main()
