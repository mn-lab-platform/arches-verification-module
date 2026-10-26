FROM node:22-alpine AS frontend-build
WORKDIR /frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/app/backend
WORKDIR /app
COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir -r /app/backend/requirements.txt
COPY backend/verify_service /app/backend/verify_service
COPY --from=frontend-build /frontend/dist /app/frontend/dist
RUN useradd --system --uid 10001 --create-home verify
# A new named volume copies this ownership, so the service can write custom rules.
RUN install -d -o verify /data
USER verify
EXPOSE 8000
CMD ["python", "-m", "verify_service.start"]
