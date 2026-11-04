import Cocoa
import WebKit
import Darwin

final class AppDelegate: NSObject, NSApplicationDelegate {
    private var window: NSWindow!
    private var webView: WKWebView!
    private var server: Process?
    private var port: Int = 8899

    func applicationDidFinishLaunching(_ notification: Notification) {
        buildMenu()
        port = Self.findFreePort(start: 8899)
        startServer()
        waitForServer { [weak self] ok in
            DispatchQueue.main.async {
                guard let self = self else { return }
                self.buildWindow()
                if !ok {
                    let html = "<html><body style=\"font-family:-apple-system;padding:40px\">" +
                        "<h1>本地服务启动失败</h1>" +
                        "<p style=\"color:#888\">请确认系统自带的 python3 可用，并重新打开本应用。</p>" +
                        "</body></html>"
                    self.webView.loadHTMLString(html, baseURL: nil)
                }
            }
        }
    }

    private func buildMenu() {
        let mainMenu = NSMenu()
        let appItem = NSMenuItem()
        mainMenu.addItem(appItem)
        let appMenu = NSMenu()
        appMenu.addItem(withTitle: "退出微信双开重签工具",
                        action: #selector(NSApplication.terminate(_:)),
                        keyEquivalent: "q")
        appItem.submenu = appMenu
        NSApp.mainMenu = mainMenu
    }

    private static func findFreePort(start: Int) -> Int {
        for p in start..<(start + 40) {
            let fd = socket(AF_INET, SOCK_STREAM, 0)
            if fd < 0 { continue }
            var addr = sockaddr_in()
            addr.sin_family = sa_family_t(AF_INET)
            addr.sin_addr.s_addr = inet_addr("127.0.0.1")
            addr.sin_port = in_port_t(UInt16(p).bigEndian)
            let res: Int32 = withUnsafePointer(to: &addr) { ptr in
                ptr.withMemoryRebound(to: sockaddr.self, capacity: 1) { sptr in
                    Darwin.bind(fd, sptr, socklen_t(MemoryLayout<sockaddr_in>.size))
                }
            }
            close(fd)
            if res == 0 { return p }
        }
        return start
    }

    private func startServer() {
        guard let res = Bundle.main.resourcePath else { return }
        let script = res + "/server.py"
        let p = Process()
        p.executableURL = URL(fileURLWithPath: "/usr/bin/python3")
        p.arguments = [script]
        var env = ProcessInfo.processInfo.environment
        env["PORT"] = String(port)
        env["NO_BROWSER"] = "1"
        p.environment = env
        p.currentDirectoryURL = URL(fileURLWithPath: res)
        p.standardOutput = FileHandle.nullDevice
        p.standardError = FileHandle.nullDevice
        do {
            try p.run()
            server = p
        } catch {
            NSLog("start server failed: \(error)")
        }
    }

    private func waitForServer(_ completion: @escaping (Bool) -> Void) {
        var attempts = 0
        func check() {
            attempts += 1
            guard let url = URL(string: "http://127.0.0.1:\(port)/api/status") else {
                completion(false)
                return
            }
            var req = URLRequest(url: url)
            req.timeoutInterval = 1
            URLSession.shared.dataTask(with: req) { _, resp, _ in
                if let h = resp as? HTTPURLResponse, h.statusCode == 200 {
                    completion(true)
                } else if attempts < 60 {
                    DispatchQueue.global().asyncAfter(deadline: .now() + 0.2) { check() }
                } else {
                    completion(false)
                }
            }.resume()
        }
        check()
    }

    private func buildWindow() {
        let rect = NSRect(x: 0, y: 0, width: 620, height: 860)
        window = NSWindow(contentRect: rect,
                          styleMask: [.titled, .closable, .miniaturizable, .resizable],
                          backing: .buffered, defer: false)
        window.title = "微信双开重签工具"
        window.minSize = NSSize(width: 520, height: 600)
        window.center()
        window.isReleasedWhenClosed = false

        let config = WKWebViewConfiguration()
        webView = WKWebView(frame: rect, configuration: config)
        webView.uiDelegate = self
        if let url = URL(string: "http://127.0.0.1:\(port)/") {
            webView.load(URLRequest(url: url))
        }
        window.contentView = webView
        window.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool {
        return true
    }

    func applicationWillTerminate(_ notification: Notification) {
        server?.terminate()
    }
}

extension AppDelegate: WKUIDelegate {
    func webView(_ webView: WKWebView,
                 runJavaScriptConfirmPanelWithMessage message: String,
                 initiatedByFrame frame: WKFrameInfo,
                 completionHandler: @escaping (Bool) -> Void) {
        let alert = NSAlert()
        alert.messageText = "确认"
        alert.informativeText = message
        alert.addButton(withTitle: "确定")
        alert.addButton(withTitle: "取消")
        completionHandler(alert.runModal() == .alertFirstButtonReturn)
    }

    func webView(_ webView: WKWebView,
                 runJavaScriptAlertPanelWithMessage message: String,
                 initiatedByFrame frame: WKFrameInfo,
                 completionHandler: @escaping () -> Void) {
        let alert = NSAlert()
        alert.messageText = "提示"
        alert.informativeText = message
        alert.addButton(withTitle: "好")
        alert.runModal()
        completionHandler()
    }
}

let app = NSApplication.shared
let delegate = AppDelegate()
app.delegate = delegate
app.setActivationPolicy(.regular)
app.run()
