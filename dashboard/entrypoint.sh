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
