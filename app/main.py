import logging
from fastapi import FastAPI

from app.config import settings
from app.schemas import (
    PersonInput,
    EnrichmentRequest,
    EnrichmentResponse,
    EnrichmentError,
    BulkEnrichmentRequest,
    BulkEnrichmentResponse,
    HealthResponse,
    ApiKeys,
)
from app.services.enrichment import enrich_person, enrich_people_bulk
from app.services import apollo, rocketreach, lusha, prospeo, snov


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


def _get_api_key(provider: str, api_keys: ApiKeys = None) -> str:
    """Get API key for a provider from request or env."""
    if api_keys:
        user_key = getattr(api_keys, provider, None)
        if user_key:
            return user_key

    env_key_map = {
        "apollo": settings.apollo_api_key,
        "rocketreach": settings.rocketreach_api_key,
        "lusha": settings.lusha_api_key,
        "prospeo": settings.prospeo_api_key,
        "snov": settings.snov_api_key,
    }
    return env_key_map.get(provider, "")


@app.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Health check endpoint."""
    return HealthResponse()


@app.post("/enrich", response_model=EnrichmentResponse)
async def enrich(request: EnrichmentRequest) -> EnrichmentResponse:
    """
    Enrich a single person with their email address.

    Tries providers in configured order (waterfall) until one succeeds.
    Optionally accepts API keys and/or providers list to override defaults.
    """
    logger.info(f"Enriching person: {request.person.linkedin_url}")
    result = await enrich_person(request.person, request.api_keys, request.providers)

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
    Optionally accepts API keys and/or providers list to override defaults.
    """
    logger.info(f"Bulk enriching {len(request.people)} people")
    results = await enrich_people_bulk(request.people, request.api_keys, request.providers)
    success_count = sum(1 for r in results if r.success)
    logger.info(f"Bulk enrichment complete: {success_count}/{len(results)} successful")
    return BulkEnrichmentResponse(results=results)


# ============================================================================
# Individual Provider Endpoints (for testing)
# ============================================================================

@app.post("/enrich/apollo", response_model=EnrichmentResponse)
async def enrich_apollo(request: EnrichmentRequest) -> EnrichmentResponse:
    """Test Apollo provider directly."""
    api_key = _get_api_key("apollo", request.api_keys)
    if not api_key:
        return EnrichmentError(error="auth_error", message="No Apollo API key configured", linkedin_url=request.person.linkedin_url)

    logger.info(f"[Apollo] Enriching: {request.person.linkedin_url}")
    return await apollo.enrich(request.person, api_key)


@app.post("/enrich/rocketreach", response_model=EnrichmentResponse)
async def enrich_rocketreach(request: EnrichmentRequest) -> EnrichmentResponse:
    """Test RocketReach provider directly."""
    api_key = _get_api_key("rocketreach", request.api_keys)
    if not api_key:
        return EnrichmentError(error="auth_error", message="No RocketReach API key configured", linkedin_url=request.person.linkedin_url)

    logger.info(f"[RocketReach] Enriching: {request.person.linkedin_url}")
    return await rocketreach.enrich(request.person, api_key)


@app.post("/enrich/lusha", response_model=EnrichmentResponse)
async def enrich_lusha(request: EnrichmentRequest) -> EnrichmentResponse:
    """Test Lusha provider directly."""
    api_key = _get_api_key("lusha", request.api_keys)
    if not api_key:
        return EnrichmentError(error="auth_error", message="No Lusha API key configured", linkedin_url=request.person.linkedin_url)

    logger.info(f"[Lusha] Enriching: {request.person.linkedin_url}")
    return await lusha.enrich(request.person, api_key)


@app.post("/enrich/prospeo", response_model=EnrichmentResponse)
async def enrich_prospeo(request: EnrichmentRequest) -> EnrichmentResponse:
    """Test Prospeo provider directly."""
    api_key = _get_api_key("prospeo", request.api_keys)
    if not api_key:
        return EnrichmentError(error="auth_error", message="No Prospeo API key configured", linkedin_url=request.person.linkedin_url)

    logger.info(f"[Prospeo] Enriching: {request.person.linkedin_url}")
    return await prospeo.enrich(request.person, api_key)


@app.post("/enrich/snov", response_model=EnrichmentResponse)
async def enrich_snov(request: EnrichmentRequest) -> EnrichmentResponse:
    """Test Snov.io provider directly."""
    api_key = _get_api_key("snov", request.api_keys)
    if not api_key:
        return EnrichmentError(error="auth_error", message="No Snov.io API key configured", linkedin_url=request.person.linkedin_url)

    logger.info(f"[Snov.io] Enriching: {request.person.linkedin_url}")
    return await snov.enrich(request.person, api_key)
