FROM python:3.13-slim@sha256:2d44738ebf4ce5f63b9d9ea871e9c7cfdc0426f7b0c97cac915fd88ded1d86bb

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
 && useradd --uid 10002 --home-dir /app/data --no-create-home lxmfbot

COPY bot.py database.py feed.py ./

USER lxmfbot
VOLUME /app/data
ENV DATA_DIR=/app/data
ENV PYTHONUNBUFFERED=1

CMD ["python", "-u", "bot.py"]
