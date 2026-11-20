#!/usr/bin/env bash
set -Eeuo pipefail

if (( EUID != 0 )); then
    echo "Run with sudo: sudo bash deploy/bootstrap-lightsail.sh" >&2
    exit 2
fi

deploy_user="${SUDO_USER:-ubuntu}"
domain="${SIMPLE_WORD_DOMAIN:-moon.eta.pyhub.kr}"
user_home="$(getent passwd "$deploy_user" | cut -d: -f6)"
if [[ -z "$user_home" || ! -s "$user_home/.ssh/authorized_keys" ]]; then
    echo "Refusing to change SSH settings: $deploy_user has no authorized_keys" >&2
    exit 1
fi

export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y docker.io docker-compose-v2 unattended-upgrades fail2ban ufw certbot systemd-timesyncd

usermod -aG docker "$deploy_user"
install -d -m 0755 /etc/docker
daemon_changed="$(python3 - <<'PY'
import json
from pathlib import Path

path = Path("/etc/docker/daemon.json")
config = json.loads(path.read_text()) if path.exists() else {}
config["log-driver"] = "json-file"
config["log-opts"] = {**config.get("log-opts", {}), "max-size": "10m", "max-file": "3"}
contents = json.dumps(config, indent=2) + "\n"
changed = not path.exists() or path.read_text() != contents
if changed:
    path.write_text(contents)
print("yes" if changed else "no")
PY
)"
systemctl enable --now docker
if [[ "$daemon_changed" == yes ]]; then systemctl restart docker; fi

cat > /etc/apt/apt.conf.d/20auto-upgrades <<'EOF'
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
EOF
systemctl enable --now unattended-upgrades.service

install -d -m 0755 /etc/ssh/sshd_config.d
cat > /etc/ssh/sshd_config.d/00-simple-word-hardening.conf <<'EOF'
PubkeyAuthentication yes
PasswordAuthentication no
KbdInteractiveAuthentication no
PermitRootLogin no
EOF
sshd -t
systemctl reload ssh

desired_fail2ban="$(cat <<'EOF'
[sshd]
enabled = true
backend = systemd
maxretry = 5
findtime = 10m
bantime = 1h
EOF
)"
fail2ban_conf=/etc/fail2ban/jail.d/simple-word-sshd.local
if [[ ! -f "$fail2ban_conf" ]] || [[ "$(cat "$fail2ban_conf")" != "$desired_fail2ban" ]]; then
    printf '%s\n' "$desired_fail2ban" > "$fail2ban_conf"
    systemctl restart fail2ban
fi
systemctl enable --now fail2ban

ufw allow 22/tcp
ufw allow 80/tcp
ufw allow 443/tcp
ufw default deny incoming
ufw default allow outgoing
ufw --force enable

if ! swapon --noheadings --show=NAME | grep -qx /swapfile; then
    fallocate -l 2G /swapfile
    chmod 600 /swapfile
    mkswap /swapfile
    swapon /swapfile
fi
grep -qE '^/swapfile[[:space:]]' /etc/fstab || printf '/swapfile none swap sw 0 0\n' >> /etc/fstab

timedatectl set-timezone Australia/Sydney
timedatectl set-ntp true
systemctl enable --now systemd-timesyncd

docker_group="$(getent group docker | cut -d: -f1)"
install -d -o "$deploy_user" -g "$docker_group" -m 0750 /srv/simple-word
install -d -o "$deploy_user" -g "$docker_group" -m 0755 /srv/simple-word/models
install -d -o 10001 -g 10001 -m 0750 /srv/simple-word/logs

if ! certbot certificates 2>/dev/null | grep -Fq "Domains: $domain"; then
    if certbot certonly --standalone --non-interactive --agree-tos --register-unsafely-without-email \
        --preferred-challenges http -d "$domain"; then
        echo "Issued the TLS certificate for $domain."
    else
        echo "WARNING: TLS issuance failed; verify Lightsail inbound TCP/80 and rerun this script." >&2
    fi
fi

install -d -m 0755 /etc/letsencrypt/renewal-hooks/pre /etc/letsencrypt/renewal-hooks/post
cat > /etc/letsencrypt/renewal-hooks/pre/stop-simple-word-proxy <<'EOF'
#!/usr/bin/env bash
docker stop simpleword-proxy-1 >/dev/null 2>&1 || true
EOF
cat > /etc/letsencrypt/renewal-hooks/post/start-simple-word-proxy <<'EOF'
#!/usr/bin/env bash
docker start simpleword-proxy-1 >/dev/null 2>&1 || true
EOF
chmod 0755 /etc/letsencrypt/renewal-hooks/pre/stop-simple-word-proxy \
    /etc/letsencrypt/renewal-hooks/post/start-simple-word-proxy
systemctl enable --now certbot.timer

echo "Lightsail bootstrap complete for $deploy_user ($domain)."
