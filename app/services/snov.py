import asyncio
from typing import Dict, Optional
import httpx
from app.schemas import PersonInput, EnrichmentResponse, ProviderSource
from app.services.base import TIMEOUT, create_success, create_error, handle_http_error


SNOV_BASE_URL = "https://api.snov.io"
PROVIDER_NAME: ProviderSource = "snov"
MAX_POLL_ATTEMPTS = 10
POLL_INTERVAL = 2.0  # seconds


def _get_headers(access_token: str) -> Dict[str, str]:
    return {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {access_token}",
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
    """Enrich a person via Snov.io's v2 LinkedIn profiles endpoint (async two-step process)."""
    # Get OAuth access token
    access_token = await _get_access_token(api_key)
    if not access_token:
        return create_error("auth_error", "Invalid Snov.io API credentials", person.linkedin_url)

    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        try:
            # Step 1: Submit the LinkedIn URL for processing
            # Snov.io expects urls[] as form data
            start_response = await client.post(
                f"{SNOV_BASE_URL}/v2/li-profiles-by-urls/start",
                headers={"Authorization": f"Bearer {access_token}"},
                data={"urls[]": person.linkedin_url},
            )

            # 200 = immediate result, 202 = accepted for async processing
            if start_response.status_code not in (200, 202):
                return handle_http_error(start_response.status_code, "Snov.io", person.linkedin_url)

            start_data = start_response.json()
            # task_hash can be at top level or nested in data
            task_hash = start_data.get("task_hash") or start_data.get("data", {}).get("task_hash")

            if not task_hash:
                return create_error("api_error", "Snov.io did not return task hash", person.linkedin_url)

            # Step 2: Poll for results
            for _ in range(MAX_POLL_ATTEMPTS):
                await asyncio.sleep(POLL_INTERVAL)

                result_response = await client.get(
                    f"{SNOV_BASE_URL}/v2/li-profiles-by-urls/result",
                    headers={"Authorization": f"Bearer {access_token}"},
                    params={"task_hash": task_hash},
                )

                if result_response.status_code != 200:
                    continue  # Keep polling

                result_data = result_response.json()
                status = result_data.get("status")

                if status == "in_progress":
                    continue  # Still processing

                if status == "completed":
                    data_items = result_data.get("data", [])
                    if not data_items:
                        return create_error("not_found", "No profile found in Snov.io", person.linkedin_url)

                    # Data structure: [{url: "...", result: {profile data}}]
                    item = data_items[0] if isinstance(data_items, list) else data_items
                    profile = item.get("result", item) if isinstance(item, dict) else item

                    if not profile:
                        return create_error("not_found", "No profile data in Snov.io response", person.linkedin_url)

                    # Extract email
                    email = profile.get("email")
                    if not email and profile.get("emails"):
                        emails = profile.get("emails", [])
                        if emails:
                            # emails can be list of strings or list of dicts
                            first_email = emails[0]
                            email = first_email if isinstance(first_email, str) else first_email.get("email")

                    if not email:
                        return create_error("not_found", "No email found in Snov.io", person.linkedin_url)

                    # Build name
                    first_name = profile.get("firstName", "") or profile.get("first_name", "")
                    last_name = profile.get("lastName", "") or profile.get("last_name", "")
                    name = f"{first_name} {last_name}".strip() or profile.get("name")

                    # Extract title and company from positions if available
                    title = None
                    company = None
                    positions = profile.get("positions", [])
                    if positions and isinstance(positions, list):
                        current_pos = positions[0]
                        title = current_pos.get("title")
                        company = current_pos.get("name")

                    return create_success(
                        email=email,
                        linkedin_url=person.linkedin_url,
                        source=PROVIDER_NAME,
                        name=name or None,
                        title=title or profile.get("position") or profile.get("title"),
                        company=company or profile.get("company") or profile.get("company_name"),
                    )

                # Status is error or unknown
                return create_error("not_found", "Snov.io lookup failed", person.linkedin_url)

            # Exhausted poll attempts
            return create_error("api_error", "Snov.io request timed out waiting for results", person.linkedin_url)

        except httpx.TimeoutException:
            return create_error("api_error", "Snov.io request timed out", person.linkedin_url)
        except httpx.RequestError:
            return create_error("api_error", "Snov.io API unavailable", person.linkedin_url)
