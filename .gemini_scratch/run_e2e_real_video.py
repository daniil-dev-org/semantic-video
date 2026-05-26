import paramiko, json, sys, time

host = "94.103.167.51"
port = 3322
user = "agy"
pwd  = "Hushed202!"

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(host, port=port, username=user, password=pwd, timeout=15)

# 1. Trigger the job via local API
job_payload = {
    "input_path": "storage/uploads/accepted/vid_0001.mp4",
    "profile": "light_ab_test",
    "variants": 3,
    "extract_features": True,
    "generate_proxy": True
}

payload_str = json.dumps(job_payload).replace('"', '\\"')
cmd_post = f'curl -s -X POST -H "Content-Type: application/json" -d "{payload_str}" http://127.0.0.1:8096/api/jobs'

print(">>> POST /api/jobs with payload:", job_payload)
stdin, stdout, stderr = client.exec_command(cmd_post, timeout=15)
res_post = stdout.read().decode("utf-8", errors="replace")

try:
    job_data = json.loads(res_post)
    print("API Response:", json.dumps(job_data, indent=2, ensure_ascii=False))
    job_id = job_data["job_id"]
except Exception as e:
    print("Failed to parse POST response:", res_post)
    print("Error:", e)
    client.close()
    sys.exit(1)

# 2. Poll job status
print(f"\nMonitoring job {job_id}...")
start_time = time.time()
status = "QUEUED"

while status not in ["DONE", "FAILED", "CANCELLED"]:
    time.sleep(3)
    cmd_get = f'curl -s http://127.0.0.1:8096/api/jobs/{job_id}'
    stdin, stdout, stderr = client.exec_command(cmd_get, timeout=15)
    res_get = stdout.read().decode("utf-8", errors="replace")
    
    try:
        status_data = json.loads(res_get)
        status = status_data.get("status", "UNKNOWN")
        progress = status_data.get("progress", 0.0)
        elapsed = time.time() - start_time
        print(f"[{elapsed:.1f}s] Status: {status} | Progress: {progress}%", flush=True)
        if status_data.get("error_message"):
            print("ERROR DETAILS:", status_data["error_message"])
    except Exception as e:
        print("Failed to parse GET response:", res_get)
        print("Error:", e)

# 3. Retrieve outputs
if status == "DONE":
    print("\nJob completed successfully! Fetching outputs...")
    cmd_outputs = f'curl -s http://127.0.0.1:8096/api/jobs/{job_id}/outputs'
    stdin, stdout, stderr = client.exec_command(cmd_outputs, timeout=15)
    res_outputs = stdout.read().decode("utf-8", errors="replace")
    try:
        outputs = json.loads(res_outputs)
        print("\n=== GENERATED OUTPUTS ===")
        print(json.dumps(outputs, indent=2, ensure_ascii=False))
    except Exception as e:
        print("Failed to parse outputs response:", res_outputs)
        
    print("\nFetching sidecar metadata metrics...")
    cmd_sidecar = f'curl -s http://127.0.0.1:8096/api/jobs/{job_id}/sidecar'
    stdin, stdout, stderr = client.exec_command(cmd_sidecar, timeout=15)
    res_sidecar = stdout.read().decode("utf-8", errors="replace")
    try:
        sidecar = json.loads(res_sidecar)
        print("\n=== SIDECAR METADATA (SAMPLE) ===")
        # Print a small part of the sidecar
        print("Video Probed Dimensions:", sidecar.get("original_metadata", {}).get("width"), "x", sidecar.get("original_metadata", {}).get("height"))
        print("Detected Features Count:", len(sidecar.get("frame_features", [])))
        if sidecar.get("frame_features"):
            print("First frame feature vector:", sidecar["frame_features"][0])
    except Exception as e:
        print("Failed to parse sidecar response:", res_sidecar[:500])

client.close()
