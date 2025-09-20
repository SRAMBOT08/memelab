# pathway_processor.py
"""
pathway_processor.process(payload) -> dict

Behavior:
- If a local runner script exists (checked in CWD or via PATHWAY_RUNNER env),
  the module will attempt to call it with the input JSON on stdin and parse
  JSON printed to stdout.
- If calling the runner fails or no valid JSON can be found in stdout,
  the module returns a deterministic simulated response so the rest of the
  pipeline can be exercised reliably.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
from typing import Any, Dict, List, Optional
from pathlib import Path

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Allow timeout to be configured via env var (seconds)
_DEFAULT_TIMEOUT = 30
try:
    PATHWAY_RUNNER_TIMEOUT = int(os.environ.get("PATHWAY_RUNNER_TIMEOUT", _DEFAULT_TIMEOUT))
except Exception:
    PATHWAY_RUNNER_TIMEOUT = _DEFAULT_TIMEOUT

# Candidate runner scripts (checked in order)
_DEFAULT_RUNNERS = ("run_prompt_sim.py", "run_trae_tests.py", "run_trac.py")


def _simulate(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Return a fake but deterministic 'pathway' result for testing."""
    prompt = payload.get("prompt", "")
    user = payload.get("user", "unknown")
    tone = payload.get("tone", "neutral")
    captions = [
        f"{user} tries to sue an AI — but the AI replies with a paperwork meme.",
        f"Caption riff: '{(prompt[:40] + '...') if len(prompt) > 40 else prompt}' (tone: {tone})"
    ]
    rationale = f"Simulated rationale: created {len(captions)} captions from user prompt ({len(prompt)} chars)."
    return {
        "captions": captions,
        "rationale": rationale,
        "meta": {"simulated": True}
    }


def _find_runner(candidate_list: Optional[List[str]] = None) -> Optional[Path]:
    """
    Determine which runner script to call.
    - Checks PATHWAY_RUNNER env var first (can be path or script name)
    - Then checks candidate_list in current working directory.
    Returns a Path if a file exists and is readable, otherwise None.
    """
    candidate_list = candidate_list or list(_DEFAULT_RUNNERS)

    # 1) explicit env override
    env_runner = os.environ.get("PATHWAY_RUNNER")
    if env_runner:
        p = Path(env_runner)
        if not p.is_absolute():
            # try cwd
            p = (Path.cwd() / env_runner).resolve()
        if p.exists() and p.is_file():
            logger.info("Using runner from PATHWAY_RUNNER env: %s", str(p))
            return p
        else:
            logger.warning("PATHWAY_RUNNER is set but points to missing file: %s", env_runner)

    # 2) check candidates in cwd
    for name in candidate_list:
        p = (Path.cwd() / name)
        if p.exists() and p.is_file():
            logger.info("Found runner script: %s", str(p))
            return p

    logger.info("No runner script found among candidates: %s", candidate_list)
    return None


def _extract_json_from_output(stdout: str) -> Optional[Dict[str, Any]]:
    """
    Attempt to extract the last JSON object in stdout.
    Accepts multi-line stdout where logs may be present; we iterate lines
    from the end and attempt json.loads on each line until successful.
    """
    if not stdout:
        return None

    # Strip leading/trailing whitespace and split into non-empty lines
    lines = [line.strip() for line in stdout.splitlines() if line.strip()]
    # Try parsing full stdout first (some runners print only JSON)
    try:
        return json.loads(stdout)
    except Exception:
        pass

    # Try each line from bottom to top
    for line in reversed(lines):
        try:
            parsed = json.loads(line)
            logger.info("Extracted JSON from runner output (line preview): %s", (line[:200] + '...') if len(line) > 200 else line)
            return parsed
        except Exception:
            # not JSON; continue
            continue
    return None


def _call_runner(payload: Dict[str, Any], runner_path: Path) -> Dict[str, Any]:
    """
    Call the runner script with JSON on stdin. Returns parsed JSON result.
    If runner fails or no JSON is found, raises RuntimeError.
    """
    input_json = json.dumps(payload, ensure_ascii=False)
    logger.info("Calling runner %s with payload keys=%s (timeout=%ss)", str(runner_path), list(payload.keys()), PATHWAY_RUNNER_TIMEOUT)

    # Use same Python interpreter
    cmd = [sys.executable, str(runner_path)]
    try:
        proc = subprocess.run(
            cmd,
            input=input_json.encode("utf-8"),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=PATHWAY_RUNNER_TIMEOUT
        )
    except subprocess.TimeoutExpired as te:
        logger.exception("Runner timed out after %s seconds: %s", PATHWAY_RUNNER_TIMEOUT, te)
        raise RuntimeError("Runner timed out") from te
    except Exception as e:
        logger.exception("Failed to run runner: %s", e)
        raise RuntimeError("Failed to spawn runner") from e

    stdout = proc.stdout.decode("utf-8", errors="replace").strip()
    stderr = proc.stderr.decode("utf-8", errors="replace").strip()

    # Log short previews
    logger.info("Runner exitcode=%s; stdout length=%d; stderr length=%d", proc.returncode, len(stdout), len(stderr))
    if stdout:
        logger.debug("Runner stdout (preview): %s", (stdout[:1000] + "...") if len(stdout) > 1000 else stdout)
    if stderr:
        logger.warning("Runner stderr (preview): %s", (stderr[:1000] + "...") if len(stderr) > 1000 else stderr)

    # If non-zero exit, still attempt to parse stdout for JSON before failing hard
    if proc.returncode != 0:
        logger.warning("Runner returned non-zero exit code %s; attempting to extract JSON from stdout before failing", proc.returncode)

    parsed = _extract_json_from_output(stdout)
    if parsed is None:
        logger.error("Could not parse JSON from runner output.")
        raise RuntimeError("Runner produced no valid JSON output")

    if not isinstance(parsed, dict):
        logger.error("Runner JSON is not an object/dict.")
        raise RuntimeError("Runner JSON is not a dict")

    return parsed


def process(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Main entrypoint used by Flask ingest handler.
    Tries to call a real runner, otherwise falls back to simulation.
    Always returns a dictionary (either runner result or simulated dict).
    """
    logger.info("pathway_processor.process called (payload keys=%s)", list(payload.keys()))

    runner_path = _find_runner()

    if runner_path:
        try:
            result = _call_runner(payload, runner_path)
            # enrich meta safely
            if isinstance(result, dict):
                meta = result.setdefault("meta", {})
                meta.setdefault("runner", runner_path.name)
                meta.setdefault("simulated", False)
                logger.info("Runner result accepted and returned.")
                return result
        except Exception as e:
            # Log but don't raise — fall back to simulated response
            logger.exception("Runner invocation failed; falling back to simulated response: %s", e)

    # No runner found or runner failed: return simulated output
    logger.info("Returning simulated response.")
    simulated = _simulate(payload)
    # ensure meta includes hint it is simulated
    simulated.setdefault("meta", {}).update({"runner": None, "simulated": True})
    return simulated


# If invoked as script, allow quick local test
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    sample = {"user": "tester", "prompt": "Make a funny meme about AI art lawsuits", "tone": "deadpan"}
    print(json.dumps(process(sample), indent=2, ensure_ascii=False))
