# Dashboard Deployment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deploy the Vite dashboard as an Nginx Docker container and make it live on port 8765.

**Architecture:** A single-stage Docker build utilizing an `nginx:alpine` base image. A custom `nginx.conf` sets the port to 8765. The `dist/` directory generated from a local `npm run build` is copied into the container.

**Tech Stack:** Docker, Nginx, Vite/Node.js

---

### Task 1: Add Nginx Configuration

**Files:**
- Create: `dashboard/nginx.conf`

- [ ] **Step 1: Write Nginx configuration**

```nginx
server {
    listen 8765;
    server_name localhost;

    location / {
        root   /usr/share/nginx/html;
        index  index.html index.htm;
        try_files $uri $uri/ /index.html;
    }

    error_page   500 502 503 504  /50x.html;
    location = /50x.html {
        root   /usr/share/nginx/html;
    }
}
```

- [ ] **Step 2: Commit**

```bash
git add dashboard/nginx.conf
git commit -m "chore: add nginx.conf for dashboard deployment"
```

---

### Task 2: Add Dockerfile

**Files:**
- Create: `dashboard/Dockerfile`

- [ ] **Step 1: Write Dockerfile**

```dockerfile
FROM nginx:alpine

# Remove default nginx website
RUN rm -rf /usr/share/nginx/html/*

# Copy the custom Nginx configuration
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Copy the pre-built dist folder
COPY dist/ /usr/share/nginx/html/

# Expose the configured port
EXPOSE 8765

# Start Nginx
CMD ["nginx", "-g", "daemon off;"]
```

- [ ] **Step 2: Commit**

```bash
git add dashboard/Dockerfile
git commit -m "chore: add Dockerfile for dashboard deployment"
```

---

### Task 3: Build the application artifact

**Files:** None

- [ ] **Step 1: Install dependencies and build**

Run the build commands locally to generate the `dist/` folder:

```bash
cd dashboard && npm install && npm run build
```
Expected: PASS with `✓ built in ...` output and `dist/` folder created.

- [ ] **Step 2: Ignore dist folder in version control**
(This is usually covered by the Vite `.gitignore`, but we ensure it).
No commit for the built artifact.

---

### Task 4: Build and Run the Docker Image

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

- [ ] **Step 5: Verify Application Responses**

```bash
curl -I http://localhost:8765
```
Expected: HTTP/1.1 200 OK
