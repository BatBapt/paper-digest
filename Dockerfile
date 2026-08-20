FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY veille ./veille

VOLUME ["/data"]
EXPOSE 8137

ENTRYPOINT ["python", "-m", "veille"]
CMD ["serve"]
