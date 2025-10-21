#!/bin/bash
echo "🚀 Deploying CALDROS-GTO to Zeabur..."

# Build Docker image
docker build -t caldros-gto .

# Push image to Zeabur container registry (自动连接你的 Zeabur 项目)
docker tag caldros-gto registry.zeabur.com/caldros-gto:latest
docker push registry.zeabur.com/caldros-gto:latest

# Optional: trigger redeploy hook (if configured)
curl -X POST $ZEABUR_DEPLOY_HOOK_URL

echo "✅ Deployment complete!"
