#!/bin/bash

# Exit on any error
set -e

# Configuration
EC2_USER="ec2-user"
EC2_IP="54.221.250.59"
KEY_FILE="TradePilot-key.pem"
IMAGE_NAME="arthabot:latest"
TAR_FILE="arthabot-image.tar"

echo "Building Docker image for AMD64..."
docker build --platform linux/amd64 -t ${IMAGE_NAME} .

echo "Saving Docker image to tar..."
docker save -o ${TAR_FILE} ${IMAGE_NAME}

echo "Transferring files to EC2..."
chmod 600 .env
scp -o StrictHostKeyChecking=no -i ${KEY_FILE} ${TAR_FILE} ${EC2_USER}@${EC2_IP}:~
scp -o StrictHostKeyChecking=no -i ${KEY_FILE} .env ${EC2_USER}@${EC2_IP}:~
ssh -o StrictHostKeyChecking=no -i ${KEY_FILE} ${EC2_USER}@${EC2_IP} "chmod 600 ~/.env"

echo "Loading image on EC2..."
ssh -o StrictHostKeyChecking=no -i ${KEY_FILE} ${EC2_USER}@${EC2_IP} "docker load -i ${TAR_FILE}"

echo "Restarting container on EC2..."
ssh -o StrictHostKeyChecking=no -i ${KEY_FILE} ${EC2_USER}@${EC2_IP} "docker stop arthabot || true && docker rm arthabot || true"
ssh -o StrictHostKeyChecking=no -i ${KEY_FILE} ${EC2_USER}@${EC2_IP} "docker network create arthabot-network >/dev/null 2>&1 || true"
ssh -o StrictHostKeyChecking=no -i ${KEY_FILE} ${EC2_USER}@${EC2_IP} "docker run -d --name arthabot --restart unless-stopped --network arthabot-network --env-file .env -v ~/arthabot-data:/opt/arthabot/data -v ~/arthabot-logs:/opt/arthabot/logs ${IMAGE_NAME}"

echo "Cleaning up..."
ssh -o StrictHostKeyChecking=no -i ${KEY_FILE} ${EC2_USER}@${EC2_IP} "rm ${TAR_FILE}"
rm ${TAR_FILE}
echo "Deployment complete!"
