FROM nginx:alpine
COPY index.html /usr/share/nginx/html/index.html
RUN chmod 644 /usr/share/nginx/html/index.html
HEALTHCHECK --interval=5s --timeout=2s --retries=3 CMD wget -q --spider http://localhost:80/ || exit 1
EXPOSE 80
