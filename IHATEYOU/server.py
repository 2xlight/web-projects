import json, re, time, secrets, hashlib, random, base64, threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from http.cookies import SimpleCookie
from pathlib import Path
from urllib.parse import urlparse, parse_qs, unquote

BASE = Path(__file__).parent
DATA, UP, ST = BASE / "data.json", BASE / "uploads", BASE / "static"
UP.mkdir(exist_ok=True); ST.mkdir(exist_ok=True)

RICK = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
WEEK, PRO, LIM = 7 * 86400, 200, 10   # 1 tuần | điểm đạt khung PRO | ngưỡng ban/report
HIDDEN = "H"                          # board ẩn: lưu "chiến tích" của hacker
HONEY = {"/api/admin", "/admin", "/.env", "/wp-login.php", "/phpmyadmin"}
MIME = {"png": "image/png", "jpg": "image/jpeg", "gif": "image/gif", "webp": "image/webp"}
L = threading.RLock()

BOARDS = {
    "r": {"name": "Random - nói gì cũng được.", "desc": "Bạn nói tui nghe coi-"},
    "it": {"name": "Technology - RAM, vibe-coding,...", "desc": "About công nghệ nhưng không cần thượng đẳng."},
    "CF": {"name": "Confession - Chí Fèo", "desc": "Chắc nó không chừa mình ra."},
    "Stu": {"name": "Study - Học, học nữa, học mãi", "desc": "Tìm nhóm học, bàn về học, khoe cái học."},
    "W": {"name": "Work - Thất thất nghiệp", "desc": "Thất thất nghiệp"},
}

# ---------- Payload / troll: xem security.py ----------
from security import scan, scan_ua, TROLL, NOTE_LO, NOTE_HI

def sniff(b):  # kiểm tra magic bytes, không tin tên file / mime client gửi
    if b.startswith(b"\x89PNG\r\n\x1a\n"): return "png"
    if b.startswith(b"\xff\xd8\xff"): return "jpg"
    if b[:6] in (b"GIF87a", b"GIF89a"): return "gif"
    if b[:4] == b"RIFF" and b[8:12] == b"WEBP": return "webp"

# ---------- State ----------
S = {"users": {}, "posts": [], "banned": {}, "muted": {}, "gt": {}, "pid": 1, "cid": 1}
if DATA.exists(): S.update(json.loads(DATA.read_text("utf-8")))
sessions, fails = {}, {}

def save(): DATA.write_text(json.dumps(S, ensure_ascii=False), "utf-8")
def nid(k): S[k] += 1; return S[k] - 1
def now(): return time.time()
def hashpw(pw, salt): return hashlib.pbkdf2_hmac("sha256", pw.encode(), bytes.fromhex(salt), 200_000).hex()
def uscore(o): return sum(o["uv"].values())          # điểm do NGƯỜI DÙNG vote
def mkey(author, ip): return author if author in S["users"] else "ip:" + ip

def grade(t, img):                                    # điểm do WEB chấm (chỉ board CF)
    s = min(100, 20 + len(t) // 3 + (15 if img else 0) + random.randint(0, 25))
    return s, random.choice(NOTE_LO if s < 50 else NOTE_HI)

def cf_rows():
    d = {}
    for p in S["posts"]:
        if p["board"] == "CF" and p["author"] in S["users"]:
            r = d.setdefault(p["author"], {"author": p["author"], "user": 0, "web": 0, "posts": 0})
            r["user"] += uscore(p); r["web"] += p.get("web") or 0; r["posts"] += 1
    rows = sorted(d.values(), key=lambda r: -(r["user"] + r["web"]))
    for i, r in enumerate(rows): r["rank"] = i + 1; r["total"] = r["user"] + r["web"]
    return rows

def frame(name):
    u = S["users"].get(name)
    if not u: return ""
    if S["muted"].get(name, 0) > now(): return "noob"
    if u.get("hacks"): return "hacker"
    rows = cf_rows()
    if rows and rows[0]["author"] == name: return "admin"
    return "pro" if next((r["total"] for r in rows if r["author"] == name), 0) >= PRO else ""

def pub_c(c, me):
    hide = len(c["rep"]) >= LIM
    return {"id": c["id"], "author": c["author"], "frame": frame(c["author"]), "parent": c.get("parent"),
            "content": "[Bình luận đã bị ẩn vì bị báo cáo]" if hide else c["content"],
            "score": uscore(c), "my": c["uv"].get(me, 0), "reports": len(c["rep"])}

def pub_p(p, me):
    hide = len(p["rep"]) >= LIM
    d = {"id": p["id"], "board": p["board"], "author": p["author"], "frame": frame(p["author"]),
         "content": "[Bài đã bị ẩn vì bị báo cáo]" if hide else p["content"],
         "image": None if hide else p.get("image"), "score": uscore(p), "my": p["uv"].get(me, 0),
         "reports": len(p["rep"]), "comments": [pub_c(c, me) for c in p["comments"]]}
    if p["board"] == "CF": d["web"], d["webnote"] = p.get("web"), p.get("webnote")
    return d

def find(kind, i):
    for p in S["posts"]:
        if kind == "posts" and p["id"] == i: return p
        for c in p["comments"]:
            if kind == "comments" and c["id"] == i: return c, p
    return None

def ban(ip): S["banned"][ip] = now() + WEEK; save()
def is_admin(u): return bool(u and S["users"].get(u, {}).get("admin"))

def init_admin():
    """Tạo tài khoản 'admin' lần đầu. Mật khẩu lấy từ biến môi trường IHY_ADMIN_PASS,
    nếu không có thì sinh ngẫu nhiên và in ra console đúng 1 lần. Vì tạo lúc khởi động
    nên không ai đăng ký trước tên 'admin' được."""
    import os
    if "admin" in S["users"]: return
    pw = os.environ.get("IHY_ADMIN_PASS") or secrets.token_urlsafe(9)
    salt = secrets.token_hex(8)
    S["users"]["admin"] = {"salt": salt, "hash": hashpw(pw, salt), "hacks": 0, "ts": now(), "admin": True}
    save(); print(f"[ADMIN] user=admin  pass={pw}  (chỉ in 1 lần)")

def save_img(d):
    """None = không có ảnh | 'rick' = sai định dạng | 'big' = quá lớn | '/uploads/..' = ok"""
    if not d: return None
    try:
        head, b64 = d.split(",", 1)
        raw = base64.b64decode(b64, validate=True)
    except Exception:
        return "rick"
    ext = sniff(raw)
    if not ext or head.split(";")[0] != "data:image/" + {"jpg": "jpeg"}.get(ext, ext): return "rick"
    if len(raw) > 2_000_000: return "big"
    name = secrets.token_hex(8) + "." + ext          # tên ngẫu nhiên, bỏ qua tên client
    (UP / name).write_bytes(raw)
    return "/uploads/" + name

# ---------- HTTP ----------
class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def out(self, data, code=200, ctype="application/json; charset=utf-8", cookie=None):
        b = data if isinstance(data, bytes) else data.encode() if isinstance(data, str) else json.dumps(data, ensure_ascii=False).encode()
        self.send_response(code)
        for k, v in {"Content-Type": ctype, "Content-Length": str(len(b)), "X-Content-Type-Options": "nosniff",
                     "Content-Security-Policy": "default-src 'self'; img-src 'self' data:; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; frame-ancestors 'none'"}.items():
            self.send_header(k, v)
        if cookie: self.send_header("Set-Cookie", cookie)
        self.end_headers(); self.wfile.write(b)

    def sid(self):
        c = SimpleCookie(self.headers.get("Cookie", ""))
        return c["sid"].value if "sid" in c else None

    def body(self):
        n = int(self.headers.get("Content-Length", 0) or 0)
        if n > 3_500_000 or "application/json" not in self.headers.get("Content-Type", ""): raise ValueError
        return json.loads(self.rfile.read(n) or b"{}")   # bắt buộc JSON → chặn CSRF form cross-site

    def record(self, kind, field, text, me):             # ghi danh hacker vào board ẩn (BXH Chí Fèo 4.0)
        who = me or "Khách-" + hashlib.sha1(self.ip.encode()).hexdigest()[:5]
        web, note = min(100, 15 + len(text) // 4 + random.randint(0, 40)), random.choice(TROLL[kind])
        S["posts"].insert(0, {"id": nid("pid"), "board": HIDDEN, "author": who, "content": text[:300], "field": field, "kind": kind,
                              "web": web, "webnote": note, "ts": now(), "uv": {}, "rep": [], "comments": [], "ip": self.ip})
        if me: S["users"][me]["hacks"] = S["users"][me].get("hacks", 0) + 1
        save(); return note, web

    def caught(self, kind, field, text, me):
        note, web = self.record(kind, field, text, me)
        self.out({"error": "Phát hiện payload! 🚨", "troll": note, "web": web}, 403)

    def honey(self, me):
        note, _ = self.record("honey", "path", self.path, me)
        # >>> CHÈN ẢNH RICKROLL Ở ĐÂY: đặt file vào thư mục static/ với tên rickroll.gif (hoặc đổi src bên dưới)
        self.out(f'<!doctype html><meta charset="utf-8"><title>Admin</title><body style="background:#000;color:#fff;text-align:center">'
                 f'<h2>Chào mừng admin 😏</h2><img src="/static/rickroll.gif" style="max-width:90%"><p>{note}</p>', 200, "text/html; charset=utf-8")

    def asset(self, d, name):
        f = d / Path(unquote(name)).name                 # .name chặn ../
        ct = MIME.get(f.suffix.lower().lstrip(".").replace("jpeg", "jpg"))
        if not ct or not f.is_file(): return self.out({"error": "Not found"}, 404)
        self.out(f.read_bytes(), 200, ct)

    # ---------- Phân trang ----------
    def paged(self, lst, q, me):
        """Cắt danh sách theo ?page=&size= (size tối đa 50) rồi trả {items, page, pages}."""
        size = max(1, min(int(q.get("size", ["10"])[0]), 50))
        pages = max(1, -(-len(lst) // size))                    # chia làm tròn lên
        page = max(1, min(int(q.get("page", ["1"])[0]), pages))  # kẹp page vào [1, pages]
        return self.out({"items": [pub_p(x, me) for x in lst[(page - 1) * size: page * size]], "page": page, "pages": pages})

    # ---------- Hồ sơ người dùng ----------
    def profile(self, name, me):
        """Tổng điểm (người + web) và lịch sử bài/bình luận của 1 user. Ai cũng xem được."""
        u = S["users"].get(name)
        if not u: return self.out({"error": "Không có user này"}, 404)
        ps = [x for x in S["posts"] if x["author"] == name and x["board"] != HIDDEN]
        cs = [(x["id"], c) for x in S["posts"] for c in x["comments"] if c["author"] == name]
        return self.out({
            "user": name, "frame": frame(name), "joined": u["ts"], "hacks": u.get("hacks", 0),
            "user_score": sum(uscore(x) for x in ps), "web_score": sum(x.get("web") or 0 for x in ps),
            "comment_score": sum(uscore(c) for _, c in cs),
            "posts": [{"id": x["id"], "board": x["board"], "content": x["content"][:80], "score": uscore(x), "web": x.get("web")} for x in ps[:20]],
            "comments": [{"post": i, "content": c["content"][:80], "score": uscore(c)} for i, c in cs[-20:]]})

    # ---------- Quản trị (chỉ tài khoản admin) ----------
    def mod_get(self, p, me):
        if not is_admin(me): return self.out({"error": "Chỉ admin."}, 403)
        if p == "/api/mod/bans":    # IP đang bị ban
            return self.out([{"ip": k, "until": v} for k, v in S["banned"].items() if v > now()])
        if p == "/api/mod/muted":   # user/IP đang bị khung NOOB
            return self.out([{"key": k, "until": v} for k, v in S["muted"].items() if v > now()])
        if p == "/api/mod/log":     # board ẩn + honeypot: có cả IP, loại tấn công
            keys = ("id", "author", "ip", "kind", "field", "content", "web", "ts")
            return self.out([{k: x.get(k) for k in keys} for x in S["posts"] if x["board"] == HIDDEN][:200])
        self.out({"error": "Not found"}, 404)

    def mod_post(self, p, d, me):
        if not is_admin(me): return self.out({"error": "Chỉ admin."}, 403)
        if p == "/api/mod/unban":   # gỡ ban + reset bộ đếm khách/bruteforce của IP đó
            ip = str(d.get("ip", "")); S["banned"].pop(ip, None); S["gt"].pop(ip, None); fails.pop(ip, None)
            save(); return self.out({"ok": True})
        if p == "/api/mod/unmute":
            S["muted"].pop(str(d.get("key", "")), None); save(); return self.out({"ok": True})
        self.out({"error": "Not found"}, 404)

    # ---------- Đổi mật khẩu / sửa / xóa bài ----------
    def change_pw(self, d, me):
        if not me: return self.out({"error": "Chưa đăng nhập"}, 401)
        rec, old, new = S["users"][me], str(d.get("old", "")), str(d.get("new", ""))
        if not secrets.compare_digest(rec["hash"], hashpw(old, rec["salt"])): return self.out({"error": "Mật khẩu cũ sai"}, 403)
        if len(new) < 6: return self.out({"error": "Mật khẩu mới ≥ 6 ký tự"}, 400)
        rec["salt"] = secrets.token_hex(8); rec["hash"] = hashpw(new, rec["salt"])   # salt mới
        save(); return self.out({"ok": True})

    def edit_delete(self, pid, act, d, me):
        """Chủ bài (hoặc admin) được sửa/xóa. Sửa không chấm lại điểm web để tránh farm điểm."""
        if not me: return self.out({"error": "Chưa đăng nhập"}, 401)
        post = find("posts", pid)
        if not post: return self.out({"error": "Không tìm thấy"}, 404)
        if post["author"] != me and not is_admin(me): return self.out({"error": "Không phải bài của bạn"}, 403)
        if act == "delete":
            if post.get("image"): (UP / Path(post["image"]).name).unlink(missing_ok=True)   # xóa luôn file ảnh
            S["posts"].remove(post); save(); return self.out({"ok": True})
        content = str(d.get("content", "")).strip()[:2000]
        if not content: return self.out({"error": "Nội dung trống"}, 400)
        k = scan(content)
        if k: return self.caught(k, "edit", content, me)
        post["content"] = content; save()
        return self.out(pub_p(post, me))

    def do_GET(self): self.go("GET")
    def do_POST(self): self.go("POST")

    def go(self, m):
        with L:
            self.ip = self.client_address[0]
            try:
                u = urlparse(self.path); p = u.path; me = sessions.get(self.sid())
                if S["banned"].get(self.ip, 0) > now():
                    return self.out({"error": "IP của bạn bị ban 1 tuần. Quay lại sau nhé 😘"}, 403)
                ua = self.headers.get("User-Agent", "")
                if scan_ua(ua):   # sqlmap, nikto... -> ghi danh + troll
                    return self.caught("scanner", "user-agent", ua, me)
                if p in HONEY: return self.honey(me)
                self.get(p, parse_qs(u.query), me) if m == "GET" else self.post(p, me)
            except Exception:
                self.out({"error": "Yêu cầu không hợp lệ"}, 400)

    def get(self, p, q, me):
        if p in ("/", "/index.html"): return self.out((BASE / "ihateyou.html").read_bytes(), 200, "text/html; charset=utf-8")
        if p.startswith("/static/"): return self.asset(ST, p[8:])
        if p.startswith("/uploads/"): return self.asset(UP, p[9:])
        if p == "/api/boards": return self.out(BOARDS)
        if p == "/admin.html": return self.out((BASE / "admin.html").read_bytes(), 200, "text/html; charset=utf-8")
        if p == "/api/me": return self.out({"user": me, "frame": frame(me) if me else "", "admin": is_admin(me)})
        if p == "/api/profile": return self.profile(q.get("u", [""])[0], me)
        if p.startswith("/api/mod/"): return self.mod_get(p, me)
        vis = [x for x in S["posts"] if x["board"] != HIDDEN]
        if p == "/api/posts":
            b = q.get("board", ["all"])[0]
            return self.paged([x for x in vis if b == "all" or x["board"] == b], q, me)
        if p == "/api/search":
            s = q.get("q", [""])[0][:100]; k = scan(s)
            if k: return self.caught(k, "search", s, me)
            return self.paged([x for x in vis if s.lower() in x["content"].lower() or s.lower() in x["author"].lower()], q, me)
        if p == "/api/leaderboard":
            if q.get("type", ["cf"])[0] == "cf":
                return self.out([dict(r, frame=frame(r["author"])) for r in cf_rows()[:20]])
            d = {}
            for x in S["posts"]:                         # board ẩn, mới nhất đứng trước
                if x["board"] == HIDDEN:
                    r = d.setdefault(x["author"], {"author": x["author"], "attempts": 0, "web": 0, "last": x["content"], "note": x["webnote"]})
                    r["attempts"] += 1; r["web"] += x["web"]
            rows = sorted(d.values(), key=lambda r: -r["web"])
            for i, r in enumerate(rows): r["rank"] = i + 1; r["frame"] = frame(r["author"]) or "hacker"
            return self.out(rows[:20])
        self.out({"error": "Not found"}, 404)

    def post(self, p, me):
        d = self.body(); ip = self.ip
        if p.startswith("/api/mod/"): return self.mod_post(p, d, me)
        if p == "/api/password": return self.change_pw(d, me)
        m2 = re.fullmatch(r"/api/posts/(\d+)/(edit|delete)", p)
        if m2: return self.edit_delete(int(m2[1]), m2[2], d, me)
        if p == "/api/logout":
            sessions.pop(self.sid(), None)
            return self.out({"ok": True}, cookie="sid=; Max-Age=0; Path=/")

        if p in ("/api/register", "/api/login"):
            u, pw = str(d.get("username", "")).strip(), str(d.get("password", ""))
            k = scan(u)
            if k: return self.caught(k, "login", u, None)
            if p.endswith("register"):
                if not re.fullmatch(r"\w{3,20}", u, re.A) or len(pw) < 6:
                    return self.out({"error": "Username 3-20 ký tự (chữ/số/_), mật khẩu ≥ 6 ký tự"}, 400)
                if u in S["users"]: return self.out({"error": "Username đã tồn tại"}, 409)
                salt = secrets.token_hex(8)
                S["users"][u] = {"salt": salt, "hash": hashpw(pw, salt), "hacks": 0, "ts": now()}; save()
            else:
                rec = S["users"].get(u)
                if not (rec and secrets.compare_digest(rec["hash"], hashpw(pw, rec["salt"]))):
                    fails[ip] = fails.get(ip, 0) + 1
                    if fails[ip] > LIM:
                        ban(ip); return self.out({"error": "Bruteforce hả? Ban IP 1 tuần 😘"}, 403)
                    return self.out({"error": f"Sai tài khoản/mật khẩu ({fails[ip]}/{LIM})"}, 401)
                fails.pop(ip, None)
            sid = secrets.token_hex(24); sessions[sid] = u
            return self.out({"user": u}, cookie=f"sid={sid}; HttpOnly; SameSite=Strict; Path=/; Max-Age={WEEK}")

        if p == "/api/posts":
            board, content, img = d.get("board"), str(d.get("content", "")).strip()[:2000], d.get("image")
            if board not in BOARDS or not (content or img): return self.out({"error": "Thiếu board hoặc nội dung"}, 400)
            k = scan(content)
            if k: return self.caught(k, "post", content, me)
            if S["muted"].get(mkey(me or "", ip), 0) > now(): return self.out({"error": "Bạn đang bị NOOB: cấm đăng 1 tuần."}, 403)
            if not me:                                   # khách: 1 post / IP, spam >10 lần → ban
                n = S["gt"][ip] = S["gt"].get(ip, 0) + 1; save()
                if n > LIM: ban(ip); return self.out({"error": "Spam hả? Ban IP 1 tuần."}, 403)
                if n > 1: return self.out({"error": "Khách chỉ được đăng 1 bài / IP. Đăng nhập đi cưng."}, 429)
            path = save_img(img)
            if path == "rick": return self.out({"error": "Định dạng ảnh lạ lắm nha cưng 😏", "rickroll": RICK}, 415)
            if path == "big": return self.out({"error": "Ảnh tối đa 2MB"}, 413)
            post = {"id": nid("pid"), "board": board, "author": me or "Khách-" + hashlib.sha1(ip.encode()).hexdigest()[:5],
                    "content": content, "image": path, "ts": now(), "uv": {}, "rep": [], "comments": [], "ip": ip}
            if board == "CF": post["web"], post["webnote"] = grade(content, bool(path))   # web chấm CHỈ ở CF
            S["posts"].insert(0, post); save()
            return self.out(pub_p(post, me), 201)

        m = re.fullmatch(r"/api/(posts|comments)/(\d+)/(vote|report|comments)", p)
        if not m: return self.out({"error": "Not found"}, 404)
        kind, i, act = m[1], int(m[2]), m[3]
        if not me: return self.out({"error": "Đăng nhập mới được vote / báo cáo / bình luận."}, 401)
        found = find(kind, i)
        if not found: return self.out({"error": "Không tìm thấy"}, 404)
        o, post = (found, found) if kind == "posts" else found

        if act == "comments" and kind == "posts":
            content = str(d.get("content", "")).strip()[:500]
            if not content: return self.out({"error": "Nội dung trống"}, 400)
            k = scan(content)
            if k: return self.caught(k, "comment", content, me)
            if S["muted"].get(me, 0) > now(): return self.out({"error": "Bạn đang bị NOOB: cấm bình luận 1 tuần."}, 403)
            par = d.get("parent")
            c = {"id": nid("cid"), "author": me, "content": content, "ts": now(), "uv": {}, "rep": [], "ip": ip,
                 "parent": par if par in [x["id"] for x in post["comments"]] else None}
            post["comments"].append(c); save()
            return self.out(pub_c(c, me), 201)

        if act == "vote":
            if o["author"] == me: return self.out({"error": "Tự vote cho bản thân à? Không nha."}, 403)
            v = 1 if int(d.get("value", 0)) > 0 else -1
            if o["uv"].get(me) == v: o["uv"].pop(me)    # bấm lại = bỏ vote
            else: o["uv"][me] = v
            save(); return self.out({"score": uscore(o)})

        if act == "report":
            if me in o["rep"]: return self.out({"error": "Bạn báo cáo rồi."}, 409)
            o["rep"].append(me)
            if len(o["rep"]) == LIM:                     # đủ 10 report → NOOB + cấm 1 tuần
                S["muted"][mkey(o["author"], o.get("ip", ""))] = now() + WEEK
            save(); return self.out({"reports": len(o["rep"])})
        self.out({"error": "Not found"}, 404)

if __name__ == "__main__":
    init_admin()
    print("Server running at http://127.0.0.1:8000")
    ThreadingHTTPServer(("127.0.0.1", 8000), H).serve_forever()