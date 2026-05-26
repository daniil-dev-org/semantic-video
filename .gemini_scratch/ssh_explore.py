import paramiko, sys, os
os.environ["PYTHONIOENCODING"] = "utf-8"

host = "94.103.167.51"
port = 3322
user = "agy"
pwd  = "Hushed202!"

commands = sys.argv[1:] if len(sys.argv) > 1 else ["ls -la"]

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(host, port=port, username=user, password=pwd, timeout=15)

for cmd in commands:
    sudo_cmd = f"echo '{pwd}' | sudo -S bash -c '{cmd}'"
    print(f"\n>>> {cmd}", flush=True)
    stdin, stdout, stderr = client.exec_command(sudo_cmd, timeout=300)
    out = stdout.read().decode("utf-8", errors="replace")
    err = stderr.read().decode("utf-8", errors="replace")
    err_lines = [l for l in err.strip().split('\n') if l and '[sudo]' not in l and 'password' not in l.lower()]
    if out:
        # Safe print: replace non-printable chars
        sys.stdout.buffer.write(out.encode("utf-8", errors="replace"))
        sys.stdout.buffer.write(b"\n")
        sys.stdout.buffer.flush()
    if err_lines:
        msg = "[stderr] " + "\n".join(err_lines)
        sys.stdout.buffer.write(msg.encode("utf-8", errors="replace"))
        sys.stdout.buffer.write(b"\n")
        sys.stdout.buffer.flush()

client.close()
