import paramiko, os, sys

host = "94.103.167.51"
port = 3322
user = "agy"
pwd  = "Hushed202!"

local_video_path = r"c:\prognozv4\semantic-trend-poc\samples\input\videos\vid_0001.mp4"
remote_temp_path = "/tmp/vid_0001.mp4"
remote_final_path = "/srv/video-stage/accepted/vid_0001.mp4"

print(f"Connecting to {host}:{port} via SSH/SFTP...")
client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(host, port=port, username=user, password=pwd, timeout=30)

print(f"Uploading {local_video_path} to {remote_temp_path}...")
sftp = client.open_sftp()
sftp.put(local_video_path, remote_temp_path)
sftp.close()
print("Upload completed successfully!")

print("Moving file to final destination with sudo...")
# Use sudo to move the file to /srv/video-stage/accepted and set permissions
cmd = f"echo '{pwd}' | sudo -S mv {remote_temp_path} {remote_final_path} && echo '{pwd}' | sudo -S chmod 777 {remote_final_path}"
stdin, stdout, stderr = client.exec_command(cmd)
out = stdout.read().decode("utf-8", errors="replace")
err = stderr.read().decode("utf-8", errors="replace")

print("STDOUT:", out)
print("STDERR:", err)

# Check if the file is visible in /srv/video-stage/accepted
stdin, stdout, stderr = client.exec_command(f"ls -la {remote_final_path}")
print("Verification:", stdout.read().decode("utf-8"))

client.close()
