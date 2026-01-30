from typing import Dict, List
import httpx
from app.schemas import PersonInput, EnrichmentResponse, EnrichmentError, ProviderSource
from app.services.base import TIMEOUT, create_success, create_error, handle_http_error, parse_name


APOLLO_BASE_URL = "https://api.apollo.io/api/v1"
PROVIDER_NAME: ProviderSource = "apollo"


def _get_headers(api_key: str) -> Dict[str, str]:
    return {
        "Content-Type": "application/json",
        "Cache-Control": "no-cache",
        "X-Api-Key": api_key,
    }


def _build_payload(person: PersonInput) -> dict:
    """Map our schema to Apollo's expected fields."""
    payload: dict = {
        "linkedin_url": person.linkedin_url,
        "reveal_personal_emails": True,
    }

    first_name, last_name = parse_name(person)

    if first_name:
        payload["first_name"] = first_name
    if last_name:
        payload["last_name"] = last_name
    if person.company:
        payload["organization_name"] = person.company
    if person.domain:
        payload["domain"] = person.domain

    return payload


def _parse_response(data: dict, linkedin_url: str) -> EnrichmentResponse:
    """Parse Apollo response into our schema."""
    person = data.get("person")

    if not person:
        return create_error("not_found", "No match found in Apollo", linkedin_url)

    email = person.get("email")
    if not email:
        return create_error("not_found", "No email found in Apollo", linkedin_url)

    organization = person.get("organization") or {}

    return create_success(
        email=email,
        linkedin_url=person.get("linkedin_url") or linkedin_url,
        source=PROVIDER_NAME,
        name=person.get("name"),
        title=person.get("title"),
        company=organization.get("name"),
    )


async def enrich(person: PersonInput, api_key: str) -> EnrichmentResponse:
    """Enrich a single person via Apollo's people/match endpoint."""
    payload = _build_payload(person)

    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        try:
            response = await client.post(
                f"{APOLLO_BASE_URL}/people/match",
                headers=_get_headers(api_key),
                json=payload,
            )

            if response.status_code != 200:
                return handle_http_error(response.status_code, "Apollo", person.linkedin_url)

            return _parse_response(response.json(), person.linkedin_url)

        except httpx.TimeoutException:
            return create_error("api_error", "Apollo request timed out", person.linkedin_url)
        except httpx.RequestError:
            return create_error("api_error", "Apollo API unavailable", person.linkedin_url)


async def enrich_bulk(people: List[PersonInput], api_key: str) -> List[EnrichmentResponse]:
    """Enrich multiple people via Apollo's bulk_match endpoint."""
    details = [_build_payload(person) for person in people]

    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        try:
            response = await client.post(
                f"{APOLLO_BASE_URL}/people/bulk_match",
                headers=_get_headers(api_key),
                json={"details": details, "reveal_personal_emails": True},
            )

            if response.status_code != 200:
                error = handle_http_error(response.status_code, "Apollo")
                return [
                    EnrichmentError(
                        error=error.error,
                        message=error.message,
                        linkedin_url=person.linkedin_url,
                    )
                    for person in people
                ]

            data = response.json()
            matches = data.get("matches", [])

            results: List[EnrichmentResponse] = []
            for i, person in enumerate(people):
                if i < len(matches) and matches[i]:
                    results.append(_parse_response({"person": matches[i]}, person.linkedin_url))
                else:
                    results.append(create_error("not_found", "No match found in Apollo", person.linkedin_url))

            return results

        except httpx.TimeoutException:
            return [create_error("api_error", "Apollo request timed out", p.linkedin_url) for p in people]
        except httpx.RequestError:
            return [create_error("api_error", "Apollo API unavailable", p.linkedin_url) for p in people]
