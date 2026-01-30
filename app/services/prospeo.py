from typing import Dict
import httpx
from app.schemas import PersonInput, EnrichmentResponse, ProviderSource
from app.services.base import TIMEOUT, create_success, create_error, handle_http_error


PROSPEO_BASE_URL = "https://api.prospeo.io"
PROVIDER_NAME: ProviderSource = "prospeo"


def _get_headers(api_key: str) -> Dict[str, str]:
    return {
        "Content-Type": "application/json",
        "X-KEY": api_key,
    }


async def enrich(person: PersonInput, api_key: str) -> EnrichmentResponse:
    """Enrich a person via Prospeo's enrich-person endpoint."""
    # New endpoint format (migrated from deprecated social-url-enrichment)
    payload = {
        "data": {
            "linkedin_url": person.linkedin_url,
        }
    }

    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        try:
            response = await client.post(
                f"{PROSPEO_BASE_URL}/enrich-person",
                headers=_get_headers(api_key),
                json=payload,
            )

            if response.status_code != 200:
                return handle_http_error(response.status_code, "Prospeo", person.linkedin_url)

            data = response.json()

            # Check for error response
            if data.get("error"):
                error_msg = data.get("message", "No match found in Prospeo")
                return create_error("not_found", error_msg, person.linkedin_url)

            # Extract from response wrapper
            result = data.get("response", data)

            email = result.get("email")
            if not email:
                return create_error("not_found", "No email found in Prospeo", person.linkedin_url)

            return create_success(
                email=email,
                linkedin_url=result.get("linkedin") or person.linkedin_url,
                source=PROVIDER_NAME,
                name=result.get("name"),
                title=result.get("title"),
                company=result.get("company"),
            )

        except httpx.TimeoutException:
            return create_error("api_error", "Prospeo request timed out", person.linkedin_url)
        except httpx.RequestError:
            return create_error("api_error", "Prospeo API unavailable", person.linkedin_url)
