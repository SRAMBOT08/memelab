#!/usr/bin/env python
# test_pipeline.py - Direct test for the memelab pipeline
import json
import requests
import sys

def test_direct_ingest():
    """Test the ingest service directly with a POST request"""
    url = "http://127.0.0.1:5000/ingest"
    payload = {
        "user": "tester",
        "prompt": "Create a funny meme about coding bugs",
        "tone": "sarcastic",
        "meta": {"test": True}
    }
    
    print(f"Sending test request to {url}")
    print(f"Payload: {json.dumps(payload, indent=2)}")
    
    try:
        response = requests.post(url, json=payload, timeout=30)
        print(f"Status code: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            print("Response:")
            print(json.dumps(result, indent=2))
            return True
        else:
            print(f"Error: {response.text}")
            return False
    except Exception as e:
        print(f"Request failed: {e}")
        return False

def test_direct_script():
    """Test run_prompt_sim.py directly with stdin input"""
    import subprocess
    
    payload = {
        "user": "direct_tester",
        "prompt": "Test the script directly",
        "tone": "neutral"
    }
    
    print("Testing run_prompt_sim.py directly")
    input_json = json.dumps(payload)
    
    try:
        proc = subprocess.run(
            ["python", "run_prompt_sim.py"],
            input=input_json.encode("utf-8"),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=30
        )
        
        print(f"Exit code: {proc.returncode}")
        print(f"Stderr: {proc.stderr.decode('utf-8')}")
        print(f"Stdout: {proc.stdout.decode('utf-8')}")
        
        return proc.returncode == 0
    except Exception as e:
        print(f"Script test failed: {e}")
        return False

if __name__ == "__main__":
    print("=== MEMELAB PIPELINE TEST ===")
    
    if len(sys.argv) > 1 and sys.argv[1] == "--script-only":
        success = test_direct_script()
    else:
        success = test_direct_ingest()
    
    if success:
        print("\n✅ Test completed successfully")
        sys.exit(0)
    else:
        print("\n❌ Test failed")
        sys.exit(1)