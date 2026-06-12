# Dashboard HTTPS Deployment Design

## Overview
This document specifies the design for adding HTTPS (SSL/TLS) to the ArthaBot Vite dashboard container, which is served via Nginx on port 8765. The HTTPS setup utilizes a self-signed certificate dynamically generated at container startup.

## Architecture & Components

**1. Dockerfile Modifications (`dashboard/Dockerfile`)**
- We will add the `openssl` package to the existing `nginx:alpine` image.
- We will `COPY entrypoint.sh /entrypoint.sh` and make it executable.
- We will override the default CMD by adding `ENTRYPOINT ["/entrypoint.sh"]`.

**2. Entrypoint Script (`dashboard/entrypoint.sh`)**
- **Purpose**: Dynamically generate the self-signed SSL certificate before Nginx starts.
- **Logic**:
  - Check if `/etc/nginx/ssl/nginx.crt` exists.
  - If not, create the `/etc/nginx/ssl` directory.
  - Run `openssl req -x509 -nodes -days 365 -newkey rsa:2048 -keyout /etc/nginx/ssl/nginx.key -out /etc/nginx/ssl/nginx.crt -subj "/CN=54.221.250.59"` to generate the key and certificate.
  - Start Nginx using `exec nginx -g 'daemon off;'`.

**3. Nginx Configuration (`dashboard/nginx.conf`)**
- Modify the existing server block to support SSL.
- Change `listen 8765;` to `listen 8765 ssl;`.
- Add the following SSL directives:
  - `ssl_certificate /etc/nginx/ssl/nginx.crt;`
  - `ssl_certificate_key /etc/nginx/ssl/nginx.key;`
  - (Optional but recommended) Basic SSL protocols and ciphers for security.

## Data Flow & Execution Steps
1. The container starts.
2. Docker executes `/entrypoint.sh`.
3. The script generates the SSL certificates for `54.221.250.59`.
4. The script hands over execution to Nginx.
5. Nginx starts and listens for incoming HTTPS connections on port 8765 using the generated certs.

## Error Handling & Verification
- If `openssl` fails to generate the certificates, the entrypoint script will fail, and the container will exit, providing clear logs of the error.
- The user can verify the deployment by visiting `https://54.221.250.59:8765` or `https://localhost:8765`. A browser warning will appear because the certificate is self-signed; the user can bypass it to verify functionality.

## Scope
This scope strictly covers enabling HTTPS via a self-signed certificate for the existing dashboard container. It does not set up Let's Encrypt or any reverse-proxy load balancers.
