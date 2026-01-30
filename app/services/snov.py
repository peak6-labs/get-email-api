from typing import Dict, Optional
import httpx
from app.schemas import PersonInput, EnrichmentResponse, ProviderSource
from app.services.base import TIMEOUT, create_success, create_error, handle_http_error


SNOV_BASE_URL = "https://api.snov.io"
PROVIDER_NAME: ProviderSource = "snov"


def _get_headers() -> Dict[str, str]:
    return {
        "Content-Type": "application/json",
    }


async def _get_access_token(api_key: str) -> Optional[str]:
    """Snov.io uses OAuth - exchange API key (client_id:client_secret) for access token."""
    # API key format: "client_id:client_secret"
    parts = api_key.split(":")
    if len(parts) != 2:
        return None

    client_id, client_secret = parts

    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        try:
            response = await client.post(
                f"{SNOV_BASE_URL}/v1/oauth/access_token",
                json={
                    "grant_type": "client_credentials",
                    "client_id": client_id,
                    "client_secret": client_secret,
                },
            )
            if response.status_code == 200:
                return response.json().get("access_token")
        except Exception:
            pass
    return None


async def enrich(person: PersonInput, api_key: str) -> EnrichmentResponse:
    """Enrich a person via Snov.io's get-profile-by-social-url endpoint."""
    # Get OAuth access token
    access_token = await _get_access_token(api_key)
    if not access_token:
        return create_error("auth_error", "Invalid Snov.io API credentials", person.linkedin_url)

    payload = {
        "url": person.linkedin_url,
        "access_token": access_token,
    }

    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        try:
            response = await client.post(
                f"{SNOV_BASE_URL}/v1/get-profile-by-social-url",
                headers=_get_headers(),
                json=payload,
            )

            if response.status_code != 200:
                return handle_http_error(response.status_code, "Snov.io", person.linkedin_url)

            data = response.json()

            # Check for success
            if not data.get("success", True):
                return create_error("not_found", "No match found in Snov.io", person.linkedin_url)

            # Extract email
            email = data.get("email")
            if not email and data.get("emails"):
                emails = data.get("emails", [])
                email = emails[0] if emails else None

            if not email:
                return create_error("not_found", "No email found in Snov.io", person.linkedin_url)

            # Build name
            first_name = data.get("firstName", "")
            last_name = data.get("lastName", "")
            name = f"{first_name} {last_name}".strip() or data.get("name")

            # Extract job info
            current_job = data.get("currentJob", {})
            title = current_job.get("position") if isinstance(current_job, dict) else None
            company = current_job.get("companyName") if isinstance(current_job, dict) else None

            # Extract LinkedIn URL from social data
            social = data.get("social", {})
            linkedin = social.get("linkedin") if isinstance(social, dict) else None

            return create_success(
                email=email,
                linkedin_url=linkedin or person.linkedin_url,
                source=PROVIDER_NAME,
                name=name or None,
                title=title,
                company=company,
            )

        except httpx.TimeoutException:
            return create_error("api_error", "Snov.io request timed out", person.linkedin_url)
        except httpx.RequestError:
            return create_error("api_error", "Snov.io API unavailable", person.linkedin_url)
