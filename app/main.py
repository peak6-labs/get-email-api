import logging
from fastapi import FastAPI

from app.config import settings
from app.schemas import (
    PersonInput,
    EnrichmentRequest,
    EnrichmentResponse,
    BulkEnrichmentRequest,
    BulkEnrichmentResponse,
    HealthResponse,
)
from app.services.enrichment import enrich_person, enrich_people_bulk


logging.basicConfig(
    level=getattr(logging, settings.log_level.upper()),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


app = FastAPI(
    title="Email Enrichment Service",
    description="Enrich person data with email addresses using multiple providers (Apollo, RocketReach, Lusha, Prospeo, Snov.io)",
    version="2.0.0",
)


@app.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Health check endpoint."""
    return HealthResponse()


@app.post("/enrich", response_model=EnrichmentResponse)
async def enrich(request: EnrichmentRequest) -> EnrichmentResponse:
    """
    Enrich a single person with their email address.

    Tries providers in configured order (waterfall) until one succeeds.
    Optionally accepts API keys to override environment defaults.
    """
    logger.info(f"Enriching person: {request.person.linkedin_url}")
    result = await enrich_person(request.person, request.api_keys)

    if result.success:
        logger.info(f"Found email for {request.person.linkedin_url} via {result.source}")
    else:
        logger.info(f"No email found for {request.person.linkedin_url}: {result.error}")

    return result


@app.post("/enrich/simple", response_model=EnrichmentResponse)
async def enrich_simple(person: PersonInput) -> EnrichmentResponse:
    """
    Simple enrichment endpoint (backwards compatible).
    Does not accept API keys - uses environment defaults only.
    """
    logger.info(f"Enriching person (simple): {person.linkedin_url}")
    result = await enrich_person(person, None)

    if result.success:
        logger.info(f"Found email for {person.linkedin_url} via {result.source}")
    else:
        logger.info(f"No email found for {person.linkedin_url}: {result.error}")

    return result


@app.post("/enrich/bulk", response_model=BulkEnrichmentResponse)
async def enrich_bulk(request: BulkEnrichmentRequest) -> BulkEnrichmentResponse:
    """
    Enrich multiple people with their email addresses (max 10).

    Uses Apollo bulk API when available, with waterfall fallback for failures.
    Optionally accepts API keys to override environment defaults.
    """
    logger.info(f"Bulk enriching {len(request.people)} people")
    results = await enrich_people_bulk(request.people, request.api_keys)
    success_count = sum(1 for r in results if r.success)
    logger.info(f"Bulk enrichment complete: {success_count}/{len(results)} successful")
    return BulkEnrichmentResponse(results=results)
