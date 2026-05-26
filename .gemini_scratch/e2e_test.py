import paramiko, json, sys

host = "94.103.167.51"
port = 3322
user = "agy"
pwd  = "Hushed202!"

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(host, port=port, username=user, password=pwd, timeout=15)

# Check job status
cmd1 = 'curl -s http://127.0.0.1:8096/api/jobs/2026-05-26-001'
print(">>> GET /api/jobs/2026-05-26-001")
stdin, stdout, stderr = client.exec_command(cmd1, timeout=15)
out = stdout.read().decode("utf-8", errors="replace")
try:
    data = json.loads(out)
    sys.stdout.buffer.write(json.dumps(data, indent=2, ensure_ascii=False).encode("utf-8"))
except:
    sys.stdout.buffer.write(out.encode("utf-8"))
sys.stdout.buffer.write(b"\n\n")
sys.stdout.buffer.flush()

# Check worker logs
print(">>> Container logs (last 20 lines)")
sudo_cmd = f"echo '{pwd}' | sudo -S podman logs --tail 20 semantic-video 2>&1"
stdin, stdout, stderr = client.exec_command(sudo_cmd, timeout=15)
out = stdout.read().decode("utf-8", errors="replace")
lines = [l for l in out.split('\n') if '[sudo]' not in l and 'password' not in l.lower()]
sys.stdout.buffer.write('\n'.join(lines).encode("utf-8", errors="replace"))
sys.stdout.buffer.write(b"\n")
sys.stdout.buffer.flush()

# Check via HTTPS
cmd3 = 'curl -s https://qstudio-api.duckdns.org/semantic/api/jobs/2026-05-26-001'
print("\n>>> GET /semantic/api/jobs/2026-05-26-001 (HTTPS)")
stdin, stdout, stderr = client.exec_command(cmd3, timeout=15)
out = stdout.read().decode("utf-8", errors="replace")
try:
    data = json.loads(out)
    sys.stdout.buffer.write(json.dumps(data, indent=2, ensure_ascii=False).encode("utf-8"))
except:
    sys.stdout.buffer.write(out.encode("utf-8"))
sys.stdout.buffer.write(b"\n")
sys.stdout.buffer.flush()

client.close()
