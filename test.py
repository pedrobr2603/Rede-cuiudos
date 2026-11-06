import http.client, json
H, P, INV = "127.0.0.1", 8123, "amigos2026"
ok = bad = 0
def chk(n, c, d=""):
    global ok, bad; ok += c; bad += (not c); print(("PASS " if c else "FAIL ") + n + (" — " + d if (d and not c) else ""))
class C:
    sid = None
    def r(s, m, p, b=None, xrw=True, ct=True, raw=None):
        h = {}
        if ct: h["Content-Type"] = "application/json"
        if xrw: h["X-Requested-With"] = "fetch"
        if s.sid: h["Cookie"] = "sid=" + s.sid
        c = http.client.HTTPConnection(H, P); c.request(m, p, raw if raw is not None else (json.dumps(b) if b is not None else None), h); r = c.getresponse(); t = r.read().decode()
        sc = r.getheader("Set-Cookie")
        if sc and sc.startswith("sid=") and "Max-Age=0" not in sc: s.sid = sc.split(";")[0][4:]
        try: j = json.loads(t)
        except Exception: j = None
        return r.status, j, t, r
def user(u, pw="senha-forte-1"):
    c = C(); c.r("POST", "/api/register", {"username": u, "password": pw, "name": u.title(), "invite": INV}); c.r("POST", "/api/login", {"username": u, "password": pw}); return c
chk("Cadastro sem convite → 403", C().r("POST", "/api/register", {"username": "x1x", "password": "senha-forte-1", "invite": "errado"})[0] == 403)
chk("Cadastro com senha curta → 400", C().r("POST", "/api/register", {"username": "x2x", "password": "123", "invite": INV})[0] == 400)
a, b, c = user("ana"), user("beto"), user("carla")
chk("Login ok e /api/me", a.r("GET", "/api/me")[1]["username"] == "ana")
chk("Sem login → 401", C().r("GET", "/api/feed")[0] == 401)
chk("SQLi no login → 401", C().r("POST", "/api/login", {"username": "' OR 1=1--", "password": "x"})[0] == 401)
pid = a.r("POST", "/api/posts", {"text": "<script>alert(1)</script> oi"})[1]["id"]
s, j, t, r = b.r("GET", "/api/feed"); chk("Feed compartilhado + JSON/nosniff (XSS inerte)", "oi" in t and r.getheader("X-Content-Type-Options") == "nosniff")
chk("IDOR: beto não apaga post da ana", b.r("DELETE", f"/api/posts/{pid}")[0] == 404)
b.r("POST", f"/api/posts/{pid}/like"); chk("Curtir", len(a.r("GET", "/api/feed")[1]["posts"][0]["likes"]) == 1)
b.r("POST", f"/api/posts/{pid}/like"); chk("Descurtir (toggle)", len(a.r("GET", "/api/feed")[1]["posts"][0]["likes"]) == 0)
b.r("POST", f"/api/posts/{pid}/comments", {"text": "boa"}); chk("Comentar", a.r("GET", "/api/feed")[1]["posts"][0]["comments"][0]["text"] == "boa")
ids = {u["username"] if "username" in u else u["name"]: u["id"] for u in a.r("GET", "/api/users")[1]["users"]}
idA = a.r("GET", "/api/me")[1]["id"]; idB = [u["id"] for u in a.r("GET", "/api/users")[1]["users"] if u["name"] == "Beto"][0]
a.r("POST", f"/api/dm/{idB}", {"text": "segredo entre ana e beto"})
chk("Beto lê a DM", "segredo entre ana e beto" in b.r("GET", f"/api/dm/{idA}")[2])
chk("Carla NÃO lê a DM", "segredo" not in c.r("GET", f"/api/dm/{idA}")[2] and "segredo" not in c.r("GET", f"/api/dm/{idB}")[2])
chk("Não dá pra mandar DM pra si mesmo", a.r("POST", f"/api/dm/{idA}", {"text": "x"})[0] == 400)
import time; eid = a.r("POST", "/api/events", {"title": "Churrasco", "when": int(time.time() * 1000) + 86400000, "place": "casa"})[1]["id"]
b.r("POST", f"/api/events/{eid}/rsvp", {"s": "go"}); chk("RSVP", a.r("GET", "/api/events")[1]["events"][0]["rsvps"][0]["s"] == "go")
chk("IDOR: beto não apaga evento da ana", b.r("DELETE", f"/api/events/{eid}")[0] == 404)
chk("CSRF: sem X-Requested-With → 403", a.r("POST", "/api/posts", {"text": "x"}, xrw=False)[0] == 403)
chk("CSRF: form-urlencoded → 403", a.r("POST", "/api/posts", raw="text=x", ct=False)[0] == 403)
chk("Body gigante → 413", a.r("POST", "/api/posts", raw="x" * 20000)[0] == 413)
chk("JSON quebrado → 400 sem stack", (lambda x: x[0] == 400 and "Traceback" not in x[2])(a.r("POST", "/api/posts", raw="{x")))
codes = [C().r("POST", "/api/login", {"username": "ana", "password": f"errada{i}"})[0] for i in range(8)]; chk("Rate limit de login", 429 in codes, str(codes))
codes = [C().r("POST", "/api/register", {"username": "zz", "password": "x", "invite": f"c{i}"})[0] for i in range(12)]; chk("Rate limit de convite (força bruta)", 429 in codes, str(codes))
for p in ["/../app.py", "/..%2fapp.py", "/cuiudos.db"]: s, _, t, _ = C().r("GET", p); chk(f"Path traversal {p}", s == 404 and "import" not in t)
s, _, _, r = C().r("GET", "/"); chk("Headers de segurança + CSP", all(r.getheader(h) for h in ["Content-Security-Policy", "X-Frame-Options", "X-Content-Type-Options"]))
ck = C().r("POST", "/api/login", {"username": "beto", "password": "senha-forte-1"})[3].getheader("Set-Cookie"); chk("Cookie HttpOnly + SameSite=Strict", "HttpOnly" in ck and "SameSite=Strict" in ck)
old = a.sid; a.r("POST", "/api/logout"); z = C(); z.sid = old; chk("Logout invalida sessão no servidor", z.r("GET", "/api/me")[0] == 401)
print(f"\n{ok}/{ok+bad} passaram")
