FROM python:3.12-slim
WORKDIR /app
COPY server.py ./
COPY public ./public
RUN useradd --create-home app && mkdir /app/data && chown -R app:app /app
USER app
ENV HOST=0.0.0.0 PORT=8000 DATABASE_PATH=/app/data/app.sqlite3
EXPOSE 8000
VOLUME ["/app/data"]
CMD ["python", "server.py"]
