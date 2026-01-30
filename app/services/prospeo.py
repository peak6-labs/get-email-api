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
            if data.get("error") is True:
                error_msg = data.get("message", "No match found in Prospeo")
                return create_error("not_found", error_msg, person.linkedin_url)

            # Extract person data (new format uses 'person', old used 'response')
            person_data = data.get("person") or data.get("response", data)

            if not person_data:
                return create_error("not_found", "No profile found in Prospeo", person.linkedin_url)

            # Email can be a string or an object {status, revealed, email}
            email_data = person_data.get("email")
            email = None
            if isinstance(email_data, str):
                email = email_data
            elif isinstance(email_data, dict):
                if email_data.get("status") == "VERIFIED" or email_data.get("revealed"):
                    email = email_data.get("email")

            if not email:
                return create_error("not_found", "No email found in Prospeo", person.linkedin_url)

            # Extract name and job info
            full_name = person_data.get("full_name") or person_data.get("name")
            title = person_data.get("current_job_title") or person_data.get("title") or person_data.get("headline")

            # Company might be nested
            company_data = data.get("company") or person_data.get("company")
            company = None
            if isinstance(company_data, dict):
                company = company_data.get("name")
            elif isinstance(company_data, str):
                company = company_data

            return create_success(
                email=email,
                linkedin_url=person_data.get("linkedin_url") or person.linkedin_url,
                source=PROVIDER_NAME,
                name=full_name,
                title=title,
                company=company,
            )

        except httpx.TimeoutException:
            return create_error("api_error", "Prospeo request timed out", person.linkedin_url)
        except httpx.RequestError:
            return create_error("api_error", "Prospeo API unavailable", person.linkedin_url)
