import paramiko

host = "94.103.167.51"
port = 3322
user = "agy"
pwd  = "Hushed202!"

UNIT_FILE = """[Unit]
Description=Semantic Video Processing Microservice
Wants=network-online.target
After=network-online.target nextcloud-redis.service video-pipeline.service

[Service]
Type=simple
Restart=always
RestartSec=5
ExecStartPre=-/usr/bin/podman stop semantic-video
ExecStartPre=-/usr/bin/podman rm semantic-video
ExecStart=/usr/bin/podman run --name semantic-video \\
    --cpus=1.0 --memory=2g \\
    -p 8096:8000 \\
    --network nextcloud-net \\
    -v /srv/video-stage:/app/storage/uploads:ro \\
    -v /srv/video-outputs:/app/storage/outputs:rw \\
    -v /srv/semantic-video-db:/app/storage:rw \\
    -v /opt/semantic-video/profiles:/app/profiles:ro \\
    -e THREAD_LIMIT=1 \\
    -e REDIS_ADDR=nextcloud-redis:6379 \\
    -e REDIS_STREAM_PROCESS=video:process \\
    -e JOB_TIMEOUT_SEC=600 \\
    localhost/semantic-video:latest
ExecStop=/usr/bin/podman stop semantic-video

[Install]
WantedBy=multi-user.target
"""

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(host, port=port, username=user, password=pwd, timeout=15)

def sudo_exec(cmd):
    full = f"echo '{pwd}' | sudo -S bash -c '{cmd}'"
    stdin, stdout, stderr = client.exec_command(full, timeout=30)
    return stdout.read().decode("utf-8", errors="replace"), stderr.read().decode("utf-8", errors="replace")

# Write unit file via SFTP
sftp = client.open_sftp()
with sftp.open("/home/agy/semantic-video.service", "w") as f:
    f.write(UNIT_FILE)
sftp.close()
print("1. Wrote unit file to /home/agy/semantic-video.service")

# Copy to systemd
out, err = sudo_exec("cp /home/agy/semantic-video.service /etc/systemd/system/semantic-video.service")
print("2. Copied to /etc/systemd/system/")

# Stop the manually-started container first
out, err = sudo_exec("podman stop semantic-video && podman rm semantic-video")
print(f"3. Stopped manual container: {out.strip()}")

# Reload systemd and enable
out, err = sudo_exec("systemctl daemon-reload")
print("4. systemctl daemon-reload done")

out, err = sudo_exec("systemctl enable --now semantic-video.service")
print(f"5. Enabled and started service")

import time
time.sleep(3)

out, err = sudo_exec("systemctl status semantic-video.service --no-pager")
print(f"6. Service status:\n{out}")

# Cleanup
sudo_exec("rm -f /home/agy/semantic-video.service")

client.close()
print("Done!")
