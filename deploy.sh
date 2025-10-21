#!/usr/bin/env bash

echo "🚀 开始自动部署 CALDROS-GTO ..."

# 1️⃣ 烟雾测试
python3 tests/smoke_test.py || { echo "❌ 烟雾测试失败，终止部署"; exit 1; }

# 2️⃣ 构建 Docker 镜像
docker build -t caldros_gto:latest .

# 3️⃣ 启动本地容器（开发调试用）
docker run -d -p 8080:8080 caldros_gto:latest

# 4️⃣ 部署到 Zeabur（或远程服务器）
# ⚠️ 若使用 Zeabur CLI，可替换以下命令：
# zeabur deploy --image caldros_gto:latest --project caldros-gto

echo "✅ 部署完成！服务运行在端口 8080"
