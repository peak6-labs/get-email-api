from typing import Dict, List, Optional
import httpx
from app.config import settings
from app.schemas import PersonInput, EnrichmentSuccess, EnrichmentError, EnrichmentResponse


APOLLO_BASE_URL = "https://api.apollo.io/api/v1"
TIMEOUT = 30.0


def _get_headers() -> Dict[str, str]:
    return {
        "Content-Type": "application/json",
        "Cache-Control": "no-cache",
        "X-Api-Key": settings.apollo_api_key,
    }


def _build_apollo_payload(person: PersonInput) -> dict:
    """Map our schema to Apollo's expected fields."""
    payload: dict = {
        "linkedin_url": person.linkedin_url,
        "reveal_personal_emails": True,
    }

    # Handle name parsing if first/last not provided
    first_name = person.first_name
    last_name = person.last_name

    if not first_name and not last_name and person.name:
        parts = person.name.strip().split(maxsplit=1)
        first_name = parts[0] if parts else None
        last_name = parts[1] if len(parts) > 1 else None

    if first_name:
        payload["first_name"] = first_name
    if last_name:
        payload["last_name"] = last_name
    if person.company:
        payload["organization_name"] = person.company
    if person.domain:
        payload["domain"] = person.domain

    return payload


def _parse_apollo_response(apollo_data: dict, linkedin_url: str) -> EnrichmentResponse:
    """Parse Apollo response into our schema."""
    person = apollo_data.get("person")

    if not person:
        return EnrichmentError(
            error="not_found",
            message="No email found for this LinkedIn profile",
            linkedin_url=linkedin_url,
        )

    email = person.get("email")
    if not email:
        return EnrichmentError(
            error="not_found",
            message="No email found for this LinkedIn profile",
            linkedin_url=linkedin_url,
        )

    organization = person.get("organization") or {}

    return EnrichmentSuccess(
        email=email,
        name=person.get("name"),
        title=person.get("title"),
        company=organization.get("name"),
        linkedin_url=person.get("linkedin_url") or linkedin_url,
    )


def _handle_apollo_error(status_code: int, linkedin_url: Optional[str] = None) -> EnrichmentError:
    """Convert Apollo HTTP errors to our error schema."""
    if status_code == 401:
        return EnrichmentError(
            error="auth_error",
            message="Invalid Apollo API key",
            linkedin_url=linkedin_url,
        )
    elif status_code == 429:
        return EnrichmentError(
            error="rate_limit",
            message="Apollo rate limit exceeded. Try again later.",
            linkedin_url=linkedin_url,
        )
    else:
        return EnrichmentError(
            error="api_error",
            message="Apollo API unavailable",
            linkedin_url=linkedin_url,
        )


async def enrich_person(person: PersonInput) -> EnrichmentResponse:
    """Enrich a single person via Apollo's people/match endpoint."""
    payload = _build_apollo_payload(person)

    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        try:
            response = await client.post(
                f"{APOLLO_BASE_URL}/people/match",
                headers=_get_headers(),
                json=payload,
            )

            if response.status_code != 200:
                return _handle_apollo_error(response.status_code, person.linkedin_url)

            return _parse_apollo_response(response.json(), person.linkedin_url)

        except httpx.TimeoutException:
            return EnrichmentError(
                error="api_error",
                message="Request to Apollo timed out",
                linkedin_url=person.linkedin_url,
            )
        except httpx.RequestError:
            return EnrichmentError(
                error="api_error",
                message="Apollo API unavailable",
                linkedin_url=person.linkedin_url,
            )


async def enrich_people_bulk(people: List[PersonInput]) -> List[EnrichmentResponse]:
    """Enrich multiple people via Apollo's bulk_match endpoint."""
    details = [_build_apollo_payload(person) for person in people]

    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        try:
            response = await client.post(
                f"{APOLLO_BASE_URL}/people/bulk_match",
                headers=_get_headers(),
                json={"details": details, "reveal_personal_emails": True},
            )

            if response.status_code != 200:
                error = _handle_apollo_error(response.status_code)
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
                    results.append(
                        _parse_apollo_response({"person": matches[i]}, person.linkedin_url)
                    )
                else:
                    results.append(
                        EnrichmentError(
                            error="not_found",
                            message="No email found for this LinkedIn profile",
                            linkedin_url=person.linkedin_url,
                        )
                    )

            return results

        except httpx.TimeoutException:
            return [
                EnrichmentError(
                    error="api_error",
                    message="Request to Apollo timed out",
                    linkedin_url=person.linkedin_url,
                )
                for person in people
            ]
        except httpx.RequestError:
            return [
                EnrichmentError(
                    error="api_error",
                    message="Apollo API unavailable",
                    linkedin_url=person.linkedin_url,
                )
                for person in people
            ]
