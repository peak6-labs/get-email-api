import asyncio
from typing import Dict, Optional
import httpx
from app.schemas import PersonInput, EnrichmentResponse, ProviderSource
from app.services.base import TIMEOUT, create_success, create_error, handle_http_error


SNOV_BASE_URL = "https://api.snov.io"
PROVIDER_NAME: ProviderSource = "snov"
MAX_POLL_ATTEMPTS = 10
POLL_INTERVAL = 2.0  # seconds


async def _get_access_token(api_key: str) -> Optional[str]:
    """Snov.io uses OAuth - exchange API key (client_id:client_secret) for access token."""
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


async def _get_profile_from_linkedin(client: httpx.AsyncClient, access_token: str, linkedin_url: str) -> Optional[Dict]:
    """Get profile data (name, company) from LinkedIn URL."""
    try:
        start_response = await client.post(
            f"{SNOV_BASE_URL}/v2/li-profiles-by-urls/start",
            headers={"Authorization": f"Bearer {access_token}"},
            data={"urls[]": linkedin_url},
        )

        if start_response.status_code not in (200, 202):
            return None

        start_data = start_response.json()
        task_hash = start_data.get("task_hash") or start_data.get("data", {}).get("task_hash")

        if not task_hash:
            return None

        # Poll for results
        for _ in range(MAX_POLL_ATTEMPTS):
            await asyncio.sleep(POLL_INTERVAL)

            result_response = await client.get(
                f"{SNOV_BASE_URL}/v2/li-profiles-by-urls/result",
                headers={"Authorization": f"Bearer {access_token}"},
                params={"task_hash": task_hash},
            )

            if result_response.status_code != 200:
                continue

            result_data = result_response.json()
            status = result_data.get("status")

            if status == "in_progress":
                continue

            if status == "completed":
                data_items = result_data.get("data", [])
                if data_items:
                    item = data_items[0] if isinstance(data_items, list) else data_items
                    return item.get("result", item)

            break

    except Exception:
        pass

    return None


async def _find_email_by_name_domain(client: httpx.AsyncClient, access_token: str, first_name: str, last_name: str, domain: str) -> Optional[str]:
    """Find email using name + company domain."""
    try:
        start_response = await client.post(
            f"{SNOV_BASE_URL}/v2/emails-by-domain-by-name/start",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            },
            json={
                "rows": [{
                    "first_name": first_name,
                    "last_name": last_name,
                    "domain": domain,
                }]
            },
        )

        if start_response.status_code != 200:
            return None

        start_data = start_response.json()
        task_hash = start_data.get("data", {}).get("task_hash")

        if not task_hash:
            return None

        # Poll for results
        for _ in range(MAX_POLL_ATTEMPTS):
            await asyncio.sleep(POLL_INTERVAL)

            result_response = await client.get(
                f"{SNOV_BASE_URL}/v2/emails-by-domain-by-name/result",
                headers={"Authorization": f"Bearer {access_token}"},
                params={"task_hash": task_hash},
            )

            if result_response.status_code != 200:
                continue

            result_data = result_response.json()
            status = result_data.get("status")

            if status == "in_progress":
                continue

            if status == "completed":
                data_items = result_data.get("data", [])
                if data_items:
                    item = data_items[0] if isinstance(data_items, list) else data_items
                    results = item.get("result", [])
                    if results:
                        return results[0].get("email")

            break

    except Exception:
        pass

    return None


def _extract_domain_from_url(url: str) -> Optional[str]:
    """Extract domain from company URL."""
    if not url:
        return None
    # Remove protocol
    domain = url.replace("https://", "").replace("http://", "").replace("www.", "")
    # Remove path
    domain = domain.split("/")[0]
    return domain if domain else None


async def enrich(person: PersonInput, api_key: str) -> EnrichmentResponse:
    """
    Enrich a person via Snov.io's API.

    Two-step process:
    1. Get profile data from LinkedIn URL (name, company)
    2. Find email using name + company domain
    """
    access_token = await _get_access_token(api_key)
    if not access_token:
        return create_error("auth_error", "Invalid Snov.io API credentials", person.linkedin_url)

    async with httpx.AsyncClient(timeout=60.0) as client:  # Longer timeout for multi-step process
        try:
            # Step 1: Get profile from LinkedIn URL
            profile = await _get_profile_from_linkedin(client, access_token, person.linkedin_url)

            # Extract name - prefer from profile, fall back to input
            first_name = None
            last_name = None
            company_domain = None

            if profile:
                first_name = profile.get("first_name")
                last_name = profile.get("last_name")

                # Get company domain from positions
                positions = profile.get("positions", [])
                if positions:
                    company_url = positions[0].get("url")
                    company_domain = _extract_domain_from_url(company_url)

            # Fall back to input data if profile didn't have info
            if not first_name and person.first_name:
                first_name = person.first_name
            if not last_name and person.last_name:
                last_name = person.last_name
            if not first_name and not last_name and person.name:
                parts = person.name.strip().split(maxsplit=1)
                first_name = parts[0] if parts else None
                last_name = parts[1] if len(parts) > 1 else None

            # Fall back to input domain
            if not company_domain and person.domain:
                company_domain = person.domain

            if not first_name or not last_name:
                return create_error("not_found", "Could not determine name from Snov.io profile", person.linkedin_url)

            if not company_domain:
                return create_error("not_found", "Could not determine company domain from Snov.io profile", person.linkedin_url)

            # Step 2: Find email using name + domain
            email = await _find_email_by_name_domain(client, access_token, first_name, last_name, company_domain)

            if not email:
                return create_error("not_found", "No email found in Snov.io", person.linkedin_url)

            # Build full name
            full_name = f"{first_name} {last_name}".strip()

            # Extract title and company from profile
            title = None
            company = None
            if profile:
                positions = profile.get("positions", [])
                if positions:
                    title = positions[0].get("title")
                    company = positions[0].get("name")

            return create_success(
                email=email,
                linkedin_url=person.linkedin_url,
                source=PROVIDER_NAME,
                name=full_name or None,
                title=title,
                company=company,
            )

        except httpx.TimeoutException:
            return create_error("api_error", "Snov.io request timed out", person.linkedin_url)
        except httpx.RequestError:
            return create_error("api_error", "Snov.io API unavailable", person.linkedin_url)
