FROM python:3.12-slim
WORKDIR /app
RUN pip install --no-cache-dir fastapi uvicorn segno
COPY main.py .
RUN mkdir -p static
COPY site_index.html /app/static/index.html
COPY paniers_du_vendredi_catu.html /app/static/app.html
ENV DB_PATH=/data/catu.db
EXPOSE 80
CMD ["uvicorn","main:app","--host","0.0.0.0","--port","80"]