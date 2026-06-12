# Dashboard HTTPS Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enable HTTPS for the dashboard container using a dynamically generated self-signed certificate on port 8765.

**Architecture:** We use an `entrypoint.sh` script that generates a self-signed cert on startup via OpenSSL before launching Nginx. Nginx configuration is updated to serve SSL.

**Tech Stack:** Docker, Nginx, OpenSSL

---

### Task 1: Add Entrypoint Script

**Files:**
- Create: `dashboard/entrypoint.sh`

- [ ] **Step 1: Write entrypoint.sh**

```sh
#!/bin/sh

# Directory for SSL certificates
SSL_DIR="/etc/nginx/ssl"

# Check if the certificate already exists
if [ ! -f "$SSL_DIR/nginx.crt" ]; then
    echo "Generating self-signed SSL certificate..."
    mkdir -p "$SSL_DIR"
    
    # Generate a self-signed certificate
    openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
        -keyout "$SSL_DIR/nginx.key" \
        -out "$SSL_DIR/nginx.crt" \
        -subj "/CN=54.221.250.59"
        
    echo "Certificate generated successfully."
fi

# Execute the CMD or default nginx behavior
exec nginx -g 'daemon off;'
```

- [ ] **Step 2: Commit**

```bash
git add dashboard/entrypoint.sh
git commit -m "feat(dashboard): add entrypoint script for dynamic SSL cert generation"
```

---

### Task 2: Modify Nginx Configuration

**Files:**
- Modify: `dashboard/nginx.conf`

- [ ] **Step 1: Update nginx.conf**

Replace the existing `listen 8765;` line with the following SSL configuration block. Keep the rest of the configuration the same.

```nginx
    listen 8765 ssl;
    server_name localhost;

    ssl_certificate /etc/nginx/ssl/nginx.crt;
    ssl_certificate_key /etc/nginx/ssl/nginx.key;
    
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;
```

- [ ] **Step 2: Commit**

```bash
git add dashboard/nginx.conf
git commit -m "chore(dashboard): configure Nginx to use SSL"
```

---

### Task 3: Modify Dockerfile

**Files:**
- Modify: `dashboard/Dockerfile`

- [ ] **Step 1: Update Dockerfile**

Modify `dashboard/Dockerfile` to install openssl, copy the entrypoint script, and use it as the entrypoint.

Replace the contents with:

```dockerfile
FROM nginx:alpine

# Install OpenSSL for generating certificates
RUN apk add --no-cache openssl

# Remove default nginx website
RUN rm -rf /usr/share/nginx/html/*

# Copy the custom Nginx configuration
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Copy the entrypoint script
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Copy the pre-built dist folder
COPY dist/ /usr/share/nginx/html/

# Expose the configured port
EXPOSE 8765

# Set the entrypoint script to run on container start
ENTRYPOINT ["/entrypoint.sh"]
```

- [ ] **Step 2: Commit**

```bash
git add dashboard/Dockerfile
git commit -m "chore(dashboard): update Dockerfile for openssl and entrypoint"
```

---

### Task 4: Build and Run Docker Image

**Files:** None

- [ ] **Step 1: Build Docker Image**

```bash
cd dashboard && docker build -t arthabot-dashboard .
```
Expected: PASS with `Successfully built ...` output.

- [ ] **Step 2: Stop and remove existing container if any**

```bash
docker rm -f arthabot_dashboard || true
```

- [ ] **Step 3: Run the Docker Container**

```bash
docker run -d -p 8765:8765 --name arthabot_dashboard arthabot-dashboard
```
Expected: PASS with a new container ID returned.

- [ ] **Step 4: Verify Container is Running**

```bash
docker ps | grep arthabot_dashboard
```
Expected: PASS indicating the container is Up.

- [ ] **Step 5: Verify Application Responses over HTTPS**

Note the `-k` flag to allow insecure connections for the self-signed cert.
```bash
curl -k -I https://localhost:8765
```
Expected: HTTP/1.1 200 OK
