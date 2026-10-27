#!/usr/bin/env bash
# FairShift — Google Cloud Run deployment script
# Usage: chmod +x deploy.sh && ./deploy.sh YOUR_PROJECT_ID
# Requires: gcloud CLI authenticated, Docker, bash

set -euo pipefail

PROJECT_ID="${1:?Usage: ./deploy.sh YOUR_PROJECT_ID}"
REGION="asia-south1"
SERVICE_NAME="fairshift"
IMAGE="gcr.io/${PROJECT_ID}/${SERVICE_NAME}"

echo "🚀 Deploying FairShift to Cloud Run..."
echo "   Project : ${PROJECT_ID}"
echo "   Region  : ${REGION}"
echo "   Service : ${SERVICE_NAME}"
echo ""

# Load env vars (user must set these before running)
if [ ! -f .env ]; then
  echo "❌ .env file not found. Copy .env.example and fill in values."
  exit 1
fi
source .env

if [ -z "${SECRET_KEY:-}" ] || [ "${SECRET_KEY}" = "your-secret-key-here" ]; then
  echo "❌ SECRET_KEY not set or still placeholder. Generate with:"
  echo "   python -c \"import secrets; print(secrets.token_hex(32))\""
  exit 1
fi

# Set project
gcloud config set project "${PROJECT_ID}"

# Enable required APIs (idempotent)
gcloud services enable run.googleapis.com cloudbuild.googleapis.com \
  containerregistry.googleapis.com --quiet

# Deploy from source (Cloud Build builds the container)
gcloud run deploy "${SERVICE_NAME}" \
  --source . \
  --region "${REGION}" \
  --platform managed \
  --allow-unauthenticated \
  --set-env-vars "APP_ENV=production,SECRET_KEY=${SECRET_KEY},ADMIN_PASSWORD=${ADMIN_PASSWORD:-AdminPass@2026},WORKER_PASSWORD=${WORKER_PASSWORD:-WorkerPass@2026}" \
  --memory 512Mi \
  --cpu 1 \
  --min-instances 0 \
  --max-instances 3 \
  --timeout 60 \
  --concurrency 80

# Get URL
SERVICE_URL=$(gcloud run services describe "${SERVICE_NAME}" \
  --region "${REGION}" \
  --format='value(status.url)')

echo ""
echo "✅ Deployed successfully!"
echo "   Live URL : ${SERVICE_URL}"
echo "   Health   : ${SERVICE_URL}/health"
echo ""
echo "📋 Submit these links to the Innovator Dashboard:"
echo "   GitHub   : https://github.com/YOUR_USERNAME/FairShift.git"
echo "   Cloud Run: ${SERVICE_URL}"
echo "   LinkedIn : YOUR_LINKEDIN_POST_URL"
