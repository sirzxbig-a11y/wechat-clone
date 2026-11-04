#!/bin/bash
# 把本地网页面板打包成原生 .app（Swift + WKWebView）
# 用法：./build-native.sh
set -euo pipefail

cd "$(dirname "$0")"
GUI_DIR="$(pwd)"
ROOT="$(cd .. && pwd)"

APP_NAME="微信双开重签工具"
BUNDLE="$GUI_DIR/$APP_NAME.app"

echo "[1/4] 编译 Swift ..."
rm -rf "$BUNDLE"
mkdir -p "$BUNDLE/Contents/MacOS" "$BUNDLE/Contents/Resources"
swiftc -O -o "$BUNDLE/Contents/MacOS/WeChatResign" \
    native/main.swift -framework WebKit -framework Cocoa

echo "[2/4] 拷贝 Info.plist 与资源 ..."
cp native/Info.plist "$BUNDLE/Contents/Info.plist"
cp server.py  "$BUNDLE/Contents/Resources/server.py"
cp index.html "$BUNDLE/Contents/Resources/index.html"
cp native/AppIcon.icns "$BUNDLE/Contents/Resources/AppIcon.icns"
# 优先用仓库内的 resign-wechat.sh；没有则回退到上一级目录
SCRIPT_SRC="$GUI_DIR/resign-wechat.sh"
[ -f "$SCRIPT_SRC" ] || SCRIPT_SRC="$ROOT/resign-wechat.sh"
cp "$SCRIPT_SRC" "$BUNDLE/Contents/Resources/resign-wechat.sh"

echo "[3/4] ad-hoc 签名 ..."
codesign --force --deep --sign - "$BUNDLE"

echo "[4/4] 完成：$BUNDLE"
