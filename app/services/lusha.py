from typing import Dict
import httpx
from app.schemas import PersonInput, EnrichmentResponse, ProviderSource
from app.services.base import TIMEOUT, create_success, create_error, handle_http_error, parse_name


LUSHA_BASE_URL = "https://api.lusha.com"
PROVIDER_NAME: ProviderSource = "lusha"


def _get_headers(api_key: str) -> Dict[str, str]:
    return {
        "Content-Type": "application/json",
        "api_key": api_key,
    }


async def enrich(person: PersonInput, api_key: str) -> EnrichmentResponse:
    """Enrich a person via Lusha's person endpoint."""
    # Build query parameters
    params: Dict[str, str] = {
        "revealEmails": "true",
        "revealPhones": "false",
    }

    if person.linkedin_url:
        params["linkedinUrl"] = person.linkedin_url

    first_name, last_name = parse_name(person)
    if first_name:
        params["firstName"] = first_name
    if last_name:
        params["lastName"] = last_name
    if person.company:
        params["companyName"] = person.company
    if person.domain:
        params["companyDomain"] = person.domain

    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        try:
            response = await client.get(
                f"{LUSHA_BASE_URL}/v2/person",
                headers=_get_headers(api_key),
                params=params,
            )

            if response.status_code != 200:
                return handle_http_error(response.status_code, "Lusha", person.linkedin_url)

            data = response.json()

            # Lusha response structure: {contact: {data: {...}, error: {...}}}
            contact = data.get("contact", data)

            # Check for error in response
            error_info = contact.get("error")
            if error_info and error_info.get("name") == "EMPTY_DATA":
                return create_error("not_found", "No match found in Lusha", person.linkedin_url)

            person_data = contact.get("data") or data.get("data", data)

            if not person_data:
                return create_error("not_found", "No profile data in Lusha response", person.linkedin_url)

            # Extract email from emailAddresses array
            email = None
            email_addresses = person_data.get("emailAddresses", [])
            if email_addresses:
                # Prefer work email
                for e in email_addresses:
                    if e.get("type") == "work":
                        email = e.get("email")
                        break
                if not email:
                    email = email_addresses[0].get("email")

            if not email:
                return create_error("not_found", "No email found in Lusha", person.linkedin_url)

            full_name = person_data.get("fullName") or f"{person_data.get('firstName', '')} {person_data.get('lastName', '')}".strip()

            company_data = person_data.get("company")
            company_name = None
            if isinstance(company_data, dict):
                company_name = company_data.get("name")
            elif isinstance(company_data, str):
                company_name = company_data

            return create_success(
                email=email,
                linkedin_url=person.linkedin_url,
                source=PROVIDER_NAME,
                name=full_name or None,
                title=person_data.get("jobTitle"),
                company=company_name,
            )

        except httpx.TimeoutException:
            return create_error("api_error", "Lusha request timed out", person.linkedin_url)
        except httpx.RequestError:
            return create_error("api_error", "Lusha API unavailable", person.linkedin_url)
