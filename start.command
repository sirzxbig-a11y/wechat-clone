#!/bin/bash
# 双击运行：启动本地服务并自动打开浏览器
cd "$(dirname "$0")" || exit 1
exec /usr/bin/python3 server.py
