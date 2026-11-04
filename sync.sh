#!/bin/bash
#
# 一键同步：把本地改动提交并推送到 GitHub
#
# 用法：
#   ./sync.sh                  # 使用默认提交信息
#   ./sync.sh "feat: 改了xxx"   # 自定义提交信息
#
set -euo pipefail
cd "$(dirname "$0")"

MSG="${1:-chore: sync}"

if [ -z "$(git status --porcelain)" ]; then
  echo "[i] 没有本地改动。"
else
  echo "[+] 提交本地改动：$MSG"
  git add -A
  git commit -m "$MSG"
fi

echo "[+] 推送到 origin/main ..."
git push origin main
echo "[✓] 已同步到 GitHub"
