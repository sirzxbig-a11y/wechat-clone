#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
微信双开重签工具 · 本地网页面板

在本机起一个 HTTP 服务，浏览器打开后点按钮即可重签微信。
只监听 127.0.0.1，不对外网暴露；实际重签动作复用同目录（或上一级）的 resign-wechat.sh。
"""

import glob
import http.server
import json
import os
import socket
import subprocess
import threading
import time
import webbrowser

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
HTML_PATH = os.path.join(BASE_DIR, "index.html")

# resign-wechat.sh：优先同目录，其次上一级目录
SCRIPT_CANDIDATES = [
    os.path.join(BASE_DIR, "resign-wechat.sh"),
    os.path.join(os.path.dirname(BASE_DIR), "resign-wechat.sh"),
]
SCRIPT = next((p for p in SCRIPT_CANDIDATES if os.path.isfile(p)), SCRIPT_CANDIDATES[0])

MAIN_APP = "/Applications/WeChat.app"
WORK_APP = "/Applications/工作微信.app"
MAIN_DOC = os.path.expanduser("~/Library/Containers/com.tencent.xinWeChat/Data/Documents")
WORK_FILES = os.path.expanduser("~/Library/Containers/com.mywork.wechat/Data/Documents/xwechat_files")


def run(cmd, timeout=600):
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return p.returncode, (p.stdout or ""), (p.stderr or "")
    except subprocess.TimeoutExpired:
        return 124, "", "执行超时"
    except Exception as e:
        return 1, "", str(e)


def plist_get(app, key):
    code, out, _ = run(["/usr/libexec/PlistBuddy", "-c", "Print :" + key,
                        os.path.join(app, "Contents", "Info.plist")], timeout=20)
    return out.strip() if (code == 0 and out.strip()) else None


def sig_kind(app):
    code, out, err = run(["codesign", "-dv", app], timeout=20)
    text = (out or "") + (err or "")
    if "Authority=Apple Mac OS Application Signing" in text:
        return "appstore"
    if "Signature=adhoc" in text:
        return "adhoc"
    return "unknown"


def app_status(app):
    if not os.path.isdir(app):
        return {"exists": False, "path": app, "backup": bool(glob.glob(app + ".orig*"))}
    return {
        "exists": True,
        "path": app,
        "bundle_id": plist_get(app, "CFBundleIdentifier"),
        "version": plist_get(app, "CFBundleShortVersionString"),
        "build": plist_get(app, "CFBundleVersion"),
        "signature": sig_kind(app),
        "backup": bool(glob.glob(app + ".orig*")),
    }


def link_target(path):
    if os.path.islink(path):
        try:
            return os.readlink(path)
        except Exception:
            return None
    if os.path.isdir(path):
        return "(真实目录)"
    return None


def get_status():
    return {
        "script": SCRIPT if os.path.isfile(SCRIPT) else None,
        "main": app_status(MAIN_APP),
        "work": app_status(WORK_APP),
        "data": {
            "main_documents": {"path": MAIN_DOC, "target": link_target(MAIN_DOC)},
            "work_xwechat_files": {"path": WORK_FILES, "target": link_target(WORK_FILES)},
        },
    }


def resign(mode):
    if not os.path.isfile(SCRIPT):
        return {"ok": False, "output": "找不到 resign-wechat.sh，请把它放到本工具目录或上一级目录。"}
    code, out, err = run(["bash", SCRIPT, mode], timeout=900)
    output = out + ("\n" + err if err.strip() else "")
    return {"ok": code == 0, "code": code, "output": output.strip()}


def rollback(which):
    app = MAIN_APP if which == "main" else WORK_APP
    orig = app + ".orig"
    if not os.path.isdir(orig):
        return {"ok": False, "output": "找不到备份：%s" % orig}

    # 先退出正在运行的同名实例
    run(["pkill", "-TERM", "-f", app], timeout=15)
    time.sleep(2)
    run(["pkill", "-KILL", "-f", app], timeout=15)

    # 当前应用挪到一边（保留，不删除）
    if os.path.isdir(app):
        aside = "%s.rollback-%s" % (app, time.strftime("%Y%m%d-%H%M%S"))
        code, out, err = run(["mv", app, aside], timeout=60)
        if code != 0:
            return {"ok": False, "output": "移走当前应用失败：%s%s" % (out, err)}

    code, out, err = run(["mv", orig, app], timeout=60)
    if code != 0:
        return {"ok": False, "output": "恢复备份失败：%s%s" % (out, err)}
    return {"ok": True, "output": "已回滚：%s" % app}


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def _send(self, code, body, ctype="application/json"):
        data = body.encode("utf-8") if isinstance(body, str) else body
        try:
            self.send_response(code)
            self.send_header("Content-Type", ctype + "; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)
        except Exception:
            pass

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path in ("/", "/index.html"):
            try:
                with open(HTML_PATH, "r", encoding="utf-8") as f:
                    self._send(200, f.read(), "text/html")
            except Exception as e:
                self._send(500, "<h1>无法读取 index.html</h1><pre>%s</pre>" % e, "text/html")
        elif path == "/api/status":
            self._send(200, json.dumps(get_status(), ensure_ascii=False))
        elif path == "/favicon.ico":
            self._send(204, b"", "image/x-icon")
        else:
            self._send(404, json.dumps({"error": "not found"}, ensure_ascii=False))

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0") or "0")
        raw = self.rfile.read(length) if length else b"{}"
        try:
            params = json.loads(raw.decode("utf-8") or "{}")
        except Exception:
            params = {}
        path = self.path.split("?", 1)[0]

        if path == "/api/resign":
            mode = params.get("mode", "both")
            if mode not in ("main", "work", "both"):
                self._send(400, json.dumps({"ok": False, "output": "非法参数 mode"}, ensure_ascii=False))
                return
            result = resign(mode)
            result["status"] = get_status()
            self._send(200, json.dumps(result, ensure_ascii=False))
        elif path == "/api/rollback":
            which = params.get("which", "main")
            if which not in ("main", "work"):
                self._send(400, json.dumps({"ok": False, "output": "非法参数 which"}, ensure_ascii=False))
                return
            result = rollback(which)
            result["status"] = get_status()
            self._send(200, json.dumps(result, ensure_ascii=False))
        else:
            self._send(404, json.dumps({"error": "not found"}, ensure_ascii=False))


def pick_port(start=8899):
    for p in range(start, start + 30):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind(("127.0.0.1", p))
            return p
        except OSError:
            continue
        finally:
            s.close()
    return start


_env_port = os.environ.get("PORT", "").strip()
PORT = int(_env_port) if _env_port.isdigit() else pick_port(8899)


def main():
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    httpd.daemon_threads = True
    url = "http://127.0.0.1:%d/" % PORT
    print("=" * 54)
    print(" 微信双开重签工具已启动")
    print(" 浏览器打开： %s" % url)
    print(" 关闭本窗口或按 Ctrl+C 即可停止")
    print("=" * 54)
    if os.environ.get("NO_BROWSER") != "1":
        threading.Timer(0.7, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止。")
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()
