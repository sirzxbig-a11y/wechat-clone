#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
微信双开重签工具 · 本地网页面板

在本机起一个 HTTP 服务，浏览器打开后点按钮即可重签微信 / 创建多开。
只监听 127.0.0.1，不对外网暴露；实际重签动作复用同目录（或上一级）的 resign-wechat.sh。
"""

import glob
import http.server
import json
import os
import socket
import subprocess
import tempfile
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

CLONE_PREFIX = "com.mywork.wechat"


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


def list_clones():
    """列出 /Applications 下所有「多开」副本（bundle id 以 com.mywork.wechat 开头，且不是固定工作微信）。"""
    clones = []
    for d in sorted(glob.glob("/Applications/*.app")):
        bid = plist_get(d, "CFBundleIdentifier") or ""
        if bid.startswith(CLONE_PREFIX) and bid != "com.mywork.wechat":
            clones.append({
                "path": d,
                "name": os.path.basename(d)[:-4] if d.endswith(".app") else os.path.basename(d),
                "bundle_id": bid,
                "version": plist_get(d, "CFBundleShortVersionString"),
                "signature": sig_kind(d),
            })
    return clones


def next_bundle_id():
    existing = set()
    for d in glob.glob("/Applications/*.app"):
        bid = plist_get(d, "CFBundleIdentifier")
        if bid:
            existing.add(bid)
    i = 2
    while True:
        bid = "%s%d" % (CLONE_PREFIX, i)
        if bid not in existing:
            return bid
        i += 1


def get_status():
    return {
        "script": SCRIPT if os.path.isfile(SCRIPT) else None,
        "main": app_status(MAIN_APP),
        "work": app_status(WORK_APP),
        "clones": list_clones(),
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


def create_clone(name, bundle_id=None):
    """从主微信复制一个副本、改 bundle id、ad-hoc 重签，得到一个新的多开微信。"""
    name = (name or "").strip()
    if not name:
        return {"ok": False, "output": "请输入副本名称（如：微信3）"}
    if "/" in name or ":" in name or name.startswith("."):
        return {"ok": False, "output": "副本名称不能包含 / : 或以 . 开头"}
    target = "/Applications/%s.app" % name
    if os.path.exists(target):
        return {"ok": False, "output": "已存在同名应用：%s" % target}
    if not os.path.isdir(MAIN_APP):
        return {"ok": False, "output": "找不到主微信：%s" % MAIN_APP}

    bid = (bundle_id or "").strip() or next_bundle_id()

    work = tempfile.mkdtemp(prefix="wechat-clone-")
    tmp_app = os.path.join(work, "%s.app" % name)
    try:
        code, out, err = run(["ditto", MAIN_APP, tmp_app], timeout=300)
        if code != 0:
            return {"ok": False, "output": "复制失败：%s%s" % (out, err)}
        run(["chmod", "-R", "u+w", tmp_app], timeout=120)

        code, out, err = run(["/usr/libexec/PlistBuddy", "-c",
                              "Set :CFBundleIdentifier %s" % bid,
                              os.path.join(tmp_app, "Contents", "Info.plist")], timeout=30)
        if code != 0:
            return {"ok": False, "output": "设置 bundle id 失败：%s%s" % (out, err)}

        ent = os.path.join(work, "empty.plist")
        with open(ent, "w") as f:
            f.write('<?xml version="1.0" encoding="UTF-8"?>\n'
                    '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" '
                    '"http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
                    '<plist version="1.0"><dict/></plist>\n')

        code, out, err = run(["codesign", "--force", "--deep", "--sign", "-",
                              "--entitlements", ent, tmp_app], timeout=600)
        if code != 0:
            return {"ok": False, "output": "重签名失败：%s%s" % (out, err)}

        code, out, err = run(["codesign", "--verify", "--deep", "--strict", tmp_app], timeout=120)
        if code != 0:
            return {"ok": False, "output": "签名校验失败：%s%s" % (out, err)}

        code, out, err = run(["mv", tmp_app, target], timeout=120)
        if code != 0:
            return {"ok": False, "output": "安装失败：%s%s" % (out, err)}

        return {
            "ok": True,
            "app": target,
            "bundle_id": bid,
            "output": "已创建多开微信：%s\nbundle id: %s\n到「应用程序」双击打开，登录你要开的账号即可。"
                      % (target, bid),
        }
    finally:
        run(["rm", "-rf", work], timeout=60)


def open_app(app):
    if not (app.startswith("/Applications/") and app.endswith(".app") and os.path.isdir(app)):
        return {"ok": False, "output": "非法应用路径"}
    run(["open", app], timeout=30)
    return {"ok": True, "output": "已打开：%s" % app}


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
        elif path == "/api/create":
            name = params.get("name", "")
            bid = params.get("bundle_id") or None
            result = create_clone(name, bid)
            result["status"] = get_status()
            self._send(200, json.dumps(result, ensure_ascii=False))
        elif path == "/api/open":
            app = params.get("path", "")
            result = open_app(app)
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
