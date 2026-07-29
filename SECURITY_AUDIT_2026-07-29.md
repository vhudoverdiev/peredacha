# Security audit, 2026-07-29

Scope: Ubuntu VDS on Selectel, Python/Flask, PostgreSQL, Nginx, Gunicorn, Let's Encrypt.

Limitation: direct SSH audit was not possible from this workspace. `ssh -o BatchMode=yes peredacha-server "hostname; id; uname -a"` returned `Permission denied (publickey,password)`. Public network checks and full local project audit were completed.

## Executive findings

1. Critical: PostgreSQL is reachable from the internet on `135.106.139.229:5432`.
   Why dangerous: if PostgreSQL has a weak password, old CVE, or permissive `pg_hba.conf`, the database can be attacked directly.
   Fix:
   ```bash
   sudo ss -tulpn | grep ':5432'
   sudo sed -i "s/^#\?listen_addresses.*/listen_addresses = '127.0.0.1'/" /etc/postgresql/*/main/postgresql.conf
   sudo cp /etc/postgresql/*/main/pg_hba.conf /etc/postgresql/pg_hba.conf.bak.$(date +%F-%H%M)
   sudo awk 'BEGIN{print "local all all peer\nhost all all 127.0.0.1/32 scram-sha-256\nhost all all ::1/128 scram-sha-256"}' | sudo tee /etc/postgresql/*/main/pg_hba.conf
   sudo systemctl restart postgresql
   sudo ufw deny 5432/tcp
   ```

2. High: ports `5000` and `8080` are reachable from the internet.
   Why dangerous: these ports often expose direct Flask/dev/Gunicorn/admin services outside Nginx, bypassing TLS, rate limits, logging, and headers.
   Fix:
   ```bash
   sudo ss -tulpn | egrep ':(5000|8080)\b'
   sudo systemctl disable --now <unexpected-service>
   sudo ufw deny 5000/tcp
   sudo ufw deny 8080/tcp
   ```

3. Medium: SSH is exposed on `22` and the configured alias uses `root`.
   Why dangerous: direct root SSH increases blast radius after key/password compromise.
   Fix:
   ```bash
   sudo adduser deploy
   sudo usermod -aG sudo deploy
   sudo install -d -m 700 -o deploy -g deploy /home/deploy/.ssh
   sudo cp /root/.ssh/authorized_keys /home/deploy/.ssh/authorized_keys
   sudo chown deploy:deploy /home/deploy/.ssh/authorized_keys
   sudo chmod 600 /home/deploy/.ssh/authorized_keys
   sudoedit /etc/ssh/sshd_config
   ```
   Recommended `sshd_config`:
   ```text
   PermitRootLogin no
   PasswordAuthentication no
   KbdInteractiveAuthentication no
   PubkeyAuthentication yes
   AllowUsers deploy
   MaxAuthTries 3
   LoginGraceTime 20
   X11Forwarding no
   AllowTcpForwarding no
   ```
   Apply:
   ```bash
   sudo sshd -t && sudo systemctl reload ssh
   ```

4. Medium: public Nginx responses reveal `Server: nginx/1.24.0 (Ubuntu)`.
   Why dangerous: version disclosure helps attackers pick known exploit chains.
   Fixed in repo config: `deploy/nginx-akvilon-peredacha.conf` now includes `server_tokens off`.
   Apply:
   ```bash
   sudo cp deploy/nginx-akvilon-peredacha.conf /etc/nginx/sites-available/peredacha.conf
   sudo nginx -t && sudo systemctl reload nginx
   ```

5. Medium: landing domain lacks HSTS and CSP in observed headers.
   Evidence: `https://akvilon-peredacha.ru/` returned XFO, nosniff and referrer policy, but no HSTS/CSP.
   Fixed in repo config: landing HTTPS server now adds HSTS and basic security headers.

6. Medium: application-side rate limiting is in-process.
   Why dangerous: with multiple Gunicorn workers, limits are per-process, not global.
   Mitigation added: Nginx rate-limit deploy snippet at `deploy/nginx-rate-limit.conf`.
   Better long-term fix: Redis-backed limiter such as Flask-Limiter.

7. Medium: Flask proxy headers were not explicitly trusted through `ProxyFix`.
   Why dangerous: audit logs and rate limits can use proxy IP instead of client IP; HTTPS detection can depend on workarounds.
   Fixed in code: `TRUSTED_PROXY_COUNT` and `ProxyFix` added.

8. Low: CSP still allows inline scripts/styles.
   Why dangerous: inline allowances reduce XSS resistance.
   Current state: user content is escaped and tests cover XSS, but CSP hardening should be gradual because the UI has inline scripts/styles.

9. Low: Python code still uses `datetime.utcnow()` in several places.
   Why dangerous: not a direct security bug, but timezone ambiguity can hurt audit logs.
   Recommendation: migrate to timezone-aware UTC in a separate cleanup.

10. Unknown: backups, UFW/iptables, Fail2Ban, AppArmor, OS package CVEs, PostgreSQL roles, and real systemd status require SSH access.

## Changes made in this audit

- Added `ProxyFix` support in Flask, controlled by `TRUSTED_PROXY_COUNT`.
- Hardened `.env.example` for production defaults.
- Replaced the project Nginx deploy template with HTTPS redirect, TLS blocks, HSTS, upload limits, static file hardening, and rate limit usage.
- Added `deploy/nginx-rate-limit.conf` for `/etc/nginx/conf.d/`.
- Hardened Gunicorn systemd unit with `NoNewPrivileges`, `PrivateTmp`, filesystem protection, `UMask`, and resource limits.
- Added security regression tests for the changes.

## Verification performed

```text
Public HTTPS CRM: 200 OK, Secure/HttpOnly/SameSite cookie, HSTS present.
Public HTTP CRM: 301 redirect to HTTPS.
Public HTTPS landing: 200 OK, server version disclosed, HSTS missing before deploy config fix.
TLS <= 1.1: handshake rejected.
TLS 1.2: accepted.
Open public ports observed: 22, 80, 443, 5432, 5000, 8080.
SSH batch audit: denied, no server-side commands executed.
Python dependency audit: pip-audit found no known vulnerabilities.
pip check: no broken requirements.
JS syntax: script.js OK, service-worker.js OK.
Python tests: 497 tests OK.
```

## Recommended deploy sequence

```bash
cd /opt/peredacha
git pull

sudo cp deploy/nginx-rate-limit.conf /etc/nginx/conf.d/peredacha-rate-limit.conf
sudo cp deploy/nginx-akvilon-peredacha.conf /etc/nginx/sites-available/peredacha.conf
sudo ln -sf /etc/nginx/sites-available/peredacha.conf /etc/nginx/sites-enabled/peredacha.conf
sudo nginx -t && sudo systemctl reload nginx

sudo cp deploy/gunicorn.service /etc/systemd/system/gunicorn.service
sudo cp deploy/gunicorn.socket /etc/systemd/system/gunicorn.socket
sudo systemctl daemon-reload
sudo systemctl restart gunicorn.socket gunicorn.service
sudo systemctl status gunicorn.service --no-pager
```

Firewall baseline:
```bash
sudo apt update
sudo apt install -y ufw fail2ban unattended-upgrades
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw deny 5432/tcp
sudo ufw deny 5000/tcp
sudo ufw deny 8080/tcp
sudo ufw enable
sudo ufw status verbose
```

Fail2Ban baseline:
```ini
# /etc/fail2ban/jail.d/sshd.local
[sshd]
enabled = true
port = ssh
maxretry = 3
findtime = 10m
bantime = 1h
```

```bash
sudo systemctl enable --now fail2ban
sudo fail2ban-client status sshd
```

Automatic security updates:
```bash
sudo dpkg-reconfigure -plow unattended-upgrades
sudo systemctl status unattended-upgrades --no-pager
```

PostgreSQL least privilege:
```sql
CREATE ROLE peredacha_app LOGIN PASSWORD 'replace-with-strong-password';
CREATE DATABASE peredacha OWNER peredacha_app;
REVOKE ALL ON DATABASE peredacha FROM PUBLIC;
GRANT CONNECT ON DATABASE peredacha TO peredacha_app;
```

Backups:
```bash
sudo install -d -m 700 -o postgres -g postgres /var/backups/peredacha/postgres
sudo -u postgres pg_dump -Fc peredacha > /var/backups/peredacha/postgres/peredacha-$(date +%F-%H%M).dump
sudo -u postgres pg_restore --list /var/backups/peredacha/postgres/latest.dump >/dev/null
```

Logs to review:
```bash
sudo journalctl -u ssh --since "7 days ago" --no-pager
sudo journalctl -u gunicorn --since "7 days ago" --no-pager
sudo tail -n 300 /var/log/nginx/access.log
sudo tail -n 300 /var/log/nginx/error.log
sudo grep -Ei "failed|invalid|accepted|sudo|session" /var/log/auth.log | tail -n 300
```

## 100-point checklist

1. ❌ PostgreSQL port `5432` closed from internet.
2. ❌ Port `5000` closed from internet.
3. ❌ Port `8080` closed from internet.
4. ⚠ SSH port exposed only intentionally.
5. ❌ Root SSH disabled.
6. ❌ SSH password login disabled.
7. ⚠ SSH `MaxAuthTries` limited.
8. ⚠ SSH `AllowUsers` configured.
9. ⚠ Deploy user exists.
10. ⚠ Deploy user has minimal sudo.
11. ⚠ Root login audited.
12. ⚠ `sudo` group reviewed.
13. ⚠ No shared admin accounts.
14. ⚠ UFW enabled.
15. ⚠ Default incoming firewall policy is deny.
16. ⚠ Only 80/443/SSH allowed publicly.
17. ⚠ iptables/nftables rules reviewed.
18. ⚠ Fail2Ban installed.
19. ⚠ Fail2Ban sshd jail enabled.
20. ⚠ Fail2Ban Nginx jails considered.
21. ⚠ AppArmor status checked.
22. ⚠ OS packages updated.
23. ⚠ Unattended security upgrades enabled.
24. ⚠ Reboot-required monitored.
25. ⚠ Selectel firewall/security groups checked.
26. ✅ HTTP redirects to HTTPS on CRM.
27. ✅ TLS 1.1 rejected by CRM.
28. ✅ TLS 1.2 accepted by CRM.
29. ⚠ TLS 1.3 should be verified from server.
30. ❌ Nginx version disclosure still visible on live server.
31. ✅ `server_tokens off` added to deploy config.
32. ✅ HSTS present on CRM.
33. ❌ HSTS missing on live landing domain.
34. ✅ HSTS added to landing deploy config.
35. ✅ `X-Frame-Options` present.
36. ✅ `X-Content-Type-Options` present.
37. ✅ Referrer Policy present.
38. ✅ Permissions Policy present on CRM.
39. ⚠ CSP present but allows inline scripts/styles.
40. ✅ Dynamic CRM pages are no-store.
41. ✅ Static cache configured.
42. ✅ Nginx upload limit configured.
43. ✅ Nginx general rate limit configured in repo.
44. ✅ Nginx login rate limit configured in repo.
45. ⚠ Rate-limit config must be deployed to `/etc/nginx/conf.d`.
46. ✅ Gunicorn uses Unix socket in deploy config.
47. ✅ Gunicorn runs as `www-data`.
48. ✅ Gunicorn restart is enabled.
49. ✅ Gunicorn timeout is configured.
50. ✅ Gunicorn `NoNewPrivileges` added.
51. ✅ Gunicorn `PrivateTmp` added.
52. ✅ Gunicorn filesystem protection added.
53. ✅ Gunicorn resource limits added.
54. ✅ Flask DEBUG defaults off.
55. ✅ Production rejects missing/weak `SECRET_KEY`.
56. ✅ `.env` ignored by Git.
57. ✅ `.env.example` no longer suggests `change-me`.
58. ✅ Secure cookie flags are documented.
59. ✅ Session cookies are HttpOnly.
60. ✅ Remember cookies are HttpOnly.
61. ✅ SameSite is `Lax`.
62. ✅ CSRF protection enabled.
63. ✅ CSRF regression test exists.
64. ✅ Upload extension allow-list exists.
65. ✅ Upload magic-byte validation exists.
66. ✅ Upload max size exists.
67. ⚠ Uploaded files should be stored on non-executable mount if possible.
68. ✅ SQLAlchemy ORM is used for normal queries.
69. ✅ SQL injection regression test exists.
70. ✅ XSS escaping regression test exists.
71. ✅ IDOR read regression tests exist.
72. ✅ IDOR write/delete regression tests exist.
73. ✅ Role guards exist.
74. ✅ Current project access is checked in key routes.
75. ✅ Viewer write access is denied.
76. ✅ Worker route allow-list exists.
77. ✅ Verifier route allow-list exists.
78. ✅ Login attempt rate limit exists.
79. ✅ Account lockout exists.
80. ⚠ App rate limit should move to Redis for multi-worker production.
81. ✅ Login failure security events are logged.
82. ✅ Passwords are not written into security logs.
83. ✅ Session version revocation exists.
84. ⚠ 2FA exists but should be mandatory for admins.
85. ⚠ Admin password policy should be enforced at creation/update.
86. ⚠ CORS should stay disabled unless explicitly needed.
87. ✅ Public `/csrf-token` returns no-store token.
88. ⚠ Analytics CSRF exemption is limited but should stay monitored.
89. ⚠ PostgreSQL listening address must be verified over SSH.
90. ⚠ PostgreSQL users/privileges must be audited over SSH.
91. ⚠ PostgreSQL logging must be verified over SSH.
92. ⚠ PostgreSQL backups must be verified with restore.
93. ⚠ Nginx logs must be reviewed on server.
94. ⚠ Gunicorn logs must be reviewed on server.
95. ⚠ `auth.log` suspicious entries must be reviewed on server.
96. ⚠ Ubuntu package CVEs must be audited on server.
97. ✅ Python dependency audit found no known CVEs locally.
98. ✅ `pip check` found no broken dependencies.
99. ✅ Security regression tests pass.
100. ❌ Full server audit still requires working SSH access.
