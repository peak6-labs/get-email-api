from typing import Optional
from app.schemas import PersonInput, EnrichmentSuccess, EnrichmentError, ProviderSource


TIMEOUT = 30.0


def create_success(
    email: str,
    linkedin_url: str,
    source: ProviderSource,
    name: Optional[str] = None,
    title: Optional[str] = None,
    company: Optional[str] = None,
) -> EnrichmentSuccess:
    """Create a standardized success response."""
    return EnrichmentSuccess(
        email=email,
        name=name,
        title=title,
        company=company,
        linkedin_url=linkedin_url,
        source=source,
    )


def create_error(
    error_type: str,
    message: str,
    linkedin_url: Optional[str] = None,
) -> EnrichmentError:
    """Create a standardized error response."""
    return EnrichmentError(
        error=error_type,
        message=message,
        linkedin_url=linkedin_url,
    )


def handle_http_error(status_code: int, provider: str, linkedin_url: Optional[str] = None) -> EnrichmentError:
    """Convert HTTP status codes to standardized errors."""
    if status_code == 401:
        return create_error("auth_error", f"Invalid {provider} API key", linkedin_url)
    elif status_code == 429:
        return create_error("rate_limit", f"{provider} rate limit exceeded", linkedin_url)
    else:
        return create_error("api_error", f"{provider} API error (HTTP {status_code})", linkedin_url)


def parse_name(person: PersonInput) -> tuple:
    """Extract first_name and last_name, parsing from name if needed."""
    first_name = person.first_name
    last_name = person.last_name

    if not first_name and not last_name and person.name:
        parts = person.name.strip().split(maxsplit=1)
        first_name = parts[0] if parts else None
        last_name = parts[1] if len(parts) > 1 else None

    return first_name, last_name
