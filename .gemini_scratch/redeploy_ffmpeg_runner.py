import paramiko, os, sys

host = "94.103.167.51"
port = 3322
user = "agy"
pwd  = "Hushed202!"

local = r"c:\prognozv4\semantic-trend-poc\app\video\ffmpeg_runner.py"
remote_tmp = "/tmp/ffmpeg_runner.py"
remote_final = "/home/lebowski/semantic-video/app/video/ffmpeg_runner.py"

print(f"Connecting to {host}:{port} via SSH/SFTP...")
client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(host, port=port, username=user, password=pwd, timeout=30)

sftp = client.open_sftp()
print(f"Uploading {local} to temporary path {remote_tmp}...")
sftp.put(local, remote_tmp)
sftp.close()
print("Uploaded successfully!")

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

# Move file and chown
run_sudo_cmd(f"mv {remote_tmp} {remote_final} && chown lebowski:lebowski {remote_final}")

# Rebuild and restart
run_sudo_cmd("podman build -t localhost/semantic-video:latest /home/lebowski/semantic-video")
run_sudo_cmd("systemctl restart semantic-video.service && systemctl status semantic-video.service --no-pager")

client.close()
print("\nFFmpeg runner redeployment completed successfully!")
