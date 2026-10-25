FROM node:22-alpine AS frontend
WORKDIR /frontend
COPY Alpha-front/package.json Alpha-front/package-lock.json ./
RUN npm ci
COPY Alpha-front/ ./
RUN npm run build

FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt requirements.lock ./
RUN pip install --no-cache-dir -r requirements.lock
COPY app ./app
COPY --from=frontend /frontend/dist ./app/static
EXPOSE 8000
CMD ["python", "-m", "app.main"]
