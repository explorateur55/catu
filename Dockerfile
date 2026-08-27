FROM nginx:1.27-alpine
# CATU v3 - site vitrine + appli paniers
COPY index.html /usr/share/nginx/html/index.html
COPY paniers_du_vendredi_catu.html /usr/share/nginx/html/paniers_du_vendredi_catu.html
EXPOSE 80
