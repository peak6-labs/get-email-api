from typing import Dict
import httpx
from app.schemas import PersonInput, EnrichmentResponse, ProviderSource
from app.services.base import TIMEOUT, create_success, create_error, handle_http_error, parse_name


ROCKETREACH_BASE_URL = "https://api.rocketreach.co/api/v2"
PROVIDER_NAME: ProviderSource = "rocketreach"


def _get_headers(api_key: str) -> Dict[str, str]:
    return {
        "Content-Type": "application/json",
        "Api-Key": api_key,
    }


async def enrich(person: PersonInput, api_key: str) -> EnrichmentResponse:
    """Enrich a person via RocketReach's person/lookup endpoint."""
    first_name, last_name = parse_name(person)

    # Build query parameters
    params: Dict[str, str] = {}
    if person.linkedin_url:
        params["linkedin_url"] = person.linkedin_url
    if first_name:
        params["name"] = f"{first_name} {last_name}".strip() if last_name else first_name
    if person.company:
        params["current_employer"] = person.company

    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        try:
            response = await client.get(
                f"{ROCKETREACH_BASE_URL}/person/lookup",
                headers=_get_headers(api_key),
                params=params,
            )

            if response.status_code == 404:
                return create_error("not_found", "Person not found in RocketReach", person.linkedin_url)
            if response.status_code != 200:
                return handle_http_error(response.status_code, "RocketReach", person.linkedin_url)

            data = response.json()

            # RocketReach returns person data directly (not nested)
            email = data.get("current_work_email") or data.get("personal_email")
            if not email and data.get("emails"):
                emails = data.get("emails", [])
                email = emails[0] if emails else None

            if not email:
                return create_error("not_found", "No email found in RocketReach", person.linkedin_url)

            return create_success(
                email=email,
                linkedin_url=data.get("linkedin_url") or person.linkedin_url,
                source=PROVIDER_NAME,
                name=data.get("name"),
                title=data.get("current_title"),
                company=data.get("current_employer"),
            )

        except httpx.TimeoutException:
            return create_error("api_error", "RocketReach request timed out", person.linkedin_url)
        except httpx.RequestError:
            return create_error("api_error", "RocketReach API unavailable", person.linkedin_url)
