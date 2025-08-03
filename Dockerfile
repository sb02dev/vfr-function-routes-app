# Set a default build argument (can be specified for local docker testing)
ARG APP_ENV="production"

# Stage 1: Build Angular
FROM node:21 AS frontend
ARG APP_ENV
WORKDIR /app/ngapp
COPY ngapp/ .
RUN npm install && npm run build -- --configuration ${APP_ENV}

# Stage 2: Python FastAPI backend
FROM python:3.12-slim
WORKDIR /app

# System deps (if you use numpy/matplotlib etc.)
RUN apt-get update && apt-get install -y build-essential && rm -rf /var/lib/apt/lists/*

# Install Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend code
COPY api/ ./api/
COPY VFRFunctionRoutes/ ./VFRFunctionRoutes/
COPY .env main.py ./

# Copy Angular build into backend (to be served by FastAPI)
COPY --from=frontend /app/frontend/browser ./frontend/browser

# Create data folders
RUN mkdir data
RUN mkdir output
RUN mkdir tracks

# Expose port
EXPOSE 8080

WORKDIR /app
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
