"""Server-side authentication, sessions, and audit logging for FloodAI."""
# ruff: noqa: E401, E701, E702
from __future__ import annotations
import hashlib, hmac, os, re, secrets, sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from fastapi import HTTPException, Request, status
ROOT=Path(__file__).resolve().parents[1]
DB_PATH=Path(os.getenv("FLOODAI_AUTH_DB",str(ROOT/"data"/"floodai_auth.sqlite3")))
SESSION_COOKIE="floodai_session"; SESSION_HOURS=int(os.getenv("FLOODAI_SESSION_HOURS","12")); PBKDF2_ROUNDS=310_000
EMAIL_RE=re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
def now_utc(): return datetime.now(timezone.utc)
def iso(dt=None): return (dt or now_utc()).isoformat()
def _connect():
    DB_PATH.parent.mkdir(parents=True,exist_ok=True); db=sqlite3.connect(DB_PATH,timeout=10)
    db.row_factory=sqlite3.Row; db.execute("PRAGMA foreign_keys=ON"); return db
def init_db():
    with _connect() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY AUTOINCREMENT,email TEXT NOT NULL UNIQUE COLLATE NOCASE,
        password_hash TEXT NOT NULL,role TEXT NOT NULL DEFAULT 'user' CHECK(role IN ('user','admin')),
        is_verified INTEGER NOT NULL DEFAULT 0,is_active INTEGER NOT NULL DEFAULT 1,alerts_enabled INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL,verification_token_hash TEXT,verification_expires_at TEXT);
        CREATE TABLE IF NOT EXISTS sessions(token_hash TEXT PRIMARY KEY,user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        created_at TEXT NOT NULL,expires_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS audit_logs(id INTEGER PRIMARY KEY AUTOINCREMENT,actor_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
        actor_email TEXT,action TEXT NOT NULL,target TEXT,outcome TEXT NOT NULL,details TEXT,created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS alert_dispatches(id INTEGER PRIMARY KEY AUTOINCREMENT,region_id TEXT NOT NULL,status TEXT NOT NULL,
        event_id TEXT NOT NULL,recipient_count INTEGER NOT NULL DEFAULT 0,created_at TEXT NOT NULL,UNIQUE(region_id,status,event_id));
        CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);
        CREATE INDEX IF NOT EXISTS idx_audit_created ON audit_logs(created_at);
        """)
    _bootstrap_admin()
def _password_hash(password,salt=None):
    salt=salt or secrets.token_bytes(16); digest=hashlib.pbkdf2_hmac("sha256",password.encode(),salt,PBKDF2_ROUNDS)
    return "pbkdf2_sha256$"+str(PBKDF2_ROUNDS)+"$"+salt.hex()+"$"+digest.hex()
def _verify_password(password,encoded):
    try:
        algorithm,rounds,salt_hex,expected=encoded.split("$",3)
        if algorithm!="pbkdf2_sha256": return False
        actual=hashlib.pbkdf2_hmac("sha256",password.encode(),bytes.fromhex(salt_hex),int(rounds)).hex()
        return hmac.compare_digest(actual,expected)
    except (ValueError,TypeError): return False
def validate_email(email):
    value=email.strip().lower()
    if len(value)>254 or not EMAIL_RE.fullmatch(value): raise HTTPException(422,"Enter a valid email address.")
    return value
def validate_password(password):
    if len(password)<10 or len(password)>128: raise HTTPException(422,"Password must contain between 10 and 128 characters.")
def _bootstrap_admin():
    email=os.getenv("FLOODAI_ADMIN_EMAIL","").strip().lower(); password=os.getenv("FLOODAI_ADMIN_PASSWORD","")
    if not email and not password: return
    if not email or not password: raise RuntimeError("Set both FLOODAI_ADMIN_EMAIL and FLOODAI_ADMIN_PASSWORD to provision the admin.")
    if not EMAIL_RE.fullmatch(email): raise RuntimeError("FLOODAI_ADMIN_EMAIL must be valid.")
    if len(password)<14: raise RuntimeError("FLOODAI_ADMIN_PASSWORD must contain at least 14 characters.")
    with _connect() as db:
        existing=db.execute("SELECT id,role FROM users WHERE email=?",(email,)).fetchone()
        if existing:
            if existing["role"]!="admin": raise RuntimeError("Configured admin email already belongs to a regular account.")
            db.execute("UPDATE users SET password_hash=?,is_verified=1,is_active=1 WHERE id=?",(_password_hash(password),existing["id"]))
        else:
            another_admin=db.execute("SELECT email FROM users WHERE role='admin' LIMIT 1").fetchone()
            if another_admin:
                raise RuntimeError("FloodAI permits one platform admin; configured email does not match the provisioned admin.")
            db.execute("INSERT INTO users(email,password_hash,role,is_verified,is_active,alerts_enabled,created_at) VALUES(?,?,'admin',1,1,0,?)",(email,_password_hash(password),iso()))
def create_user(email,password):
    email=validate_email(email); validate_password(password); token=secrets.token_urlsafe(32)
    expiry=iso(now_utc()+timedelta(hours=24)); hashed=hashlib.sha256(token.encode()).hexdigest()
    try:
        with _connect() as db:
            cur=db.execute("""INSERT INTO users(email,password_hash,role,is_verified,is_active,alerts_enabled,created_at,verification_token_hash,verification_expires_at)
            VALUES(?,?,'user',0,1,1,?,?,?)""",(email,_password_hash(password),iso(),hashed,expiry)); uid=int(cur.lastrowid)
    except sqlite3.IntegrityError as exc: raise HTTPException(409,"An account with this email already exists.") from exc
    return uid,token
def verify_email_token(token):
    if not token or len(token)>200: return False
    with _connect() as db:
        row=db.execute("SELECT id,verification_expires_at FROM users WHERE verification_token_hash=?",(hashlib.sha256(token.encode()).hexdigest(),)).fetchone()
        if not row or not row["verification_expires_at"]: return False
        try: expiry=datetime.fromisoformat(row["verification_expires_at"])
        except ValueError: return False
        if expiry<=now_utc(): return False
        db.execute("UPDATE users SET is_verified=1,verification_token_hash=NULL,verification_expires_at=NULL WHERE id=?",(row["id"],))
        return True
def public_user(u):
    return {"id":int(u["id"]),"email":u["email"],"role":u["role"],"is_verified":bool(u["is_verified"]),
            "alerts_enabled":bool(u["alerts_enabled"]),"created_at":u["created_at"]}
def authenticate(email,password):
    with _connect() as db: u=db.execute("SELECT * FROM users WHERE email=?",(email.strip().lower(),)).fetchone()
    if not u or not _verify_password(password,u["password_hash"]) or not u["is_active"] or not u["is_verified"]: return None
    return public_user(dict(u))
def create_session(user_id):
    token=secrets.token_urlsafe(48); hashed=hashlib.sha256(token.encode()).hexdigest(); created=now_utc()
    expiry=created+timedelta(hours=max(1,min(SESSION_HOURS,168)))
    with _connect() as db:
        db.execute("DELETE FROM sessions WHERE expires_at<=?",(iso(created),))
        db.execute("INSERT INTO sessions(token_hash,user_id,created_at,expires_at) VALUES(?,?,?,?)",(hashed,user_id,iso(created),iso(expiry)))
    return token,iso(expiry)
def get_user_from_request(request):
    token=request.cookies.get(SESSION_COOKIE)
    if not token or len(token)>200: return None
    with _connect() as db:
        row=db.execute("""SELECT u.* FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token_hash=? AND s.expires_at>?""",
          (hashlib.sha256(token.encode()).hexdigest(),iso())).fetchone()
    if not row or not row["is_active"] or not row["is_verified"]: return None
    return public_user(dict(row))
def require_user(request:Request):
    user=get_user_from_request(request)
    if not user: raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,detail="Sign in required.")
    return user
def require_admin(request:Request):
    user=require_user(request)
    if user["role"]!="admin": raise HTTPException(403,"Platform admin access required.")
    return user
def revoke_session(request):
    token=request.cookies.get(SESSION_COOKIE)
    if token:
        with _connect() as db: db.execute("DELETE FROM sessions WHERE token_hash=?",(hashlib.sha256(token.encode()).hexdigest(),))
def audit(action,actor=None,target=None,outcome="success",details=None):
    with _connect() as db:
        db.execute("INSERT INTO audit_logs(actor_user_id,actor_email,action,target,outcome,details,created_at) VALUES(?,?,?,?,?,?,?)",
        (actor.get("id") if actor else None,actor.get("email") if actor else None,action,target,outcome,(details or "")[:500],iso()))
def set_alerts_enabled(uid,enabled):
    with _connect() as db: db.execute("UPDATE users SET alerts_enabled=? WHERE id=? AND role='user'",(int(enabled),uid))
def admin_snapshot():
    with _connect() as db:
        counts={"users_total":db.execute("SELECT COUNT(*) FROM users WHERE role='user'").fetchone()[0],
        "users_verified":db.execute("SELECT COUNT(*) FROM users WHERE role='user' AND is_verified=1").fetchone()[0],
        "admins":db.execute("SELECT COUNT(*) FROM users WHERE role='admin'").fetchone()[0],
        "active_sessions":db.execute("SELECT COUNT(*) FROM sessions WHERE expires_at>?",(iso(),)).fetchone()[0],
        "alerts_sent":db.execute("SELECT COUNT(*) FROM alert_dispatches WHERE recipient_count>0").fetchone()[0]}
        logs=db.execute("SELECT id,actor_email,action,target,outcome,details,created_at FROM audit_logs ORDER BY id DESC LIMIT 20").fetchall()
    return {"counts":{k:int(v) for k,v in counts.items()},"recent_activity":[dict(x) for x in logs]}
def list_users(limit=200):
    with _connect() as db:
        rows=db.execute("SELECT id,email,role,is_verified,is_active,alerts_enabled,created_at FROM users ORDER BY id DESC LIMIT ?",(max(1,min(limit,500)),)).fetchall()
    return [{**dict(r),"is_verified":bool(r["is_verified"]),"is_active":bool(r["is_active"]),"alerts_enabled":bool(r["alerts_enabled"])} for r in rows]
def set_user_active(uid,active):
    with _connect() as db:
        cur=db.execute("UPDATE users SET is_active=? WHERE id=? AND role='user'",(int(active),uid))
        if not active: db.execute("DELETE FROM sessions WHERE user_id=?",(uid,))
        return cur.rowcount>0
def get_verified_alert_recipients():
    with _connect() as db:
        rows=db.execute("SELECT email FROM users WHERE role='user' AND is_active=1 AND is_verified=1 AND alerts_enabled=1 ORDER BY id").fetchall()
    return [r["email"] for r in rows]
def reserve_alert_dispatch(region_id,status_value,event_id):
    try:
        with _connect() as db: db.execute("INSERT INTO alert_dispatches(region_id,status,event_id,recipient_count,created_at) VALUES(?,?,?,0,?)",(region_id,status_value,event_id,iso()))
        return True
    except sqlite3.IntegrityError: return False
def finish_alert_dispatch(region_id,status_value,event_id,count):
    with _connect() as db: db.execute("UPDATE alert_dispatches SET recipient_count=? WHERE region_id=? AND status=? AND event_id=?",(count,region_id,status_value,event_id))
