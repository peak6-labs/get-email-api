import logging
from fastapi import FastAPI
from pydantic import ValidationError

from app.config import settings
from app.schemas import (
    PersonInput,
    EnrichmentResponse,
    EnrichmentError,
    BulkEnrichmentRequest,
    BulkEnrichmentResponse,
    HealthResponse,
)
from app.services.apollo import enrich_person, enrich_people_bulk


logging.basicConfig(
    level=getattr(logging, settings.log_level.upper()),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


app = FastAPI(
    title="Email Enrichment Service",
    description="Enrich person data with email addresses using Apollo.io",
    version="1.0.0",
)


@app.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Health check endpoint."""
    return HealthResponse()


@app.post("/enrich", response_model=EnrichmentResponse)
async def enrich(person: PersonInput) -> EnrichmentResponse:
    """Enrich a single person with their email address."""
    logger.info(f"Enriching person: {person.linkedin_url}")
    result = await enrich_person(person)
    if result.success:
        logger.info(f"Found email for {person.linkedin_url}")
    else:
        logger.info(f"No email found for {person.linkedin_url}: {result.error}")
    return result


@app.post("/enrich/bulk", response_model=BulkEnrichmentResponse)
async def enrich_bulk(request: BulkEnrichmentRequest) -> BulkEnrichmentResponse:
    """Enrich multiple people with their email addresses (max 10)."""
    logger.info(f"Bulk enriching {len(request.people)} people")
    results = await enrich_people_bulk(request.people)
    success_count = sum(1 for r in results if r.success)
    logger.info(f"Bulk enrichment complete: {success_count}/{len(results)} successful")
    return BulkEnrichmentResponse(results=results)
