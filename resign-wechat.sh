#!/usr/bin/env bash
#
# =============================================================================
#  微信 Mac 双开一键重签名脚本
#  WeChat (macOS) double-instance re-signing script
# =============================================================================
#
#  背景 / Why:
#    App Store 更新微信后，官方「沙盒版」会因为聊天记录软链接到外置硬盘而导致
#    启动崩溃（沙盒容器完整性检查失败，报 "failed integrity checks for container"）。
#    本脚本把微信重新 ad-hoc 签名（去掉 com.apple.security.app-sandbox 沙盒授权），
#    并同步把「工作微信」副本更新到与主微信相同的版本。
#
#  用法 / Usage:
#    ./resign-wechat.sh           # 默认：重签主微信 + 更新工作微信
#    ./resign-wechat.sh main      # 只重签主微信
#    ./resign-wechat.sh work      # 只更新工作微信（基于当前主微信版本）
#    ./resign-wechat.sh status    # 仅查看当前状态，不做任何修改
#
#  注意 / Note:
#    - 重签名后无法再通过 Mac App Store 自动更新；每次更新后需重跑本脚本。
#    - 本脚本只操作 .app 本体，不修改聊天记录 / 软链接 / 容器数据。
#    - 原版会自动备份为 <app>.orig，可随时改回名字回滚。
#    - 无需 sudo：要求当前用户属于 admin 组（macOS 默认即是）。
#
# =============================================================================

set -euo pipefail

# ---------------------------------------------------------------------------
# 配置区（按你的实际情况修改）
# ---------------------------------------------------------------------------
MAIN_APP="/Applications/WeChat.app"        # 主微信
WORK_APP="/Applications/工作微信.app"        # 工作微信（双开副本）
WORK_BUNDLE_ID="com.mywork.wechat"          # 工作微信 bundle id（自定义，须与主不同）
# ---------------------------------------------------------------------------

MODE="${1:-both}"

# ---- 输出辅助 ----
info()  { printf '\033[1;32m[+]\033[0m %s\n' "$*"; }
warn()  { printf '\033[1;33m[!]\033[0m %s\n' "$*"; }
error() { printf '\033[1;31m[-]\033[0m %s\n' "$*" >&2; }
step()  { printf '\n\033[1;36m==>\033[0m %s\n' "$*"; }

TMP_ROOT="$(mktemp -d /tmp/wechat-resign.XXXXXX)"
trap 'rm -rf "$TMP_ROOT"' EXIT

bundle_id_of() {
  /usr/libexec/PlistBuddy -c 'Print :CFBundleIdentifier' "$1/Contents/Info.plist" 2>/dev/null || echo '(none)'
}
version_of() {
  /usr/libexec/PlistBuddy -c 'Print :CFBundleShortVersionString' "$1/Contents/Info.plist" 2>/dev/null || echo '(none)'
}
sig_kind_of() {
  local out
  out="$(codesign -dv "$1" 2>&1 || true)"
  if   printf '%s' "$out" | grep -q 'Authority=Apple Mac OS Application Signing'; then echo 'AppStore沙盒版'
  elif printf '%s' "$out" | grep -q 'Signature=adhoc';                  then echo 'ad-hoc(已重签)'
  else echo '未知'
  fi
}

quit_app() {
  local app_path="$1"
  if pgrep -f "$app_path" >/dev/null 2>&1; then
    info "正在退出 $app_path ..."
    pkill -TERM -f "$app_path" 2>/dev/null || true
    local _i
    for _i in 1 2 3 4 5 6; do
      sleep 1
      pgrep -f "$app_path" >/dev/null 2>&1 || break
    done
    if pgrep -f "$app_path" >/dev/null 2>&1; then
      warn "未能优雅退出，强制结束"
      pkill -KILL -f "$app_path" 2>/dev/null || true
      sleep 1
    fi
  fi
}

# 核心：复制 source_app → (可选改 bundle id) → ad-hoc 重签 → 装回 target_app
resign() {
  local source_app="$1"
  local target_app="$2"
  local new_bundle_id="${3:-}"

  [ -d "$source_app" ] || { error "源应用不存在: $source_app"; exit 1; }

  local ver target_bid
  ver="$(version_of "$source_app")"
  target_bid="$(bundle_id_of "$source_app")"
  [ -n "$new_bundle_id" ] && target_bid="$new_bundle_id"

  info "处理: $(basename "$source_app") -> $(basename "$target_app")  (bundle: $target_bid | v$ver)"

  # 1. 复制到临时目录（当前用户可写，避免 root 权限问题）
  local tmp_app="$TMP_ROOT/$(basename "$target_app")"
  ditto "$source_app" "$tmp_app"
  chmod -R u+w "$tmp_app"

  # 2. 修改 bundle id（仅工作微信需要）
  if [ -n "$new_bundle_id" ]; then
    /usr/libexec/PlistBuddy -c "Set :CFBundleIdentifier $new_bundle_id" "$tmp_app/Contents/Info.plist"
    info "  已设置 CFBundleIdentifier = $new_bundle_id"
  fi

  # 3. 空 entitlements（去沙盒）
  local ent="$TMP_ROOT/empty.plist"
  cat > "$ent" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict/></plist>
PLIST

  # 4. ad-hoc 重签名
  codesign --force --deep --sign - --entitlements "$ent" "$tmp_app"
  info "  已 ad-hoc 重签名（去沙盒）"

  # 5. 校验签名与沙盒授权
  codesign --verify --deep --strict "$tmp_app"
  if codesign -d --entitlements - "$tmp_app" 2>/dev/null | grep -q 'com.apple.security.app-sandbox'; then
    error "  沙盒授权仍存在，重签名异常，中止"
    exit 1
  fi
  info "  校验通过：沙盒已移除"

  # 6. 备份原版并替换（用 mv 改名，无需删 root 所有的旧文件）
  if [ -e "$target_app" ]; then
    local bak="$target_app.orig"
    if [ -e "$bak" ]; then
      mv "$bak" "$bak.$(date +%Y%m%d-%H%M%S)"
    fi
    mv "$target_app" "$bak"
    info "  原版已备份: $bak"
  fi
  mv "$tmp_app" "$target_app"
  info "  已安装: $target_app (bundle: $(bundle_id_of "$target_app") | v$(version_of "$target_app") | $(sig_kind_of "$target_app"))"
}

show_status() {
  local app
  for app in "$MAIN_APP" "$WORK_APP"; do
    if [ -d "$app" ]; then
      printf '  %-24s  bundle=%-24s  v%-8s  %s\n' \
        "$(basename "$app")" "$(bundle_id_of "$app")" "$(version_of "$app")" "$(sig_kind_of "$app")"
    else
      printf '  %-24s  (不存在)\n' "$(basename "$app")"
    fi
  done
}

case "$MODE" in
  status)
    echo '当前状态:'
    show_status
    exit 0
    ;;
  main)
    quit_app "$MAIN_APP"
    resign "$MAIN_APP" "$MAIN_APP"
    ;;
  work)
    quit_app "$WORK_APP"
    resign "$MAIN_APP" "$WORK_APP" "$WORK_BUNDLE_ID"
    ;;
  both)
    quit_app "$MAIN_APP"
    quit_app "$WORK_APP"
    resign "$MAIN_APP" "$MAIN_APP"
    resign "$MAIN_APP" "$WORK_APP" "$WORK_BUNDLE_ID"
    ;;
  *)
    error "未知参数: ${MODE}（可选 main / work / both / status）"
    exit 1
    ;;
esac

step '完成'
show_status
echo
echo '提示：'
echo "  启动主微信:   open \"$MAIN_APP\""
echo "  启动工作微信: open \"$WORK_APP\""
echo '  回滚: 把 *.orig 改回原应用名即可'
