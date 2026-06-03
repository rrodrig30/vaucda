

---

## 6. EPIC FHIR Integration Layer

### 6.1 OAuth 2.0 SMART on FHIR with PKCE

#### 6.1.1 Authorization Flow Implementation

```python
# epic_fhir/oauth.py
import hashlib
import base64
import secrets
import urllib.parse
from dataclasses import dataclass, field
from typing import Optional, Dict
from datetime import datetime, timedelta
import httpx

@dataclass
class SMARTConfig:
    """SMART on FHIR OAuth 2.0 configuration."""
    fhir_base_url: str
    client_id: str
    redirect_uri: str
    scopes: str
    authorize_endpoint: Optional[str] = None
    token_endpoint: Optional[str] = None

    # PKCE parameters (generated per session)
    code_verifier: str = field(default_factory=lambda: "")
    code_challenge: str = field(default_factory=lambda: "")
    state: str = field(default_factory=lambda: "")

    # SMART on FHIR well-known endpoints
    smart_configuration_url: str = field(default="")

    def __post_init__(self):
        if not self.smart_configuration_url:
            self.smart_configuration_url = (
                f"{self.fhir_base_url}/.well-known/smart-configuration"
            )

    def generate_pkce(self) -> None:
        """Generate PKCE code verifier and challenge per RFC 7636."""
        # Generate 32-byte random code verifier (base64url encoded = 43 chars)
        self.code_verifier = base64.urlsafe_b64encode(
            secrets.token_bytes(32)
        ).rstrip(b'=').decode('ascii')

        # Generate code challenge using S256 method
        digest = hashlib.sha256(self.code_verifier.encode('ascii')).digest()
        self.code_challenge = base64.urlsafe_b64encode(
            digest
        ).rstrip(b'=').decode('ascii')

        # Generate state parameter for CSRF protection
        self.state = secrets.token_hex(16)


class SMARTAuthClient:
    """SMART on FHIR OAuth 2.0 authorization client with PKCE."""

    def __init__(self, config: SMARTConfig):
        self.config = config
        self._http_client = httpx.AsyncClient(timeout=30.0)
        self._access_token: Optional[str] = None
        self._refresh_token: Optional[str] = None
        self._token_expiry: Optional[datetime] = None
        self._patient_id: Optional[str] = None

    async def discover_endpoints(self) -> None:
        """Discover SMART on FHIR authorization endpoints from well-known."""
        response = await self._http_client.get(
            self.config.smart_configuration_url
        )
        response.raise_for_status()
        smart_config = response.json()

        self.config.authorize_endpoint = smart_config["authorization_endpoint"]
        self.config.token_endpoint = smart_config["token_endpoint"]

    def get_authorization_url(self) -> str:
        """Build OAuth 2.0 authorization URL with PKCE parameters.

        Returns:
            Complete authorization URL for browser redirect
        """
        self.config.generate_pkce()

        params = {
            "response_type": "code",
            "client_id": self.config.client_id,
            "redirect_uri": self.config.redirect_uri,
            "scope": self.config.scopes,
            "state": self.config.state,
            "aud": self.config.fhir_base_url,
            "code_challenge": self.config.code_challenge,
            "code_challenge_method": "S256",
        }

        return f"{self.config.authorize_endpoint}?{urllib.parse.urlencode(params)}"

    async def exchange_code(self, authorization_code: str, state: str) -> Dict:
        """Exchange authorization code for access token.

        Args:
            authorization_code: Code returned from OAuth redirect
            state: State parameter for CSRF validation

        Returns:
            Token response dictionary

        Raises:
            ValueError: If state parameter doesn't match (CSRF detected)
            httpx.HTTPStatusError: If token exchange fails
        """
        # Validate state parameter (CSRF protection)
        if state != self.config.state:
            raise ValueError("State parameter mismatch - potential CSRF attack")

        token_data = {
            "grant_type": "authorization_code",
            "code": authorization_code,
            "redirect_uri": self.config.redirect_uri,
            "client_id": self.config.client_id,
            "code_verifier": self.config.code_verifier,
        }

        response = await self._http_client.post(
            self.config.token_endpoint,
            data=token_data,
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )
        response.raise_for_status()
        token_response = response.json()

        # Store tokens in memory only (never persisted)
        self._access_token = token_response["access_token"]
        self._refresh_token = token_response.get("refresh_token")
        self._token_expiry = datetime.utcnow() + timedelta(
            seconds=token_response.get("expires_in", 3600)
        )
        self._patient_id = token_response.get("patient")

        return token_response

    async def refresh_access_token(self) -> Dict:
        """Refresh the access token using the refresh token.

        Returns:
            New token response dictionary

        Raises:
            RuntimeError: If no refresh token is available
        """
        if not self._refresh_token:
            raise RuntimeError("No refresh token available - re-authorization required")

        token_data = {
            "grant_type": "refresh_token",
            "refresh_token": self._refresh_token,
            "client_id": self.config.client_id,
        }

        response = await self._http_client.post(
            self.config.token_endpoint,
            data=token_data,
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )
        response.raise_for_status()
        token_response = response.json()

        self._access_token = token_response["access_token"]
        if "refresh_token" in token_response:
            self._refresh_token = token_response["refresh_token"]
        self._token_expiry = datetime.utcnow() + timedelta(
            seconds=token_response.get("expires_in", 3600)
        )

        return token_response

    async def get_valid_token(self) -> str:
        """Get a valid access token, refreshing if needed.

        Returns:
            Valid access token string

        Raises:
            RuntimeError: If no valid token and refresh fails
        """
        if self._access_token and self._token_expiry:
            # Refresh 60 seconds before expiry
            if datetime.utcnow() < self._token_expiry - timedelta(seconds=60):
                return self._access_token

        if self._refresh_token:
            await self.refresh_access_token()
            return self._access_token

        raise RuntimeError("No valid token - authorization required")

    @property
    def patient_id(self) -> Optional[str]:
        """Get the patient ID from the launch context."""
        return self._patient_id

    @property
    def is_authenticated(self) -> bool:
        """Check if client has a valid (non-expired) token."""
        if not self._access_token or not self._token_expiry:
            return False
        return datetime.utcnow() < self._token_expiry

    async def revoke_token(self) -> None:
        """Revoke current tokens and clear from memory."""
        self._access_token = None
        self._refresh_token = None
        self._token_expiry = None
        self._patient_id = None

    async def close(self) -> None:
        """Close HTTP client and clear all tokens from memory."""
        await self.revoke_token()
        await self._http_client.aclose()
```

### 6.2 Async FHIR R4 Client

```python
# epic_fhir/client.py
from dataclasses import dataclass
from typing import Optional, List, Dict, Any
import httpx
from .oauth import SMARTAuthClient

@dataclass
class FHIRClientConfig:
    """FHIR R4 client configuration."""
    base_url: str
    timeout: float = 30.0
    max_pages: int = 10          # Maximum pagination depth
    page_size: int = 100         # Default _count parameter
    retry_attempts: int = 3
    retry_delay: float = 1.0

class AsyncFHIRClient:
    """Async FHIR R4 client for EPIC EHR integration.

    Handles authenticated FHIR queries with automatic pagination,
    retry logic, and Bundle processing.
    """

    def __init__(self, config: FHIRClientConfig, auth: SMARTAuthClient):
        self.config = config
        self.auth = auth
        self._http_client = httpx.AsyncClient(
            base_url=config.base_url,
            timeout=config.timeout,
            headers={"Accept": "application/fhir+json"}
        )

    async def _get_auth_headers(self) -> Dict[str, str]:
        """Get authorization headers with valid token."""
        token = await self.auth.get_valid_token()
        return {
            "Authorization": f"Bearer {token}",
            "Accept": "application/fhir+json"
        }

    async def search(
        self,
        resource_type: str,
        params: Optional[Dict[str, str]] = None,
        patient_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Search FHIR resources with automatic pagination.

        Args:
            resource_type: FHIR resource type (e.g., "Observation")
            params: Search parameters
            patient_id: Patient ID for scoped queries

        Returns:
            List of FHIR resource dictionaries from all pages
        """
        all_resources = []
        search_params = dict(params or {})

        # Add patient scope if provided
        if patient_id:
            search_params["patient"] = patient_id

        # Add default page size
        if "_count" not in search_params:
            search_params["_count"] = str(self.config.page_size)

        headers = await self._get_auth_headers()
        url = f"/{resource_type}"

        for page in range(self.config.max_pages):
            for attempt in range(self.config.retry_attempts):
                try:
                    if page == 0:
                        response = await self._http_client.get(
                            url, params=search_params, headers=headers
                        )
                    else:
                        # Follow Bundle.link "next" URL for pagination
                        response = await self._http_client.get(
                            url, headers=headers
                        )

                    response.raise_for_status()
                    bundle = response.json()
                    break

                except httpx.HTTPStatusError as e:
                    if e.response.status_code == 401:
                        # Token expired - refresh and retry
                        await self.auth.refresh_access_token()
                        headers = await self._get_auth_headers()
                        continue
                    if attempt == self.config.retry_attempts - 1:
                        raise
                    await self._delay(attempt)

                except httpx.TransportError:
                    if attempt == self.config.retry_attempts - 1:
                        raise
                    await self._delay(attempt)

            # Extract resources from Bundle
            if bundle.get("resourceType") == "Bundle":
                entries = bundle.get("entry", [])
                for entry in entries:
                    resource = entry.get("resource", {})
                    if resource:
                        all_resources.append(resource)

                # Check for next page
                next_link = self._get_next_link(bundle)
                if next_link:
                    url = next_link
                else:
                    break
            else:
                # Single resource response
                all_resources.append(bundle)
                break

        return all_resources

    async def read(
        self,
        resource_type: str,
        resource_id: str
    ) -> Dict[str, Any]:
        """Read a single FHIR resource by ID.

        Args:
            resource_type: FHIR resource type
            resource_id: Resource ID

        Returns:
            FHIR resource dictionary
        """
        headers = await self._get_auth_headers()
        response = await self._http_client.get(
            f"/{resource_type}/{resource_id}",
            headers=headers
        )
        response.raise_for_status()
        return response.json()

    def _get_next_link(self, bundle: Dict) -> Optional[str]:
        """Extract 'next' pagination link from Bundle."""
        for link in bundle.get("link", []):
            if link.get("relation") == "next":
                return link.get("url")
        return None

    async def _delay(self, attempt: int) -> None:
        """Exponential backoff delay for retries."""
        import asyncio
        delay = self.config.retry_delay * (2 ** attempt)
        await asyncio.sleep(delay)

    async def close(self) -> None:
        """Close HTTP client."""
        await self._http_client.aclose()
```

### 6.3 Resource-Specific Fetchers

#### 6.3.1 Lab Observation Fetcher (Dual-Strategy)

```python
# epic_fhir/fetchers/lab_fetcher.py
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from ..client import AsyncFHIRClient
from ...data_layer.loinc_registry import (
    UROLOGY_LOINC_REGISTRY, LabCategory, get_loinc_codes_for_category,
    get_all_targeted_loinc_codes, get_loinc_entry
)

@dataclass
class LabResult:
    """Structured lab result from FHIR Observation."""
    loinc_code: str
    display_name: str
    value: str
    unit: Optional[str]
    reference_range: Optional[str]
    effective_date: datetime
    status: str
    category: LabCategory
    is_abnormal: bool = False
    interpretation: Optional[str] = None

class LabFetcher:
    """Fetch and organize laboratory results from EPIC FHIR.

    Implements dual-strategy retrieval:
    1. Temporal window: ALL labs from last 6 months
    2. Targeted LOINC: Urology-specific labs regardless of date
    """

    def __init__(self, fhir_client: AsyncFHIRClient):
        self.client = fhir_client

    async def fetch_all_labs(
        self,
        patient_id: str
    ) -> Dict[str, List[LabResult]]:
        """Fetch all labs using dual-strategy approach.

        Args:
            patient_id: FHIR Patient resource ID

        Returns:
            Dictionary of lab results keyed by category
        """
        import asyncio

        # Execute both strategies concurrently
        temporal_task = asyncio.create_task(
            self._fetch_temporal_labs(patient_id)
        )
        targeted_task = asyncio.create_task(
            self._fetch_targeted_urology_labs(patient_id)
        )

        temporal_results, targeted_results = await asyncio.gather(
            temporal_task, targeted_task
        )

        # Merge and deduplicate results
        all_results = self._merge_and_deduplicate(
            temporal_results, targeted_results
        )

        # Organize by category
        return self._organize_by_category(all_results)

    async def _fetch_temporal_labs(
        self,
        patient_id: str
    ) -> List[Dict[str, Any]]:
        """Strategy 1: Fetch ALL labs from last 6 months."""
        six_months_ago = (
            datetime.utcnow() - timedelta(days=180)
        ).strftime("%Y-%m-%d")

        return await self.client.search(
            "Observation",
            params={
                "category": "laboratory",
                "date": f"ge{six_months_ago}",
                "_sort": "-date",
            },
            patient_id=patient_id
        )

    async def _fetch_targeted_urology_labs(
        self,
        patient_id: str
    ) -> List[Dict[str, Any]]:
        """Strategy 2: Fetch urology-specific labs by LOINC (all dates)."""
        import asyncio

        # Split LOINC codes into batches to avoid URL length limits
        all_codes = [entry.code for entry in UROLOGY_LOINC_REGISTRY]
        batches = [all_codes[i:i+10] for i in range(0, len(all_codes), 10)]

        tasks = []
        for batch in batches:
            code_string = ",".join(batch)
            tasks.append(
                self.client.search(
                    "Observation",
                    params={
                        "code": code_string,
                        "_sort": "-date",
                    },
                    patient_id=patient_id
                )
            )

        results = await asyncio.gather(*tasks)
        return [obs for batch_result in results for obs in batch_result]

    def _merge_and_deduplicate(
        self,
        temporal: List[Dict],
        targeted: List[Dict]
    ) -> List[LabResult]:
        """Merge temporal and targeted results, removing duplicates."""
        seen_ids = set()
        merged = []

        for obs_list in [temporal, targeted]:
            for obs in obs_list:
                obs_id = obs.get("id", "")
                if obs_id in seen_ids:
                    continue
                seen_ids.add(obs_id)

                lab_result = self._parse_observation(obs)
                if lab_result:
                    merged.append(lab_result)

        # Sort by date (most recent first)
        merged.sort(key=lambda x: x.effective_date, reverse=True)
        return merged

    def _parse_observation(self, obs: Dict) -> Optional[LabResult]:
        """Parse FHIR Observation into LabResult."""
        # Extract LOINC code
        coding = self._get_loinc_coding(obs)
        if not coding:
            return None

        loinc_code = coding.get("code", "")
        display = coding.get("display", "Unknown Lab")

        # Look up in registry for category
        registry_entry = get_loinc_entry(loinc_code)
        category = registry_entry.category if registry_entry else LabCategory.GENERAL

        # Extract value
        value, unit = self._extract_value(obs)
        if value is None:
            return None

        # Extract date
        effective_date = self._parse_date(
            obs.get("effectiveDateTime", obs.get("issued", ""))
        )

        # Extract reference range
        ref_range = self._extract_reference_range(obs)

        # Check interpretation
        interpretation = self._extract_interpretation(obs)
        is_abnormal = interpretation in ("H", "L", "HH", "LL", "A", "AA")

        return LabResult(
            loinc_code=loinc_code,
            display_name=registry_entry.display_name if registry_entry else display,
            value=value,
            unit=unit,
            reference_range=ref_range,
            effective_date=effective_date,
            status=obs.get("status", "final"),
            category=category,
            is_abnormal=is_abnormal,
            interpretation=interpretation
        )

    def _get_loinc_coding(self, obs: Dict) -> Optional[Dict]:
        """Extract LOINC coding from Observation.code."""
        code_concept = obs.get("code", {})
        for coding in code_concept.get("coding", []):
            if coding.get("system") == "http://loinc.org":
                return coding
        # Fall back to first coding if no LOINC system
        codings = code_concept.get("coding", [])
        return codings[0] if codings else None

    def _extract_value(self, obs: Dict) -> tuple:
        """Extract value and unit from Observation."""
        # Quantity value
        if "valueQuantity" in obs:
            vq = obs["valueQuantity"]
            return str(vq.get("value", "")), vq.get("unit", "")

        # String value
        if "valueString" in obs:
            return obs["valueString"], None

        # CodeableConcept value
        if "valueCodeableConcept" in obs:
            cc = obs["valueCodeableConcept"]
            return cc.get("text", cc.get("coding", [{}])[0].get("display", "")), None

        return None, None

    def _extract_reference_range(self, obs: Dict) -> Optional[str]:
        """Extract reference range text from Observation."""
        ranges = obs.get("referenceRange", [])
        if ranges:
            rr = ranges[0]
            if "text" in rr:
                return rr["text"]
            low = rr.get("low", {}).get("value", "")
            high = rr.get("high", {}).get("value", "")
            if low and high:
                return f"{low}-{high}"
        return None

    def _extract_interpretation(self, obs: Dict) -> Optional[str]:
        """Extract interpretation code (H, L, N, etc.)."""
        interps = obs.get("interpretation", [])
        for interp in interps:
            for coding in interp.get("coding", []):
                return coding.get("code")
        return None

    def _parse_date(self, date_str: str) -> datetime:
        """Parse FHIR datetime string."""
        for fmt in [
            "%Y-%m-%dT%H:%M:%S.%fZ",
            "%Y-%m-%dT%H:%M:%SZ",
            "%Y-%m-%dT%H:%M:%S%z",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d",
        ]:
            try:
                return datetime.strptime(date_str.replace("+00:00", "Z"), fmt)
            except ValueError:
                continue
        return datetime.utcnow()

    def _organize_by_category(
        self,
        results: List[LabResult]
    ) -> Dict[str, List[LabResult]]:
        """Organize lab results into note-section categories."""
        organized = {
            "endocrine_labs": [],
            "stone_labs": [],
            "general_labs": [],
            "psa_values": [],
            "tumor_markers": [],
            "urinalysis": [],
        }

        category_mapping = {
            LabCategory.ENDOCRINE: "endocrine_labs",
            LabCategory.STONE: "stone_labs",
            LabCategory.GENERAL: "general_labs",
            LabCategory.RENAL: "general_labs",
            LabCategory.PROSTATE: "psa_values",
            LabCategory.TUMOR_MARKER: "tumor_markers",
            LabCategory.URINALYSIS: "urinalysis",
        }

        for result in results:
            target = category_mapping.get(result.category, "general_labs")
            organized[target].append(result)

        return organized
```

#### 6.3.2 Clinical Note Fetcher

```python
# epic_fhir/fetchers/note_fetcher.py
from typing import List, Dict, Optional
from dataclasses import dataclass
from datetime import datetime
import base64
from ..client import AsyncFHIRClient

@dataclass
class ClinicalNote:
    """Parsed clinical note from FHIR DocumentReference."""
    id: str
    date: datetime
    note_type: str          # "clinic_note", "procedure_note", "consult"
    author: Optional[str]
    content: str            # Full text content
    specialty: Optional[str]
    encounter_id: Optional[str]

class NoteFetcher:
    """Fetch urology clinical notes from EPIC FHIR."""

    # LOINC document type codes for urology-relevant notes
    UROLOGY_DOC_TYPES = [
        "11488-4",   # Consultation note
        "34117-2",   # History and physical note
        "28570-0",   # Procedure note
        "18842-5",   # Discharge summary
        "34111-5",   # Emergency department note
        "11506-3",   # Progress note
    ]

    def __init__(self, fhir_client: AsyncFHIRClient):
        self.client = fhir_client

    async def fetch_urology_notes(
        self,
        patient_id: str,
        max_notes: int = 20
    ) -> List[ClinicalNote]:
        """Fetch urology-relevant clinical notes.

        Args:
            patient_id: FHIR Patient resource ID
            max_notes: Maximum number of notes to retrieve

        Returns:
            List of parsed ClinicalNote objects sorted by date (newest first)
        """
        all_notes = []

        # Fetch DocumentReference resources
        doc_refs = await self.client.search(
            "DocumentReference",
            params={
                "category": "clinical-note",
                "_sort": "-date",
                "_count": str(max_notes),
            },
            patient_id=patient_id
        )

        for doc_ref in doc_refs:
            note = await self._parse_document_reference(doc_ref)
            if note and self._is_urology_relevant(note):
                all_notes.append(note)

        all_notes.sort(key=lambda n: n.date, reverse=True)
        return all_notes[:max_notes]

    async def _parse_document_reference(
        self,
        doc_ref: Dict
    ) -> Optional[ClinicalNote]:
        """Parse FHIR DocumentReference into ClinicalNote."""
        # Extract content
        content = await self._extract_content(doc_ref)
        if not content:
            return None

        # Extract date
        date_str = doc_ref.get("date", doc_ref.get("context", {}).get("period", {}).get("start", ""))
        date = self._parse_date(date_str)

        # Extract note type from type coding
        note_type = self._determine_note_type(doc_ref)

        # Extract author
        authors = doc_ref.get("author", [])
        author = authors[0].get("display") if authors else None

        # Extract specialty context
        specialty = self._extract_specialty(doc_ref)

        return ClinicalNote(
            id=doc_ref.get("id", ""),
            date=date,
            note_type=note_type,
            author=author,
            content=content,
            specialty=specialty,
            encounter_id=doc_ref.get("context", {}).get("encounter", [{}])[0].get("reference", "").replace("Encounter/", "") if doc_ref.get("context", {}).get("encounter") else None
        )

    async def _extract_content(self, doc_ref: Dict) -> Optional[str]:
        """Extract text content from DocumentReference."""
        for content_item in doc_ref.get("content", []):
            attachment = content_item.get("attachment", {})

            # Inline base64-encoded content
            if "data" in attachment:
                decoded = base64.b64decode(attachment["data"])
                return decoded.decode("utf-8", errors="replace")

            # URL reference to content
            if "url" in attachment:
                try:
                    response = await self.client._http_client.get(
                        attachment["url"],
                        headers=await self.client._get_auth_headers()
                    )
                    response.raise_for_status()
                    return response.text
                except Exception:
                    continue

        return None

    def _determine_note_type(self, doc_ref: Dict) -> str:
        """Determine note type from DocumentReference.type coding."""
        type_concept = doc_ref.get("type", {})
        for coding in type_concept.get("coding", []):
            code = coding.get("code", "")
            if code in ("11488-4", "11506-3"):
                return "clinic_note"
            elif code == "28570-0":
                return "procedure_note"
            elif code == "11488-4":
                return "consult"
            elif code == "34117-2":
                return "history_and_physical"
        return "clinic_note"

    def _is_urology_relevant(self, note: ClinicalNote) -> bool:
        """Check if a note is urology-relevant based on content/specialty."""
        if note.specialty and "urology" in note.specialty.lower():
            return True

        urology_keywords = [
            "urology", "urolog", "prostate", "bladder", "kidney",
            "psa", "bph", "ipss", "cystoscopy", "turp", "turbt",
            "nephrectomy", "orchiectomy", "vasectomy", "lithotripsy",
            "hematuria", "incontinence", "erectile", "testosterone",
            "gu exam", "genitourinary"
        ]

        content_lower = note.content.lower()
        return any(kw in content_lower for kw in urology_keywords)

    def _extract_specialty(self, doc_ref: Dict) -> Optional[str]:
        """Extract specialty from DocumentReference context."""
        context = doc_ref.get("context", {})
        practice_setting = context.get("practiceSetting", {})
        for coding in practice_setting.get("coding", []):
            return coding.get("display")
        return None

    def _parse_date(self, date_str: str) -> datetime:
        """Parse FHIR datetime string."""
        for fmt in ["%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%SZ",
                     "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"]:
            try:
                return datetime.strptime(date_str.replace("+00:00", "Z"), fmt)
            except ValueError:
                continue
        return datetime.utcnow()
```

#### 6.3.3 Imaging Report Fetcher

```python
# epic_fhir/fetchers/imaging_fetcher.py
from typing import List, Dict, Optional
from dataclasses import dataclass
from datetime import datetime
from ..client import AsyncFHIRClient

@dataclass
class ImagingReport:
    """Parsed imaging report from FHIR DiagnosticReport."""
    id: str
    date: datetime
    modality: str           # "CT", "MRI", "US", "XRAY", "NM"
    body_site: Optional[str]
    narrative: str           # Full report text
    conclusion: Optional[str]
    status: str
    performer: Optional[str]

class ImagingFetcher:
    """Fetch imaging reports from EPIC FHIR."""

    def __init__(self, fhir_client: AsyncFHIRClient):
        self.client = fhir_client

    async def fetch_imaging_reports(
        self,
        patient_id: str,
        max_reports: int = 50
    ) -> List[ImagingReport]:
        """Fetch all imaging reports for a patient.

        Args:
            patient_id: FHIR Patient resource ID
            max_reports: Maximum number of reports

        Returns:
            List of parsed ImagingReport objects (newest first)
        """
        reports = await self.client.search(
            "DiagnosticReport",
            params={
                "category": "IMG",
                "_sort": "-date",
                "_count": str(max_reports),
            },
            patient_id=patient_id
        )

        parsed = []
        for report in reports:
            imaging = self._parse_report(report)
            if imaging:
                parsed.append(imaging)

        return parsed

    def _parse_report(self, report: Dict) -> Optional[ImagingReport]:
        """Parse FHIR DiagnosticReport into ImagingReport."""
        # Extract narrative text
        narrative = ""
        if "presentedForm" in report:
            for form in report["presentedForm"]:
                if "data" in form:
                    import base64
                    narrative = base64.b64decode(form["data"]).decode("utf-8", errors="replace")
                    break
        if not narrative and "text" in report:
            narrative = report["text"].get("div", "")
            # Strip HTML tags
            import re
            narrative = re.sub(r'<[^>]+>', '', narrative)
        if not narrative:
            narrative = report.get("conclusion", "")

        if not narrative:
            return None

        # Extract modality from code
        modality = self._extract_modality(report)

        # Extract date
        date_str = report.get("effectiveDateTime", report.get("issued", ""))
        date = self._parse_date(date_str)

        # Extract body site
        body_site = None
        for coding in report.get("code", {}).get("coding", []):
            if coding.get("display"):
                body_site = coding["display"]
                break

        return ImagingReport(
            id=report.get("id", ""),
            date=date,
            modality=modality,
            body_site=body_site,
            narrative=narrative,
            conclusion=report.get("conclusion"),
            status=report.get("status", "final"),
            performer=self._extract_performer(report)
        )

    def _extract_modality(self, report: Dict) -> str:
        """Determine imaging modality from report code."""
        code_text = report.get("code", {}).get("text", "").upper()
        for coding in report.get("code", {}).get("coding", []):
            display = coding.get("display", "").upper()
            code_text = f"{code_text} {display}"

        modality_keywords = {
            "CT": ["CT", "COMPUTED TOMOGRAPHY", "CAT SCAN"],
            "MRI": ["MRI", "MAGNETIC RESONANCE", "MR "],
            "US": ["ULTRASOUND", "SONOGRAPHY", "US "],
            "XRAY": ["X-RAY", "XRAY", "RADIOGRAPH", "PLAIN FILM"],
            "NM": ["NUCLEAR", "BONE SCAN", "RENAL SCAN", "MAG3", "DMSA"],
            "FLUORO": ["FLUOROSCOPY", "VCUG", "CYSTOGRAM"],
        }

        for modality, keywords in modality_keywords.items():
            if any(kw in code_text for kw in keywords):
                return modality

        return "OTHER"

    def _extract_performer(self, report: Dict) -> Optional[str]:
        """Extract performer/radiologist name."""
        performers = report.get("performer", [])
        if performers:
            return performers[0].get("display")
        return None

    def _parse_date(self, date_str: str) -> datetime:
        """Parse FHIR datetime string."""
        for fmt in ["%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%SZ",
                     "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"]:
            try:
                return datetime.strptime(date_str.replace("+00:00", "Z"), fmt)
            except ValueError:
                continue
        return datetime.utcnow()
```

#### 6.3.4 Pathology Report Fetcher

```python
# epic_fhir/fetchers/pathology_fetcher.py
from typing import List, Dict, Optional
from dataclasses import dataclass
from datetime import datetime
from ..client import AsyncFHIRClient

@dataclass
class PathologySpecimen:
    """Individual specimen detail from pathology report."""
    site: str
    finding: str
    grade: Optional[str] = None
    gleason_score: Optional[str] = None
    grade_group: Optional[int] = None
    percent_involvement: Optional[float] = None
    margin_status: Optional[str] = None

@dataclass
class PathologyReport:
    """Parsed pathology report from FHIR DiagnosticReport."""
    id: str
    date: datetime
    procedure_type: str
    narrative: str
    conclusion: Optional[str]
    specimens: List[PathologySpecimen]
    status: str

class PathologyFetcher:
    """Fetch pathology reports from EPIC FHIR.

    Preserves specimen-level detail including anatomical locations,
    grades, Gleason scores, and percentages.
    """

    def __init__(self, fhir_client: AsyncFHIRClient):
        self.client = fhir_client

    async def fetch_pathology_reports(
        self,
        patient_id: str,
        max_reports: int = 20
    ) -> List[PathologyReport]:
        """Fetch all pathology reports for a patient.

        Args:
            patient_id: FHIR Patient resource ID
            max_reports: Maximum number of reports

        Returns:
            List of PathologyReport objects (newest first)
        """
        reports = await self.client.search(
            "DiagnosticReport",
            params={
                "category": "PAT",
                "_sort": "-date",
                "_count": str(max_reports),
            },
            patient_id=patient_id
        )

        parsed = []
        for report in reports:
            pathology = self._parse_report(report)
            if pathology:
                parsed.append(pathology)

        return parsed

    def _parse_report(self, report: Dict) -> Optional[PathologyReport]:
        """Parse FHIR DiagnosticReport into PathologyReport."""
        # Extract full narrative (critical: preserve ALL detail)
        narrative = self._extract_full_narrative(report)
        if not narrative:
            return None

        date_str = report.get("effectiveDateTime", report.get("issued", ""))
        date = self._parse_date(date_str)

        procedure_type = report.get("code", {}).get("text", "Surgical Pathology")

        # Parse specimens from narrative
        specimens = self._parse_specimens(narrative)

        return PathologyReport(
            id=report.get("id", ""),
            date=date,
            procedure_type=procedure_type,
            narrative=narrative,
            conclusion=report.get("conclusion"),
            specimens=specimens,
            status=report.get("status", "final")
        )

    def _extract_full_narrative(self, report: Dict) -> Optional[str]:
        """Extract complete pathology narrative preserving all detail."""
        # Check presentedForm first (most complete)
        if "presentedForm" in report:
            for form in report["presentedForm"]:
                if "data" in form:
                    import base64
                    return base64.b64decode(
                        form["data"]
                    ).decode("utf-8", errors="replace")

        # Fall back to text.div
        if "text" in report:
            import re
            html = report["text"].get("div", "")
            return re.sub(r'<[^>]+>', '', html).strip()

        # Fall back to conclusion
        return report.get("conclusion")

    def _parse_specimens(self, narrative: str) -> List[PathologySpecimen]:
        """Parse individual specimen details from pathology narrative.

        Extracts anatomical sites, findings, Gleason scores,
        grade groups, and percentage involvement.
        """
        import re
        specimens = []

        # Pattern for specimen blocks
        specimen_pattern = re.compile(
            r'(?:Specimen|Core|Site|Part)\s*[#\d]*[:\-]?\s*(.+?)(?=(?:Specimen|Core|Site|Part)\s*[#\d]*[:\-]|$)',
            re.IGNORECASE | re.DOTALL
        )

        # Gleason pattern
        gleason_pattern = re.compile(
            r'Gleason\s*(?:score|grade)?[:\s]*(\d)\s*\+\s*(\d)\s*=\s*(\d+)',
            re.IGNORECASE
        )

        # Grade group pattern
        grade_group_pattern = re.compile(
            r'Grade\s*Group[:\s]*(\d)',
            re.IGNORECASE
        )

        # Percent involvement pattern
        percent_pattern = re.compile(
            r'(\d+(?:\.\d+)?)\s*%\s*(?:involvement|tumor|cancer|carcinoma)',
            re.IGNORECASE
        )

        for match in specimen_pattern.finditer(narrative):
            text = match.group(1).strip()
            if len(text) < 5:
                continue

            specimen = PathologySpecimen(
                site=self._extract_site(text),
                finding=text[:500]  # Preserve up to 500 chars per specimen
            )

            # Extract Gleason
            gleason_match = gleason_pattern.search(text)
            if gleason_match:
                specimen.gleason_score = (
                    f"{gleason_match.group(1)}+{gleason_match.group(2)}"
                    f"={gleason_match.group(3)}"
                )
                # Derive grade group
                total = int(gleason_match.group(3))
                primary = int(gleason_match.group(1))
                if total <= 6:
                    specimen.grade_group = 1
                elif total == 7 and primary == 3:
                    specimen.grade_group = 2
                elif total == 7 and primary == 4:
                    specimen.grade_group = 3
                elif total == 8:
                    specimen.grade_group = 4
                elif total >= 9:
                    specimen.grade_group = 5

            # Override with explicit grade group if present
            gg_match = grade_group_pattern.search(text)
            if gg_match:
                specimen.grade_group = int(gg_match.group(1))

            # Extract percent involvement
            pct_match = percent_pattern.search(text)
            if pct_match:
                specimen.percent_involvement = float(pct_match.group(1))

            specimens.append(specimen)

        return specimens

    def _extract_site(self, text: str) -> str:
        """Extract anatomical site from specimen text."""
        import re
        site_patterns = [
            r'(left|right)\s+(base|mid|apex|lateral|medial)',
            r'(base|mid|apex|lateral|medial)\s+(left|right)',
            r'(periurethral|transition\s+zone|peripheral\s+zone)',
            r'(left|right)\s+(?:kidney|testis|ureter|prostate)',
        ]
        for pattern in site_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(0).strip().title()

        # Return first 50 chars as site descriptor
        return text[:50].split('\n')[0].strip()

    def _parse_date(self, date_str: str) -> datetime:
        for fmt in ["%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%SZ",
                     "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"]:
            try:
                return datetime.strptime(date_str.replace("+00:00", "Z"), fmt)
            except ValueError:
                continue
        return datetime.utcnow()
```

#### 6.3.5 Patient Demographics Fetcher

```python
# epic_fhir/fetchers/patient_fetcher.py
from typing import Dict, Optional, List
from dataclasses import dataclass
from datetime import datetime, date
from ..client import AsyncFHIRClient

@dataclass
class PatientDemographics:
    """Patient demographic information from FHIR Patient resource."""
    id: str
    name: str
    date_of_birth: Optional[date]
    age: Optional[int]
    gender: str
    race: Optional[str]
    ethnicity: Optional[str]
    marital_status: Optional[str]
    language: Optional[str]
    identifiers: Dict[str, str]    # MRN, SSN last 4, etc.

class PatientFetcher:
    """Fetch patient demographics from EPIC FHIR."""

    def __init__(self, fhir_client: AsyncFHIRClient):
        self.client = fhir_client

    async def fetch_patient(self, patient_id: str) -> PatientDemographics:
        """Fetch patient demographics by ID.

        Args:
            patient_id: FHIR Patient resource ID

        Returns:
            PatientDemographics with parsed fields
        """
        patient = await self.client.read("Patient", patient_id)
        return self._parse_patient(patient)

    def _parse_patient(self, patient: Dict) -> PatientDemographics:
        """Parse FHIR Patient resource into PatientDemographics."""
        # Parse name
        names = patient.get("name", [])
        name = self._format_name(names[0]) if names else "Unknown"

        # Parse DOB and calculate age
        dob_str = patient.get("birthDate", "")
        dob = None
        age = None
        if dob_str:
            dob = datetime.strptime(dob_str, "%Y-%m-%d").date()
            today = date.today()
            age = today.year - dob.year - (
                (today.month, today.day) < (dob.month, dob.day)
            )

        # Parse race and ethnicity from US Core extensions
        race = self._extract_us_core_extension(
            patient, "ombCategory",
            "http://hl7.org/fhir/us/core/StructureDefinition/us-core-race"
        )
        ethnicity = self._extract_us_core_extension(
            patient, "ombCategory",
            "http://hl7.org/fhir/us/core/StructureDefinition/us-core-ethnicity"
        )

        # Parse identifiers
        identifiers = {}
        for ident in patient.get("identifier", []):
            system = ident.get("system", "")
            if "MRN" in system.upper() or "medical-record" in system:
                identifiers["MRN"] = ident.get("value", "")
            elif "SSN" in system.upper():
                # Store only last 4 for display
                ssn = ident.get("value", "")
                identifiers["SSN_last4"] = ssn[-4:] if len(ssn) >= 4 else ssn

        return PatientDemographics(
            id=patient.get("id", ""),
            name=name,
            date_of_birth=dob,
            age=age,
            gender=patient.get("gender", "unknown"),
            race=race,
            ethnicity=ethnicity,
            marital_status=patient.get("maritalStatus", {}).get("text"),
            language=self._extract_language(patient),
            identifiers=identifiers
        )

    def _format_name(self, name: Dict) -> str:
        """Format FHIR HumanName."""
        given = " ".join(name.get("given", []))
        family = name.get("family", "")
        prefix = " ".join(name.get("prefix", []))
        parts = [p for p in [prefix, given, family] if p]
        return " ".join(parts)

    def _extract_us_core_extension(
        self, patient: Dict, sub_ext: str, ext_url: str
    ) -> Optional[str]:
        """Extract value from US Core race/ethnicity extension."""
        for ext in patient.get("extension", []):
            if ext.get("url") == ext_url:
                for sub in ext.get("extension", []):
                    if sub.get("url") == sub_ext:
                        return sub.get("valueCoding", {}).get("display")
        return None

    def _extract_language(self, patient: Dict) -> Optional[str]:
        """Extract preferred language."""
        comms = patient.get("communication", [])
        for comm in comms:
            if comm.get("preferred"):
                return comm.get("language", {}).get("text")
        return comms[0].get("language", {}).get("text") if comms else None
```

#### 6.3.6 Medication, Allergy, and History Fetchers

```python
# epic_fhir/fetchers/medication_fetcher.py
from typing import List, Dict, Optional
from dataclasses import dataclass
from ..client import AsyncFHIRClient

@dataclass
class Medication:
    """Parsed medication from FHIR MedicationStatement."""
    name: str
    dosage: Optional[str]
    route: Optional[str]
    frequency: Optional[str]
    status: str
    start_date: Optional[str]

class MedicationFetcher:
    """Fetch active medications from EPIC FHIR."""

    def __init__(self, fhir_client: AsyncFHIRClient):
        self.client = fhir_client

    async def fetch_medications(self, patient_id: str) -> List[Medication]:
        """Fetch active medication list."""
        resources = await self.client.search(
            "MedicationStatement",
            params={"status": "active"},
            patient_id=patient_id
        )

        medications = []
        for res in resources:
            med = self._parse_medication(res)
            if med:
                medications.append(med)

        medications.sort(key=lambda m: m.name)
        return medications

    def _parse_medication(self, res: Dict) -> Optional[Medication]:
        """Parse FHIR MedicationStatement."""
        # Extract medication name
        med_ref = res.get("medicationCodeableConcept", {})
        name = med_ref.get("text", "")
        if not name:
            for coding in med_ref.get("coding", []):
                name = coding.get("display", "")
                if name:
                    break
        if not name:
            return None

        # Extract dosage
        dosages = res.get("dosage", [])
        dosage_str = None
        route = None
        frequency = None
        if dosages:
            d = dosages[0]
            dose_qty = d.get("doseAndRate", [{}])[0].get("doseQuantity", {})
            if dose_qty:
                dosage_str = f"{dose_qty.get('value', '')} {dose_qty.get('unit', '')}"
            route = d.get("route", {}).get("text")
            timing = d.get("timing", {}).get("code", {}).get("text")
            frequency = timing

        return Medication(
            name=name,
            dosage=dosage_str,
            route=route,
            frequency=frequency,
            status=res.get("status", "active"),
            start_date=res.get("effectivePeriod", {}).get("start")
        )


# epic_fhir/fetchers/allergy_fetcher.py
@dataclass
class AllergyEntry:
    """Parsed allergy from FHIR AllergyIntolerance."""
    substance: str
    reaction: Optional[str]
    severity: Optional[str]
    category: str               # "medication", "food", "environment"
    status: str

class AllergyFetcher:
    """Fetch allergies from EPIC FHIR."""

    def __init__(self, fhir_client: AsyncFHIRClient):
        self.client = fhir_client

    async def fetch_allergies(self, patient_id: str) -> List[AllergyEntry]:
        """Fetch all allergy entries. Returns empty list for NKA."""
        resources = await self.client.search(
            "AllergyIntolerance",
            params={},
            patient_id=patient_id
        )

        allergies = []
        for res in resources:
            allergy = self._parse_allergy(res)
            if allergy:
                allergies.append(allergy)

        return allergies

    def _parse_allergy(self, res: Dict) -> Optional[AllergyEntry]:
        """Parse FHIR AllergyIntolerance."""
        # Check for NKA
        code = res.get("code", {})
        for coding in code.get("coding", []):
            if coding.get("code") in ("716186003", "no-known-allergy"):
                return None  # NKA - handled at caller level

        substance = code.get("text", "")
        if not substance:
            for coding in code.get("coding", []):
                substance = coding.get("display", "")
                if substance:
                    break

        if not substance:
            return None

        # Extract reaction
        reactions = res.get("reaction", [])
        reaction_text = None
        severity = None
        if reactions:
            manifestations = reactions[0].get("manifestation", [])
            if manifestations:
                reaction_text = manifestations[0].get("coding", [{}])[0].get("display")
            severity = reactions[0].get("severity")

        # Extract category
        categories = res.get("category", [])
        category = categories[0] if categories else "medication"

        return AllergyEntry(
            substance=substance,
            reaction=reaction_text,
            severity=severity,
            category=category,
            status=res.get("clinicalStatus", {}).get("coding", [{}])[0].get("code", "active")
        )

    def format_allergy_string(self, allergies: List[AllergyEntry]) -> str:
        """Format allergy list for note insertion."""
        if not allergies:
            return "No known drug allergies (NKDA)"
        return ", ".join(a.substance for a in allergies)


# epic_fhir/fetchers/history_fetcher.py
@dataclass
class ConditionEntry:
    """Parsed condition from FHIR Condition."""
    name: str
    icd10: Optional[str]
    status: str
    onset_date: Optional[str]

@dataclass
class ProcedureEntry:
    """Parsed procedure from FHIR Procedure."""
    name: str
    date: Optional[str]
    status: str

@dataclass
class FamilyHistoryEntry:
    """Parsed family history from FHIR FamilyMemberHistory."""
    relationship: str
    condition: str
    deceased: Optional[bool]
    age_of_onset: Optional[str]

class HistoryFetcher:
    """Fetch medical/surgical/family history from EPIC FHIR."""

    def __init__(self, fhir_client: AsyncFHIRClient):
        self.client = fhir_client

    async def fetch_conditions(self, patient_id: str) -> List[ConditionEntry]:
        """Fetch active conditions (problem list / PMH)."""
        resources = await self.client.search(
            "Condition",
            params={"clinical-status": "active"},
            patient_id=patient_id
        )
        return [self._parse_condition(r) for r in resources
                if self._parse_condition(r)]

    async def fetch_procedures(self, patient_id: str) -> List[ProcedureEntry]:
        """Fetch surgical history."""
        resources = await self.client.search(
            "Procedure",
            params={"_sort": "-date", "_count": "50"},
            patient_id=patient_id
        )
        return [self._parse_procedure(r) for r in resources
                if self._parse_procedure(r)]

    async def fetch_family_history(self, patient_id: str) -> List[FamilyHistoryEntry]:
        """Fetch family member history."""
        resources = await self.client.search(
            "FamilyMemberHistory",
            params={},
            patient_id=patient_id
        )
        entries = []
        for res in resources:
            parsed = self._parse_family_history(res)
            entries.extend(parsed)
        return entries

    def _parse_condition(self, res: Dict) -> Optional[ConditionEntry]:
        code = res.get("code", {})
        name = code.get("text", "")
        if not name:
            for coding in code.get("coding", []):
                name = coding.get("display", "")
                if name:
                    break
        if not name:
            return None

        icd10 = None
        for coding in code.get("coding", []):
            if "icd" in coding.get("system", "").lower():
                icd10 = coding.get("code")
                break

        return ConditionEntry(
            name=name,
            icd10=icd10,
            status=res.get("clinicalStatus", {}).get("coding", [{}])[0].get("code", "active"),
            onset_date=res.get("onsetDateTime", res.get("recordedDate"))
        )

    def _parse_procedure(self, res: Dict) -> Optional[ProcedureEntry]:
        code = res.get("code", {})
        name = code.get("text", "")
        if not name:
            for coding in code.get("coding", []):
                name = coding.get("display", "")
                if name:
                    break
        if not name:
            return None

        date = res.get("performedDateTime", res.get("performedPeriod", {}).get("start"))

        return ProcedureEntry(
            name=name,
            date=date,
            status=res.get("status", "completed")
        )

    def _parse_family_history(self, res: Dict) -> List[FamilyHistoryEntry]:
        relationship = res.get("relationship", {}).get("text", "Unknown")
        entries = []
        for condition in res.get("condition", []):
            code = condition.get("code", {})
            name = code.get("text", "")
            if not name:
                for coding in code.get("coding", []):
                    name = coding.get("display", "")
                    if name:
                        break
            if name:
                entries.append(FamilyHistoryEntry(
                    relationship=relationship,
                    condition=name,
                    deceased=res.get("deceasedBoolean"),
                    age_of_onset=condition.get("onsetAge", {}).get("value")
                ))
        return entries
```
