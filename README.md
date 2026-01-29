# Email Enrichment Service

A FastAPI backend service that accepts person data (LinkedIn URL + optional metadata) and returns their email address using the Apollo.io API.

## Quick Start

### Prerequisites
- Docker and Docker Compose
- Apollo.io API key

### Local Development

1. Copy the example environment file:
   ```bash
   cp .env.example .env
   ```

2. Add your Apollo API key to `.env`:
   ```
   APOLLO_API_KEY=your_actual_api_key
   ```

3. Start the service:
   ```bash
   docker-compose up --build
   ```

4. Test the health endpoint:
   ```bash
   curl http://localhost:8000/health
   ```

## API Endpoints

### Health Check
```
GET /health
```

### Single Enrichment
```bash
curl -X POST http://localhost:8000/enrich \
  -H "Content-Type: application/json" \
  -d '{
    "linkedin_url": "https://linkedin.com/in/johndoe",
    "first_name": "John",
    "last_name": "Doe",
    "company": "Acme Inc"
  }'
```

### Bulk Enrichment (max 10 people)
```bash
curl -X POST http://localhost:8000/enrich/bulk \
  -H "Content-Type: application/json" \
  -d '{
    "people": [
      {"linkedin_url": "https://linkedin.com/in/johndoe", "first_name": "John"},
      {"linkedin_url": "https://linkedin.com/in/janesmith", "company": "Globex"}
    ]
  }'
```

## GCP Cloud Run Deployment

```bash
# Set project
gcloud config set project YOUR_PROJECT_ID

# Build and push
gcloud builds submit --tag gcr.io/YOUR_PROJECT_ID/enrichment-service

# Deploy
gcloud run deploy enrichment-service \
  --image gcr.io/YOUR_PROJECT_ID/enrichment-service \
  --platform managed \
  --region us-central1 \
  --set-env-vars APOLLO_API_KEY=your_key \
  --no-allow-unauthenticated
```

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| APOLLO_API_KEY | Yes | Apollo.io API key |
| PORT | No | Server port (default: 8000) |
| LOG_LEVEL | No | Logging level (default: INFO) |
