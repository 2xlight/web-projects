from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import random
from pathlib import Path

# Cấu trúc dữ liệu: Phân loại theo Board (nhóm)
boards = {
    "r": {"name": "Random - nói gì cũng được.", "desc": "Bạn nói tui nghe coi-"},
    "it": {"name": "Technology - RAM, vibe-coding,...", "desc": "About công nghệ nhưng không cần thượng đẳng."},
    "CF": {"name": "Confession - Chí Fèo", "desc": "Chắc nó không chừa mình ra."},
    "Stu": {"name": "Study - Học, học nữa, học mãi", "desc": "Tìm nhóm học, bàn về học, khoe cái học."},
    "W": {"name": "Work - Thất thất nghiệp", "desc": "Thất thất nghiệp"}
}

# Kho lưu trữ bài viết mẫu
posts = [
    {
        "id": 1,
        "board": "b",
        "author": "Áp-min",
        "score": 0,
        "content": "Hello mấy cưng.",
        "comments": [
            {"author": "Hệ thống", "content": "Mở màn thế là ổn đấy."}
        ]
    }
]
post_id_counter = 2

class Handler(BaseHTTPRequestHandler):

    def send_json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        global posts, boards
        
        # Lấy danh sách boards
        if self.path == "/api/boards":
            self.send_json(boards)
            return

        # Lấy danh sách bài viết (có thể lọc theo board ?board=b)
        if self.path.startswith("/api/posts"):
            self.send_json(posts)
            return

        # Lấy Bảng xếp hạng (Leaderboard) dựa trên tổng điểm người dùng
        if self.path == "/api/leaderboard":
            user_scores = {}
            for p in posts:
                author = p["author"]
                user_scores[author] = user_scores.get(author, 0) + p["score"]
            
            # Sắp xếp giảm dần theo điểm
            sorted_users = sorted(user_scores.items(), key=lambda x: x[1], reverse=True)
            leaderboard = [{"rank": i+1, "author": u[0], "score": u[1]} for i, u in enumerate(sorted_users)]
            self.send_json(leaderboard)
            return
        # [TÍNH NĂNG MỚI] Bẫy Admin - Dụ hack web bằng Rickroll
        if self.path == "/api/admin":
            self.send_json({
                "message": "Ghê vậy sao? Định bypass hệ thống à cưng?",
                "secret_gift": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
            })
            return
        if self.path == "/" or self.path == "/index.html":
            self.send_file("ihateyou.html")
            return

        self.send_json({"error": "Not found"}, 404)

    def do_POST(self):
        global posts, post_id_counter

        # 1. Đăng bài viết mới + Phát hiện payload/Burpsuite
        if self.path == "/api/posts":
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length)
            data = json.loads(body)
            
            board = data.get("board", "b")
            author = data.get("author", "Ẩn danh").strip() or "Ẩn danh"
            content = data.get("content", "").strip()
            
            if not content:
                self.send_json({"error": "Nội dung trống"}, 400)
                return

            # [TÍNH NĂNG MỚI] Check xem có đang chèn payload (XSS/SQLi) hoặc táy máy Burpsuite không
            danger_keywords = ["<script>", "or 1=1", "select", "union", "drop", "alert", "eval(", "burp"]
            is_hacking = any(kw in content.lower() for kw in danger_keywords)
            
            if is_hacking:
                score = 9999 # Thưởng điểm cực mạnh cho hacker múa rìu qua mắt thợ
                content = f"[⚠️ CẢNH BÁO HACKER PÉN] {content} (Đã được ghi danh vào bảng vàng phá hoại!)"
            else:
                score = random.randint(10, 100)

            new_post = {
                "id": post_id_counter,
                "board": board,
                "author": author,
                "score": score,
                "content": content,
                "reports": 0,
                "comments": []
            }
            posts.insert(0, new_post)
            post_id_counter += 1
            
            self.send_json(new_post, 201)
            return

        # 2. [ĐÃ SỬA] API Vote điểm bài viết (+1 hoặc -1)
        if self.path.startswith("/api/posts/") and self.path.endswith("/vote"):
            try:
                parts = self.path.split("/")
                post_id = int(parts[3])
                length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(length)
                data = json.loads(body)
                val = int(data.get("value", 0))

                for post in posts:
                    if post["id"] == post_id:
                        if val > 0:
                            post["score"] += 1
                        elif val < 0:
                            post["score"] -= 1
                        self.send_json({"success": True, "score": post["score"]})
                        return
                self.send_json({"error": "Post not found"}, 404)
            except Exception:
                self.send_json({"error": "Invalid request"}, 400)
            return

        # 3. Report bài viết
        if self.path.startswith("/api/posts/") and self.path.endswith("/report"):
            try:
                post_id = int(self.path.split("/")[3])
                for post in posts:
                    if post["id"] == post_id:
                        post["reports"] += 1
                        if post["reports"] >= 5:
                            post["score"] = -999 # Đẩy xuống đáy xã hội
                        self.send_json({"success": True, "reports": post["reports"]})
                        return
                self.send_json({"error": "Post not found"}, 404)
            except Exception:
                self.send_json({"error": "Invalid request"}, 400)
            return

        # 4. Gửi bình luận
        if self.path.startswith("/api/posts/") and self.path.endswith("/comments"):
            try:
                post_id = int(self.path.split("/")[3])
                length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(length)
                data = json.loads(body)
                
                author = data.get("author", "Ẩn danh").strip() or "Ẩn danh"
                content = data.get("content", "").strip()
                
                if not content:
                    self.send_json({"error": "Nội dung trống"}, 400)
                    return

                for post in posts:
                    if post["id"] == post_id:
                        comment = {"author": author, "content": content}
                        post["comments"].append(comment)
                        self.send_json(comment, 201)
                        return
                self.send_json({"error": "Post not found"}, 404)
            except ValueError:
                self.send_json({"error": "Invalid ID"}, 400)
            return

        self.send_json({"error": "Not found"}, 404)

    def send_file(self, filename, content_type="text/html"):
        path = Path(filename)
        if not path.exists():
            self.send_json({"error": "File not found"}, 404)
            return
        body = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

server = HTTPServer(("127.0.0.1", 8000), Handler)
print("Server running at http://127.0.0.1:8000")
server.serve_forever()