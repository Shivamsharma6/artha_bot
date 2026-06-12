#!/bin/bash

# Exit on any error
set -e

# Configuration
EC2_USER="ec2-user"
EC2_IP="54.221.250.59"
KEY_FILE="TradePilot-key.pem"
IMAGE_NAME="arthabot-dashboard:latest"
TAR_FILE="arthabot-dashboard-image.tar"
DASHBOARD_DIR="dashboard"

echo "Building Docker image for AMD64..."
cd ${DASHBOARD_DIR}
docker build --platform linux/amd64 -t ${IMAGE_NAME} .
cd ..

echo "Saving Docker image to tar..."
docker save -o ${TAR_FILE} ${IMAGE_NAME}

echo "Transferring files to EC2..."
scp -o StrictHostKeyChecking=no -i ${KEY_FILE} ${TAR_FILE} ${EC2_USER}@${EC2_IP}:~

echo "Loading image on EC2..."
ssh -o StrictHostKeyChecking=no -i ${KEY_FILE} ${EC2_USER}@${EC2_IP} "docker load -i ${TAR_FILE}"

echo "Restarting container on EC2..."
ssh -o StrictHostKeyChecking=no -i ${KEY_FILE} ${EC2_USER}@${EC2_IP} "docker stop arthabot_dashboard || true && docker rm arthabot_dashboard || true"
ssh -o StrictHostKeyChecking=no -i ${KEY_FILE} ${EC2_USER}@${EC2_IP} "docker network create arthabot-network >/dev/null 2>&1 || true"
ssh -o StrictHostKeyChecking=no -i ${KEY_FILE} ${EC2_USER}@${EC2_IP} "docker run -d -p 8765:8765 --name arthabot_dashboard --restart unless-stopped --network arthabot-network ${IMAGE_NAME}"

echo "Cleaning up..."
ssh -o StrictHostKeyChecking=no -i ${KEY_FILE} ${EC2_USER}@${EC2_IP} "rm ${TAR_FILE}"
rm ${TAR_FILE}
echo "Deployment complete!"
