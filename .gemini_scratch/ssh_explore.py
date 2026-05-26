import paramiko, sys

host = "94.103.167.51"
port = 3322
user = "agy"
pwd  = "Hushed202!"

commands = sys.argv[1:] if len(sys.argv) > 1 else ["ls -la /home/lebowski/video-pipeline/"]

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(host, port=port, username=user, password=pwd, timeout=15)

for cmd in commands:
    # Wrap all commands with sudo using -S to pipe password via stdin
    sudo_cmd = f"echo '{pwd}' | sudo -S {cmd}"
    print(f"\n>>> {cmd}")
    stdin, stdout, stderr = client.exec_command(sudo_cmd, timeout=30)
    out = stdout.read().decode("utf-8", errors="replace")
    err = stderr.read().decode("utf-8", errors="replace")
    # Filter out sudo password prompt noise from stderr
    err_lines = [l for l in err.strip().split('\n') if l and '[sudo]' not in l and 'password' not in l.lower()]
    if out:
        print(out)
    if err_lines:
        print(f"[stderr] {chr(10).join(err_lines)}")

client.close()
