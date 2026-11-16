"""test_server.py - chạy:  python3 -m unittest -v test_server
Mỗi test dùng thư mục tạm + server thật chạy ở cổng ngẫu nhiên, không đụng vào data.json của bạn.
"""
import base64, http.client, json, os, tempfile, threading, time, unittest
from http.server import ThreadingHTTPServer
from pathlib import Path

os.environ["IHY_ADMIN_PASS"] = "adminpass"
import server

PNG = "data:image/png;base64," + base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"0" * 32).decode()  # chỉ cần đúng magic bytes
b64 = lambda b: base64.b64encode(b).decode()

class T(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        tmp = Path(tempfile.mkdtemp())
        server.DATA, server.UP = tmp / "data.json", tmp / "uploads"; server.UP.mkdir()
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.H)
        cls.port = cls.httpd.server_address[1]
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls): cls.httpd.shutdown()

    def setUp(self):  # reset toàn bộ trạng thái trước mỗi test
        server.S.clear(); server.S.update({"users": {}, "posts": [], "banned": {}, "muted": {}, "gt": {}, "pid": 1, "cid": 1})
        server.fails.clear(); server.sessions.clear(); server.init_admin()

    # ----- helpers -----
    def req(self, method, path, body=None, sid=None, ua="unittest"):
        c = http.client.HTTPConnection("127.0.0.1", self.port)
        h = {"User-Agent": ua}
        if body is not None: h["Content-Type"] = "application/json"
        if sid: h["Cookie"] = "sid=" + sid
        c.request(method, path, json.dumps(body) if body is not None else None, h)
        r = c.getresponse(); raw = r.read().decode()
        try: data = json.loads(raw)
        except ValueError: data = raw
        return r.status, data, r.getheader("Set-Cookie")

    def user(self, name, pw="secret1"):
        """Đăng ký và trả về session id."""
        return self.req("POST", "/api/register", {"username": name, "password": pw})[2].split(";")[0][4:]

    def admin(self):
        return self.req("POST", "/api/login", {"username": "admin", "password": "adminpass"})[2].split(";")[0][4:]

    def post(self, sid, content="hello", **kw):
        return self.req("POST", "/api/posts", {"board": "r", "content": content, **kw}, sid)

    # ----- ban IP: khách spam -----
    def test_guest_one_post_then_ban(self):
        codes = [self.post(None)[0] for _ in range(12)]
        self.assertEqual(codes[0], 201)
        self.assertTrue(all(c == 429 for c in codes[1:10]))      # lần 2..10: bị từ chối
        self.assertEqual(codes[10], 403)                          # lần 11: ban IP
        self.assertEqual(self.req("GET", "/api/boards")[0], 403)  # từ giờ mọi request đều 403

    # ----- ban IP: bruteforce mật khẩu -----
    def test_bruteforce_ban(self):
        self.user("victim")
        codes = [self.req("POST", "/api/login", {"username": "victim", "password": "sai"})[0] for _ in range(11)]
        self.assertEqual(codes[:10], [401] * 10)
        self.assertEqual(codes[10], 403)
        self.assertEqual(self.req("GET", "/api/boards")[0], 403)

    # ----- upload ảnh -----
    def test_upload_valid_png(self):
        st, d, _ = self.post(self.user("alice"), "ảnh", image=PNG)
        self.assertEqual(st, 201); self.assertTrue(d["image"].startswith("/uploads/"))
        self.assertEqual(self.req("GET", d["image"])[0], 200)

    def test_upload_bad_format_gets_rickroll(self):
        sid = self.user("alice")
        svg = "data:image/svg+xml;base64," + b64(b"<svg onload=alert(1)>")
        fake = "data:image/jpeg;base64," + b64(b"\x89PNG\r\n\x1a\n" + b"0" * 8)   # khai jpeg nhưng ruột là png
        for img in (svg, fake, "data:image/png;base64,@@@"):
            st, d, _ = self.post(sid, "x", image=img)
            self.assertEqual(st, 415); self.assertIn("youtube.com", d["rickroll"])

    # ----- payload -> troll + ghi danh BXH Chí Fèo 4.0 -----
    def test_payloads_are_caught(self):
        sid = self.user("hax")
        payloads = ["<script>alert(1)</script>", "' OR 1=1 --", "1 UNION SELECT password FROM users", '{"$ne": null}',
                    "{{7*7}}", '<!DOCTYPE x [<!ENTITY y SYSTEM "file:///etc/passwd">]>', "../../etc/passwd", "; cat /etc/passwd"]
        for pl in payloads:
            st, d, _ = self.post(sid, pl)
            self.assertEqual(st, 403, pl); self.assertIn("troll", d)
        lb = self.req("GET", "/api/leaderboard?type=cf4")[1]
        self.assertEqual(lb[0]["author"], "hax"); self.assertEqual(lb[0]["attempts"], len(payloads))
        self.assertEqual(self.req("GET", "/api/profile?u=hax")[1]["frame"], "hacker")

    def test_scanner_user_agent(self):
        st, d, _ = self.req("GET", "/api/boards", ua="sqlmap/1.7")
        self.assertEqual(st, 403); self.assertIn("troll", d)

    def test_honeypot_shows_rickroll_image_and_is_logged(self):
        st, html, _ = self.req("GET", "/api/admin")
        self.assertEqual(st, 200); self.assertIn("rickroll.gif", html)
        self.assertEqual(self.req("GET", "/api/mod/log", sid=self.admin())[1][0]["kind"], "honey")

    # ----- báo cáo -> NOOB -----
    def test_ten_reports_make_noob(self):
        author = self.user("victim"); pid = self.post(author)[1]["id"]
        for i in range(10):
            self.assertEqual(self.req("POST", f"/api/posts/{pid}/report", {}, self.user(f"rep{i}"))[0], 200)
        self.assertEqual(self.post(author)[0], 403)   # bị chặn đăng 1 tuần
        self.assertEqual(self.req("GET", "/api/profile?u=victim")[1]["frame"], "noob")

    # ----- khách không vote/comment -----
    def test_guest_cannot_vote(self):
        pid = self.post(self.user("a"))[1]["id"]
        self.assertEqual(self.req("POST", f"/api/posts/{pid}/vote", {"value": 1})[0], 401)

    # ----- phân trang, sửa/xóa, đổi mật khẩu -----
    def test_pagination(self):
        sid = self.user("a")
        for i in range(25): self.post(sid, f"bài {i}")
        d = self.req("GET", "/api/posts?size=10&page=3")[1]
        self.assertEqual((d["page"], d["pages"], len(d["items"])), (3, 3, 5))

    def test_edit_delete_permissions(self):
        a, b = self.user("a"), self.user("b"); pid = self.post(a, "gốc")[1]["id"]
        self.assertEqual(self.req("POST", f"/api/posts/{pid}/edit", {"content": "hack"}, b)[0], 403)
        self.assertEqual(self.req("POST", f"/api/posts/{pid}/edit", {"content": "mới"}, a)[1]["content"], "mới")
        self.assertEqual(self.req("POST", f"/api/posts/{pid}/delete", {}, a)[0], 200)
        self.assertEqual(self.req("GET", "/api/posts")[1]["items"], [])

    def test_change_password(self):
        sid = self.user("a", "oldpass1")
        self.assertEqual(self.req("POST", "/api/password", {"old": "sai", "new": "newpass1"}, sid)[0], 403)
        self.assertEqual(self.req("POST", "/api/password", {"old": "oldpass1", "new": "newpass1"}, sid)[0], 200)
        self.assertEqual(self.req("POST", "/api/login", {"username": "a", "password": "newpass1"})[0], 200)

    # ----- admin -----
    def test_admin_unban_and_permissions(self):
        server.S["banned"]["1.2.3.4"] = time.time() + 3600   # IP khác (admin không thể tự gỡ ban IP của chính mình)
        self.assertEqual(self.req("GET", "/api/mod/bans", sid=self.user("normal"))[0], 403)   # user thường bị từ chối
        sid = self.admin()
        self.assertEqual(self.req("GET", "/api/mod/bans", sid=sid)[1][0]["ip"], "1.2.3.4")
        self.assertEqual(self.req("POST", "/api/mod/unban", {"ip": "1.2.3.4"}, sid)[0], 200)
        self.assertEqual(self.req("GET", "/api/mod/bans", sid=sid)[1], [])

if __name__ == "__main__":
    unittest.main()
