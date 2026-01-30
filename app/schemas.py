from typing import List, Literal, Optional, Union
from pydantic import BaseModel, Field


# Provider sources
ProviderSource = Literal["apollo", "rocketreach", "lusha", "prospeo", "snov"]


class ApiKeys(BaseModel):
    """Optional API keys that override environment defaults."""
    apollo: Optional[str] = None
    rocketreach: Optional[str] = None
    lusha: Optional[str] = None
    prospeo: Optional[str] = None
    snov: Optional[str] = None


class PersonInput(BaseModel):
    linkedin_url: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    name: Optional[str] = None
    company: Optional[str] = None
    domain: Optional[str] = None
    title: Optional[str] = None
    phone: Optional[str] = None


class EnrichmentRequest(BaseModel):
    """Single enrichment request with optional API keys."""
    person: PersonInput
    api_keys: Optional[ApiKeys] = None
    providers: Optional[List[ProviderSource]] = Field(
        default=None,
        description="Optional list of providers to use, in order. Overrides default provider order."
    )


class EnrichmentSuccess(BaseModel):
    success: Literal[True] = True
    email: str
    name: Optional[str] = None
    title: Optional[str] = None
    company: Optional[str] = None
    linkedin_url: str
    source: ProviderSource = "apollo"


class EnrichmentError(BaseModel):
    success: Literal[False] = False
    error: Literal["not_found", "rate_limit", "auth_error", "api_error", "validation_error"]
    message: str
    linkedin_url: Optional[str] = None


EnrichmentResponse = Union[EnrichmentSuccess, EnrichmentError]


class BulkEnrichmentRequest(BaseModel):
    people: List[PersonInput] = Field(..., max_length=10)
    api_keys: Optional[ApiKeys] = None
    providers: Optional[List[ProviderSource]] = Field(
        default=None,
        description="Optional list of providers to use, in order. Overrides default provider order."
    )


class BulkEnrichmentResponse(BaseModel):
    results: List[EnrichmentResponse]


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
