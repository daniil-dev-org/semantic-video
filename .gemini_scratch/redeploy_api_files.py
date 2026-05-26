import paramiko, os, sys

host = "94.103.167.51"
port = 3322
user = "agy"
pwd  = "Hushed202!"

files_to_upload = {
    r"c:\prognozv4\semantic-trend-poc\app\api\routes_jobs.py": "routes_jobs.py",
    r"c:\prognozv4\semantic-trend-poc\app\api\main.py": "main.py",
    r"c:\prognozv4\semantic-trend-poc\app\api\index.html": "index.html"
}

print(f"Connecting to {host}:{port} via SSH/SFTP...")
client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(host, port=port, username=user, password=pwd, timeout=30)

sftp = client.open_sftp()
for local, name in files_to_upload.items():
    tmp_path = f"/tmp/{name}"
    print(f"Uploading {local} to temporary path {tmp_path}...")
    sftp.put(local, tmp_path)
sftp.close()
print("All files uploaded to /tmp successfully!")

def run_sudo_cmd(cmd):
    print(f"\n>>> {cmd}")
    sudo_cmd = f"echo '{pwd}' | sudo -S bash -c '{cmd}'"
    stdin, stdout, stderr = client.exec_command(sudo_cmd, timeout=300)
    out = stdout.read().decode("utf-8", errors="replace")
    err = stderr.read().decode("utf-8", errors="replace")
    if out:
        sys.stdout.buffer.write(out.encode("utf-8", errors="replace"))
        sys.stdout.buffer.write(b"\n")
    if err:
        err_lines = [l for l in err.strip().split('\n') if l and '[sudo]' not in l and 'password' not in l.lower()]
        if err_lines:
            msg = "[stderr] " + "\n".join(err_lines)
            sys.stdout.buffer.write(msg.encode("utf-8", errors="replace"))
            sys.stdout.buffer.write(b"\n")
    sys.stdout.buffer.flush()

# Move files from /tmp to /home/lebowski/semantic-video/app/api/
for name in files_to_upload.values():
    run_sudo_cmd(f"mv /tmp/{name} /home/lebowski/semantic-video/app/api/{name} && chown lebowski:lebowski /home/lebowski/semantic-video/app/api/{name}")

print("\nFiles moved to destination with correct permissions!")

# Build the podman image
run_sudo_cmd("podman build -t localhost/semantic-video:latest /home/lebowski/semantic-video")

# Restart the service
run_sudo_cmd("systemctl restart semantic-video.service && systemctl status semantic-video.service --no-pager")

client.close()
print("\nRedeployment finished successfully!")
