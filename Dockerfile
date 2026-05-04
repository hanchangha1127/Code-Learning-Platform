FROM node:24-alpine AS frontend-build

WORKDIR /frontend

COPY ["new frontend/package.json", "new frontend/package-lock.json", "./"]
RUN npm ci

COPY ["new frontend/", "./"]
RUN npm run build

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
COPY --from=frontend-build /frontend/dist /app/new-frontend/dist
RUN chmod +x /app/entrypoint.sh

EXPOSE 8000

ENTRYPOINT ["/app/entrypoint.sh"]
