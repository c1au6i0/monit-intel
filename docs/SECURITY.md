# Security

## Password Storage & Hashing

### Chat UI Credentials

Passwords are securely stored using industry-standard hashing:

- **Algorithm:** PBKDF2-SHA256
- **Iterations:** 100,000 (slow by design to resist brute-force)
- **Salt:** Random 32-character hex salt per password
- **Storage:** SQLite `monit_history.db`, `chat_credentials` table
- **Plain text:** Never stored - only cryptographic hashes

**Database Schema:**
```sql
CREATE TABLE chat_credentials (
    id INTEGER PRIMARY KEY,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,      -- PBKDF2-SHA256 hex-encoded
    salt TEXT NOT NULL,                -- Random hex salt per password
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

**Verify passwords are hashed:**
```bash
pixi run python << 'EOF'
import sqlite3
conn = sqlite3.connect("monit_history.db")
cursor = conn.cursor()
cursor.execute("SELECT username, password_hash, salt FROM chat_credentials")
for row in cursor.fetchall():
    username, hash_val, salt = row
    print(f"User: {username}")
    print(f"  Hash: {hash_val[:32]}... (64 chars total)")
    print(f"  Salt: {salt[:16]}... (32 chars total)")
conn.close()
EOF
```

### Monit API Credentials

Credentials for Monit XML API authentication:

- **Storage:** Systemd env files (production) or `.env` (development)
- **Hashing:** Plain text (systemd requires plaintext to authenticate to Monit)
- **File permissions:** `chmod 600` (root-only for production)
- **Git:** Not in repo (`.env` in `.gitignore`)

## API Security

### Authentication

- **HTTP Basic Auth:** All REST endpoints require valid chat credentials
    - Protected endpoints: `/health`, `/status`, `/analyze`, `/history`, `/logs/{service}`, all `/mother/*`
- **WebSocket Auth:** First message must contain username/password
- **Per-message verification:** Each message validates against database

### Session Management

- **Timeout:** 30 minutes of inactivity
- **Activity reset:** Any message resets the timer
- **Logout:** Manual logout button clears session

### Input Validation

- **Read-only operations:** Agent cannot execute destructive commands
- **Command whitelist:** Only safe actions are whitelisted
- **Scoped logs:** Only reads paths from Log Registry
- **Context limits:** Per-service max_lines prevents VRAM overflow

### TLS/HTTPS

- **Status:** HTTP only in development
- **Production:** Run behind reverse proxy (nginx) with TLS
- **Example:**
  ```nginx
  server {
      listen 443 ssl http2;
      server_name monit-intel.example.com;
      ssl_certificate /path/to/cert.pem;
      ssl_certificate_key /path/to/key.pem;
      
      location / {
          proxy_pass http://localhost:8000;
          proxy_set_header Host $host;
          proxy_set_header X-Real-IP $remote_addr;
      }
      
      location /ws/chat {
          proxy_pass http://localhost:8000;
          proxy_http_version 1.1;
          proxy_set_header Upgrade $http_upgrade;
          proxy_set_header Connection "upgrade";
      }
  }
  ```

## File Permissions

### Database
```bash
-rw-r--r-- 1 root root monit_history.db
# World-readable for backups
# For strict local-only access: chmod 600
```

### Systemd Environment Files
```bash
-rw------- 1 root root /etc/systemd/system/monit-intel-agent.service.d/env.conf
-rw------- 1 root root /etc/systemd/system/monit-intel-ingest.service.d/env.conf
# Root-only read/write
```

### Project Folder
```bash
drwxr-xr-x 1 user group monit-intel/
# World-readable (no secrets in files)
```

## Recommendations

### Initial Setup

1. **Change default passwords immediately** after setup
2. **Use strong passwords** - 20+ characters, mix of upper/lower/numbers/symbols
3. **Document credentials** - Store in password manager (Bitwarden, 1Password, etc.)

### Runtime Security

1. **Network access** - Run on isolated subnet or behind VPN
2. **Firewall rules** - Allow port 8000 only from trusted networks
3. **Monitor logs** - Check for failed login attempts
   ```bash
   grep "401\|Invalid credentials" /var/log/monit-intel-agent.log
   ```
4. **Regular restarts** - Periodically restart service for clean state

### Ongoing Maintenance

1. **Password rotation** - Change chat credentials quarterly
2. **Audit access** - Review who has access to the agent
3. **TLS certificates** - Renew before expiration
4. **Dependencies** - Keep Pixi packages updated (`pixi update`)

## Implementation Details

### Password Hashing Function

```python
import hashlib
import secrets

def hash_password(password: str, salt: str = None) -> tuple:
    """Hash password with PBKDF2-SHA256."""
    if salt is None:
        salt = secrets.token_hex(16)  # 32-char hex = 16 bytes
    
    hashed = hashlib.pbkdf2_hmac(
        'sha256',
        password.encode('utf-8'),
        salt.encode('utf-8'),
        100000  # iterations
    )
    return hashed.hex(), salt
```

### Verification Function

Password verification is implemented in constant time using `secrets.compare_digest()` to mitigate timing attacks:

```python
import secrets

def verify_password(password: str, stored_hash: str, salt: str) -> bool:
    """Constant-time password verification."""
    hashed, _ = hash_password(password, salt)
    return secrets.compare_digest(hashed, stored_hash)
```

## Threat Model

### What We Protect Against

✅ **Plaintext password theft** - Passwords are hashed with salt
✅ **Rainbow table attacks** - Unique salt per password
✅ **Brute-force attacks** - 100,000 iterations make cracking slow
✅ **Unauthorized API access** - All endpoints require authentication
✅ **Session hijacking** - 30-minute timeout + activity reset
✅ **Destructive commands** - Agent only executes whitelisted safe actions

### What We Don't Protect Against

⚠️ **Database theft** - If attacker gets monit_history.db, can attempt offline password cracking
⚠️ **Network eavesdropping** - No HTTPS in default setup (use reverse proxy)
⚠️ **System compromise** - If server is compromised, all credentials are accessible
⚠️ **Weak passwords** - User responsibility to choose strong passwords
✅ **Timing attacks** - Mitigated using constant-time comparison

## Audit Trail

All executed actions are logged to `action_audit_log` table:

```sql
CREATE TABLE action_audit_log (
    id INTEGER PRIMARY KEY,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    action TEXT,
    service TEXT,
    command TEXT,
    exit_code INTEGER,
    output TEXT,
    approved_by TEXT
);
```

Review audit logs:
```bash
pixi run python << 'EOF'
import sqlite3
conn = sqlite3.connect("monit_history.db")
cursor = conn.cursor()
cursor.execute(
    "SELECT timestamp, action, service, exit_code FROM action_audit_log ORDER BY timestamp DESC LIMIT 50"
)
for row in cursor.fetchall():
    print(row)
conn.close()
EOF
```

## Questions?

- **How do I change a password?** Run: `pixi run python -m monit_intel.chat_auth username newpassword`
- **How do I add multiple users?** Run the chat_auth command for each username
- **Can I use HTTPS?** Yes, run behind nginx with SSL certificates
- **What if I forget a password?** Delete the row from chat_credentials and recreate it
- **Is the database encrypted?** No - encrypt the disk/filesystem instead

