FROM nginx:alpine
# CATU build 2026-08-27-final
COPY index.html /usr/share/nginx/html/index.html
COPY paniers_du_vendredi_catu.html /usr/share/nginx/html/paniers_du_vendredi_catu.html
EXPOSE 80
