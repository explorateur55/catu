FROM nginx:alpine
COPY index.html /usr/share/nginx/html/index.html
COPY paniers_du_vendredi_catu.html /usr/share/nginx/html/paniers_du_vendredi_catu.html
EXPOSE 80
