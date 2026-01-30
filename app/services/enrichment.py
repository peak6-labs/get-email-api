import logging
from typing import Dict, List, Optional, Callable, Awaitable
from app.config import settings
from app.schemas import PersonInput, EnrichmentResponse, EnrichmentError, ApiKeys
from app.services import apollo, rocketreach, lusha, prospeo, snov


logger = logging.getLogger(__name__)


# Provider registry mapping name to enrich function
PROVIDERS: Dict[str, Callable[[PersonInput, str], Awaitable[EnrichmentResponse]]] = {
    "apollo": apollo.enrich,
    "rocketreach": rocketreach.enrich,
    "lusha": lusha.enrich,
    "prospeo": prospeo.enrich,
    "snov": snov.enrich,
}


def _get_api_key(provider: str, user_keys: Optional[ApiKeys]) -> Optional[str]:
    """Get API key for provider, preferring user-provided key over env default."""
    # Check user-provided keys first
    if user_keys:
        user_key = getattr(user_keys, provider, None)
        if user_key:
            return user_key

    # Fall back to environment keys
    env_key_map = {
        "apollo": settings.apollo_api_key,
        "rocketreach": settings.rocketreach_api_key,
        "lusha": settings.lusha_api_key,
        "prospeo": settings.prospeo_api_key,
        "snov": settings.snov_api_key,
    }
    return env_key_map.get(provider) or None


async def enrich_person(
    person: PersonInput,
    api_keys: Optional[ApiKeys] = None,
) -> EnrichmentResponse:
    """
    Enrich a person using waterfall strategy.
    Tries each enabled provider in order until one succeeds.
    """
    provider_order = settings.get_provider_order()
    last_error: Optional[EnrichmentError] = None

    for provider_name in provider_order:
        # Get API key (user-provided or env default)
        api_key = _get_api_key(provider_name, api_keys)

        if not api_key:
            logger.debug(f"Skipping {provider_name}: no API key")
            continue

        if provider_name not in PROVIDERS:
            logger.warning(f"Unknown provider: {provider_name}")
            continue

        enrich_fn = PROVIDERS[provider_name]

        logger.info(f"Trying {provider_name} for {person.linkedin_url}")
        result = await enrich_fn(person, api_key)

        if result.success:
            logger.info(f"Success from {provider_name} for {person.linkedin_url}")
            return result

        logger.info(f"{provider_name} failed: {result.error} - {result.message}")
        last_error = result

    # All providers failed
    if last_error:
        return last_error

    return EnrichmentError(
        success=False,
        error="not_found",
        message="No providers available or all providers failed",
        linkedin_url=person.linkedin_url,
    )


async def enrich_people_bulk(
    people: List[PersonInput],
    api_keys: Optional[ApiKeys] = None,
) -> List[EnrichmentResponse]:
    """
    Enrich multiple people.
    For bulk, we only use Apollo (which has native bulk support).
    Falls back to individual enrichment if Apollo fails or is disabled.
    """
    apollo_key = _get_api_key("apollo", api_keys)

    if apollo_key and "apollo" in settings.get_provider_order():
        # Try Apollo bulk first
        logger.info(f"Trying Apollo bulk for {len(people)} people")
        results = await apollo.enrich_bulk(people, apollo_key)

        # Check if any failed - for those, try waterfall
        final_results: List[EnrichmentResponse] = []
        for i, result in enumerate(results):
            if result.success:
                final_results.append(result)
            else:
                # Try waterfall for failed ones
                logger.info(f"Apollo bulk failed for {people[i].linkedin_url}, trying waterfall")
                waterfall_result = await enrich_person(people[i], api_keys)
                final_results.append(waterfall_result)

        return final_results

    # No Apollo, do individual enrichment for each
    logger.info(f"No Apollo bulk, enriching {len(people)} people individually")
    return [await enrich_person(person, api_keys) for person in people]
