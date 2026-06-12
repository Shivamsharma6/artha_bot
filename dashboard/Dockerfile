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
