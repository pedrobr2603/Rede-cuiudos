"""Rede Cuiudos: servidor próprio com cadastro/login (só biblioteca padrão)."""
import json, sqlite3, secrets, hashlib, hmac, time, os, re, threading, ssl
import urllib.parse as up
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from http.cookies import SimpleCookie

HERE = os.path.dirname(os.path.abspath(__file__))
DB = os.environ.get("DB", os.path.join(HERE, "cuiudos.db"))
PORT = int(os.environ.get("PORT", 8000)); HOST = os.environ.get("HOST", "127.0.0.1")
INVITE = os.environ.get("INVITE_CODE") or secrets.token_urlsafe(6)
HTTPS = bool(os.environ.get("HTTPS"))
fails = {}
STATIC = {p: (ct, open(os.path.join(HERE, f), "rb").read()) for p, f, ct in
          [("/", "index.html", "text/html; charset=utf-8"), ("/app.js", "app.js", "application/javascript"), ("/app.css", "app.css", "text/css")]}

MYSQL_URL = os.environ.get("MYSQL_URL")  # ex.: mysql://usuario:senha@host:porta/banco (se vazio, usa SQLite)
MYSQL = bool(MYSQL_URL)
IntegrityError = sqlite3.IntegrityError
if MYSQL:
    import pymysql; IntegrityError = pymysql.err.IntegrityError
_pool, _pl = [], threading.Lock()
class Res:
    def __init__(s, lid, rc): s.lastrowid, s.rowcount = lid, rc

def newc():
    if MYSQL:
        p = up.urlparse(MYSQL_URL); ctx = ssl.create_default_context(); ctx.check_hostname = False
        pem = os.environ.get("MYSQL_CA_PEM")
        if pem: ctx.load_verify_locations(cadata=pem)
        else: ctx.verify_mode = ssl.CERT_NONE  # criptografado, mas sem verificar o servidor (defina MYSQL_CA_PEM)
        return pymysql.connect(host=p.hostname, port=p.port or 3306, user=up.unquote(p.username or ""), password=up.unquote(p.password or ""),
                               database=p.path.lstrip("/") or None, charset="utf8mb4", autocommit=True, connect_timeout=10, cursorclass=pymysql.cursors.DictCursor, ssl=ctx)
    c = sqlite3.connect(DB, check_same_thread=False); c.row_factory = sqlite3.Row; return c

def getc():
    with _pl: c = _pool.pop() if _pool else None
    if c is None: return newc()
    if MYSQL:
        try: c.ping(reconnect=True)
        except Exception: c = newc()
    return c

def Q(sql, a=()):
    c = getc()
    try:
        cur = c.cursor(); cur.execute(sql.replace("?", "%s") if MYSQL else sql, tuple(a))
        res = [dict(r) for r in cur.fetchall()] if sql.lstrip()[:6].lower() == "select" else Res(cur.lastrowid, cur.rowcount)
        if not MYSQL: c.commit()
        with _pl:
            if len(_pool) < 8: _pool.append(c); c = None
        return res
    except Exception:
        try: c.close()
        except Exception: pass
        c = None; raise
    finally:
        if c is not None: c.close()
def one(sql, a=()): r = Q(sql, a); return r[0] if r else None

T = " engine=InnoDB default charset=utf8mb4"
DDL_MYSQL = ["create table if not exists users(id bigint auto_increment primary key, username varchar(20) unique not null, name varchar(30) not null, pw varchar(200) not null)" + T,
 "create table if not exists sessions(th char(64) primary key, uid bigint not null, exp double not null)" + T,
 "create table if not exists posts(id bigint auto_increment primary key, uid bigint not null, text varchar(500) not null, ts bigint not null)" + T,
 "create table if not exists likes(pid bigint, uid bigint, primary key(pid,uid))" + T,
 "create table if not exists comments(id bigint auto_increment primary key, pid bigint not null, uid bigint not null, text varchar(300) not null, ts bigint not null)" + T,
 "create table if not exists dms(id bigint auto_increment primary key, frm bigint not null, tof bigint not null, text varchar(500) not null, ts bigint not null)" + T,
 "create table if not exists events(id bigint auto_increment primary key, uid bigint not null, title varchar(80) not null, place varchar(100), whenx bigint not null, ts bigint not null)" + T,
 "create table if not exists rsvps(eid bigint, uid bigint, s varchar(10) not null, primary key(eid,uid))" + T]
DDL_SQLITE = """
    create table if not exists users(id integer primary key, username text unique not null, name text not null, pw text not null);
    create table if not exists sessions(th text primary key, uid integer not null, exp real not null);
    create table if not exists posts(id integer primary key, uid integer not null, text text not null, ts integer not null);
    create table if not exists likes(pid integer, uid integer, primary key(pid,uid));
    create table if not exists comments(id integer primary key, pid integer not null, uid integer not null, text text not null, ts integer not null);
    create table if not exists dms(id integer primary key, frm integer not null, tof integer not null, text text not null, ts integer not null);
    create table if not exists events(id integer primary key, uid integer not null, title text not null, place text, whenx integer not null, ts integer not null);
    create table if not exists rsvps(eid integer, uid integer, s text not null, primary key(eid,uid));"""

def init():
    if MYSQL:
        for d in DDL_MYSQL: Q(d)
        if not os.environ.get("MYSQL_CA_PEM"): print("AVISO: MYSQL_CA_PEM não definido; conexão criptografada mas sem verificar o servidor.")
    else:
        c = sqlite3.connect(DB); c.executescript(DDL_SQLITE); c.commit(); c.close()

def hp(pw):
    s = secrets.token_bytes(16); return s.hex() + "$" + hashlib.pbkdf2_hmac("sha256", pw.encode(), s, 200_000).hex()
def cp(pw, st):
    s, h = st.split("$"); return hmac.compare_digest(hashlib.pbkdf2_hmac("sha256", pw.encode(), bytes.fromhex(s), 200_000).hex(), h)
DUMMY = hp("x"); sha = lambda t: hashlib.sha256(t.encode()).hexdigest(); now = lambda: int(time.time() * 1000)

R = []
def route(m, p, public=False):
    def d(f): R.append((m, re.compile("^" + p + "$"), f, public)); return f
    return d
def throttle(key, limit=5):
    t = time.time(); fails[key] = [x for x in fails.get(key, []) if t - x < 60]; return len(fails[key]) >= limit
def txt(b, key, n):
    v = str(b.get(key, "")).strip(); return v[:n] if v else None

@route("POST", "/api/register", True)
def register(h, u, b):
    ip = h.client_address[0]
    if throttle((ip, "reg"), 8): return 429, {"error": "muitas tentativas, aguarde"}
    if not hmac.compare_digest(str(b.get("invite", "")), INVITE):
        fails[(ip, "reg")].append(time.time()); return 403, {"error": "código de convite inválido"}
    un, pw = str(b.get("username", "")).strip().lower(), str(b.get("password", ""))
    if not re.fullmatch(r"[a-z0-9_]{3,20}", un) or not 8 <= len(pw) <= 128: return 400, {"error": "usuário: 3-20 letras/números/_; senha: 8-128"}
    try: Q("insert into users(username,name,pw) values(?,?,?)", (un, (txt(b, "name", 30) or un), hp(pw)))
    except IntegrityError: return 409, {"error": "usuário já existe"}
    return 201, {"ok": True}

@route("POST", "/api/login", True)
def login(h, u, b):
    un, pw = str(b.get("username", "")).strip().lower(), str(b.get("password", "")); k = (h.client_address[0], un)
    if throttle(k): return 429, {"error": "muitas tentativas, aguarde"}
    r = one("select id,pw from users where username=?", (un,))
    if not (cp(pw, r["pw"] if r else DUMMY) and r): fails[k].append(time.time()); return 401, {"error": "usuário ou senha incorretos"}
    tok = secrets.token_urlsafe(32); Q("insert into sessions values(?,?,?)", (sha(tok), r["id"], time.time() + 7 * 86400))
    h.cookie = f"sid={tok}; HttpOnly; SameSite=Strict; Path=/; Max-Age={7*86400}" + ("; Secure" if HTTPS else ""); return 200, {"ok": True}

@route("POST", "/api/logout")
def logout(h, u, b):
    Q("delete from sessions where th=?", (sha(SimpleCookie(h.headers.get("Cookie", ""))["sid"].value),))
    h.cookie = "sid=; Max-Age=0; Path=/; HttpOnly; SameSite=Strict"; return 200, {"ok": True}

@route("GET", "/api/me")
def me(h, u, b): return 200, dict(u)

@route("GET", "/api/users")
def users(h, u, b): return 200, {"users": [dict(r) for r in Q("select id,name from users where id!=? order by name", (u["id"],))]}

@route("GET", "/api/feed")
def feed(h, u, b):
    ps = Q("select p.id,p.text,p.ts,p.uid,u.name from posts p join users u on u.id=p.uid order by p.id desc limit 100")
    lk = cm = []
    if ps:
        ids = [p["id"] for p in ps]; ph = ",".join("?" * len(ids))
        lk = Q(f"select pid,uid from likes where pid in ({ph})", ids)
        cm = Q(f"select c.pid,c.text,c.ts,c.uid,u.name from comments c join users u on u.id=c.uid where c.pid in ({ph}) order by c.id", ids)
    for p in ps:
        p["likes"] = [l["uid"] for l in lk if l["pid"] == p["id"]]
        p["comments"] = [{k: c[k] for k in ("text", "ts", "uid", "name")} for c in cm if c["pid"] == p["id"]]
    return 200, {"posts": ps}

@route("POST", "/api/posts")
def post(h, u, b):
    t = txt(b, "text", 500)
    if not t: return 400, {"error": "texto obrigatório"}
    return 201, {"id": Q("insert into posts(uid,text,ts) values(?,?,?)", (u["id"], t, now())).lastrowid}

@route("DELETE", r"/api/posts/(\d+)")
def delpost(h, u, b, i):
    if not Q("delete from posts where id=? and uid=?", (i, u["id"])).rowcount: return 404, {"error": "não encontrado"}
    Q("delete from likes where pid=?", (i,)); Q("delete from comments where pid=?", (i,)); return 200, {"ok": True}

@route("POST", r"/api/posts/(\d+)/like")
def like(h, u, b, i):
    if not one("select 1 from posts where id=?", (i,)): return 404, {"error": "não encontrado"}
    if not Q("delete from likes where pid=? and uid=?", (i, u["id"])).rowcount: Q("insert into likes values(?,?)", (i, u["id"]))
    return 200, {"ok": True}

@route("POST", r"/api/posts/(\d+)/comments")
def comment(h, u, b, i):
    t = txt(b, "text", 300)
    if not t or not one("select 1 from posts where id=?", (i,)): return 400, {"error": "inválido"}
    Q("insert into comments(pid,uid,text,ts) values(?,?,?,?)", (i, u["id"], t, now())); return 201, {"ok": True}

@route("GET", r"/api/dm/(\d+)")
def dm_get(h, u, b, o):
    return 200, {"msgs": [dict(r) for r in Q("select id,frm,text,ts from dms where (frm=? and tof=?) or (frm=? and tof=?) order by id limit 300", (u["id"], o, o, u["id"]))]}

@route("POST", r"/api/dm/(\d+)")
def dm_send(h, u, b, o):
    t = txt(b, "text", 500)
    if not t or int(o) == u["id"] or not one("select 1 from users where id=?", (o,)): return 400, {"error": "inválido"}
    Q("insert into dms(frm,tof,text,ts) values(?,?,?,?)", (u["id"], o, t, now())); return 201, {"ok": True}

@route("GET", "/api/events")
def events(h, u, b):
    es = Q("select e.id,e.title,e.place,e.whenx,e.uid,u.name from events e join users u on u.id=e.uid order by e.whenx")
    rs = Q("select r.eid,r.uid,r.s,u.name from rsvps r join users u on u.id=r.uid") if es else []
    for e in es: e["rsvps"] = [{"uid": r["uid"], "s": r["s"], "name": r["name"]} for r in rs if r["eid"] == e["id"]]
    return 200, {"events": es}

@route("POST", "/api/events")
def ev_new(h, u, b):
    t = txt(b, "title", 80)
    try: w = int(b.get("when"))
    except Exception: w = None
    if not t or not w: return 400, {"error": "título e data obrigatórios"}
    return 201, {"id": Q("insert into events(uid,title,place,whenx,ts) values(?,?,?,?,?)", (u["id"], t, txt(b, "place", 100) or "", w, now())).lastrowid}

@route("POST", r"/api/events/(\d+)/rsvp")
def rsvp(h, u, b, i):
    s = b.get("s")
    if s not in ("go", "maybe", "no", "none") or not one("select 1 from events where id=?", (i,)): return 400, {"error": "inválido"}
    Q("delete from rsvps where eid=? and uid=?", (i, u["id"]))
    if s != "none": Q("insert into rsvps values(?,?,?)", (i, u["id"], s))
    return 200, {"ok": True}

@route("DELETE", r"/api/events/(\d+)")
def ev_del(h, u, b, i):
    if not Q("delete from events where id=? and uid=?", (i, u["id"])).rowcount: return 404, {"error": "não encontrado"}
    Q("delete from rsvps where eid=?", (i,)); return 200, {"ok": True}

class H(BaseHTTPRequestHandler):
    server_version = "x"; sys_version = ""; cookie = None
    def log_message(self, *a): pass
    def out(self, code, obj, ct="application/json"):
        body = obj if isinstance(obj, bytes) else json.dumps(obj).encode()
        self.send_response(code)
        for k, v in [("Content-Type", ct), ("Content-Length", len(body)), ("X-Content-Type-Options", "nosniff"), ("X-Frame-Options", "DENY"), ("Referrer-Policy", "no-referrer"), ("Cache-Control", "no-store"),
                     ("Content-Security-Policy", "default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'")]:
            self.send_header(k, str(v))
        if self.cookie: self.send_header("Set-Cookie", self.cookie)
        self.end_headers(); self.wfile.write(body)
    def user(self):
        c = SimpleCookie(self.headers.get("Cookie", ""))
        if "sid" not in c: return None
        return one("select u.id,u.username,u.name from sessions s join users u on u.id=s.uid where s.th=? and s.exp>?", (sha(c["sid"].value), time.time()))
    def go(self, m):
        path = self.path.split("?")[0]
        if m == "GET" and path in STATIC: ct, b = STATIC[path]; return self.out(200, b, ct)
        for rm, rx, f, pub in R:
            g = rx.match(path)
            if rm != m or not g: continue
            if self.headers.get("X-Requested-With") != "fetch": return self.out(403, {"error": "requisição inválida"})  # anti-CSRF
            u = None if pub else self.user()
            if not pub and not u: return self.out(401, {"error": "não autenticado"})
            b = {}
            if m == "POST":
                n = int(self.headers.get("Content-Length") or 0)
                if n > 10_000: return self.out(413, {"error": "grande demais"})
                if "application/json" not in self.headers.get("Content-Type", ""): return self.out(403, {"error": "requisição inválida"})
                try: b = json.loads(self.rfile.read(n) or b"{}"); assert isinstance(b, dict)
                except Exception: return self.out(400, {"error": "JSON inválido"})
            try: code, obj = f(self, u, b, *g.groups())
            except Exception: code, obj = 500, {"error": "erro interno"}
            return self.out(code, obj)
        self.out(404, {"error": "não encontrado"})
    do_GET = lambda s: s.go("GET"); do_POST = lambda s: s.go("POST"); do_DELETE = lambda s: s.go("DELETE")

if __name__ == "__main__":
    init(); print(f"Rede Cuiudos em http://{HOST}:{PORT}\nCódigo de convite: {INVITE}")
    ThreadingHTTPServer((HOST, PORT), H).serve_forever()
