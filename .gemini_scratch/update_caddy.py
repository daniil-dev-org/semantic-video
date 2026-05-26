import paramiko

host = "94.103.167.51"
port = 3322
user = "agy"
pwd  = "Hushed202!"

# Route /semantic/* to Python service, everything else to Go service
CADDYFILE = """(cors) {
    header {
        Access-Control-Allow-Origin *
        Access-Control-Allow-Methods "GET, POST, OPTIONS"
        Access-Control-Allow-Headers "*"
    }
}

vraqt.duckdns.org {
    reverse_proxy localhost:8090
}

vraqt-lampac.duckdns.org {
    reverse_proxy localhost:9118
    import cors
}

vraqt-parser.duckdns.org {
    reverse_proxy localhost:9117
    import cors
}

qstudio-api.duckdns.org {
    handle /semantic/* {
        uri strip_prefix /semantic
        reverse_proxy host.containers.internal:8096
        import cors
    }
    handle {
        reverse_proxy host.containers.internal:8095
    }
}

qstudio.duckdns.org {
    reverse_proxy host.containers.internal:8080

    header {
        Strict-Transport-Security "max-age=15552000;"
    }
}
"""

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(host, port=port, username=user, password=pwd, timeout=15)

def sudo_exec(cmd):
    full = f"echo '{pwd}' | sudo -S bash -c '{cmd}'"
    stdin, stdout, stderr = client.exec_command(full, timeout=30)
    return stdout.read().decode("utf-8", errors="replace"), stderr.read().decode("utf-8", errors="replace")

# Write via SFTP
sftp = client.open_sftp()
with sftp.open("/home/agy/Caddyfile.tmp", "w") as f:
    f.write(CADDYFILE)
sftp.close()
print("1. Wrote temp Caddyfile")

out, err = sudo_exec("cp /home/agy/Caddyfile.tmp /root/caddy_data/Caddyfile")
print("2. Copied to /root/caddy_data/")

out, err = sudo_exec("podman exec caddy caddy reload --config /etc/caddy/Caddyfile")
filtered_err = [l for l in err.split('\n') if l.strip() and '[sudo]' not in l and 'password' not in l.lower()]
print(f"3. Caddy reload")
for l in filtered_err:
    print(f"   {l}")

sudo_exec("rm -f /home/agy/Caddyfile.tmp")
client.close()
print("Done!")
