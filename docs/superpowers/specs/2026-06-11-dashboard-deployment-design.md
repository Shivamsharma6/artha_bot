# Dashboard Deployment Design

## Overview
This document specifies the design for containerizing and deploying the ArthaBot Vite dashboard, making it accessible on port 8765.

## Architecture & Components

**1. Dockerfile (`dashboard/Dockerfile`)**
- Base image: `nginx:alpine`
- Build stage: Single-stage. We assume the `dist/` folder is generated on the host before building the Docker image.
- Action: The `Dockerfile` will `COPY dist/ /usr/share/nginx/html/`.

**2. Nginx Configuration (`dashboard/nginx.conf`)**
- A custom Nginx configuration file will be created to ensure the server listens directly on port `8765`.
- This config will be copied to `/etc/nginx/conf.d/default.conf` in the container.

## Data Flow & Execution Steps

1. **Build Artifact Generation**:
   - Run `npm install` and `npm run build` locally in the `dashboard/` directory.
   - This produces the static files in `dashboard/dist/`.
2. **Docker Image Build**:
   - Run `docker build -t arthabot-dashboard ./dashboard`.
3. **Container Execution**:
   - Run `docker run -d -p 8765:8765 --name arthabot_dashboard arthabot-dashboard`.
   - The container maps host port 8765 to container port 8765.

## Error Handling & Verification
- If `dist/` is missing, the `docker build` command will fail because the `COPY` instruction will fail. This is intentional to ensure an artifact exists.
- The user can verify deployment by visiting `http://localhost:8765`.

## Scope
- This design handles the immediate need to run the dashboard in a container. It explicitly excludes multi-stage Docker builds or CI/CD pipelines since a local single-stage build was selected.
