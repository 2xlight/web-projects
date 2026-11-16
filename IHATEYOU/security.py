"""security.py - phát hiện payload, phát hiện scanner qua User-Agent và kho câu troll.

Muốn thêm một loại tấn công mới: (1) thêm 1 regex vào PAT, (2) thêm vài câu vào TROLL cùng tên.
"""
import re
from urllib.parse import unquote

# Mỗi loại tấn công = 1 regex. scan() trả về tên loại đầu tiên khớp (thứ tự dict = thứ tự ưu tiên).
PAT = {
    # XSS: thẻ script, event handler, javascript:, thẻ img/svg/iframe, đánh cắp cookie
    "xss": r"<\s*script|\bon(error|load|click|mouseover|focus)\s*=|javascript:|<\s*(img|svg|iframe)[^>]*>|document\.cookie",
    # SQL injection: OR 1=1, UNION SELECT, DROP TABLE, ' OR ', '--, sleep(), information_schema
    "sqli": r"\b(or|and)\b\s+['\"]?\d+['\"]?\s*=\s*['\"]?\d+|union\s+select|drop\s+table|'\s*or\s*'|'\s*--|sleep\s*\(|information_schema",
    # NoSQL injection (MongoDB): toán tử $ne, $gt, $regex, $where...
    "nosqli": r"\$(ne|gt|gte|lt|lte|regex|where|or|and|in|nin|exists)\b",
    # SSTI (Jinja2/Twig {{7*7}}, {% %}, ${...}, <%= %>, #{...})
    "ssti": r"\{\{.*?\}\}|\{%.*?%\}|\$\{[^}]*\}|<%[=\s]|#\{[^}]*\}",
    # XXE: khai báo DOCTYPE/ENTITY, SYSTEM "file://..."
    "xxe": r"<!DOCTYPE|<!ENTITY|SYSTEM\s+[\"'](file|http|expect)",
    # Path traversal
    "path": r"\.\./|/etc/passwd|%2e%2e|\\windows\\",
    # Command injection
    "cmd": r";\s*(cat|ls|id|whoami)\b|\$\(|`[^`]+`|\|\s*(nc|bash|sh)\b",
}

# Các công cụ quét tự động hay lộ ra qua header User-Agent.
UA_PAT = r"sqlmap|nikto|nmap|nuclei|acunetix|dirbuster|gobuster|wfuzz|ffuf|hydra|masscan|zgrab|wpscan|burp"

def scan(text):
    """Trả về loại payload ('xss', 'sqli'...) nếu text khả nghi, ngược lại None. Decode URL trước khi so khớp."""
    t = unquote(str(text or ""))
    for kind, pat in PAT.items():
        if re.search(pat, t, re.I):
            return kind

def scan_ua(ua):
    """True nếu User-Agent trông giống công cụ quét lỗ hổng."""
    return bool(re.search(UA_PAT, ua or "", re.I))

# Câu troll: record() chọn ngẫu nhiên 1 câu theo loại. Tên khóa phải trùng PAT (+ 'honey', 'scanner').
TROLL = {
    "xss": ["XSS kiểu mầm non, alert(1) à? Năm 2010 gọi đòi payload.",
            "Chèn script mà quên là web đã escape sạch rồi hả cưng?",
            "<script> của bạn đã được dịch thành chữ thường. Chúc mừng!"],
    "sqli": ["' OR 1=1 -- Sách giáo khoa lớp 1 đúng không?",
             "Web này không có SQL đâu, dữ liệu nằm trong dict thôi :)",
             "UNION SELECT cái gì? Ở đây chỉ có union của mấy ông thất nghiệp."],
    "nosqli": ["$ne: null? Mongo cũng không có luôn nhé.", "Tưởng web dùng MongoDB à? Dùng json thôi bạn ơi."],
    "ssti": ["{{7*7}} = 49, còn bạn = 0 điểm.", "Template engine? Web này nối chuỗi bằng tay nhé."],
    "xxe": ["XML đâu mà XXE? Web này ăn JSON.", "<!ENTITY> à? Entity duy nhất ở đây là bạn."],
    "path": ["../../etc/passwd? Ở đây chỉ có passwd của... dì Ba.", "Lùi thêm vài thư mục nữa là ra khỏi nhà luôn đó."],
    "cmd": ["Command injection? Server đang cười.", "; cat /etc/shadow — shadow ở đây là bóng đèn thôi."],
    "honey": ["Vào được /admin rồi nè, quà đây 🎁", "Admin đây! Ủa nhầm, Rick đây."],
    "scanner": ["Scanner hả? Web này tự scan lại bạn rồi.", "User-Agent của bạn lộ hết rồi cưng ơi."],
}
NOTE_LO = ["Bài này hơi nhạt, web chấm cho có.", "Chí Phèo còn viết hay hơn.", "Web ngủ gật giữa chừng."]
NOTE_HI = ["Confession chất lượng, web gật gù.", "Đỉnh! Web suýt khóc.", "Web xin phép lưu lại làm kỷ niệm."]
