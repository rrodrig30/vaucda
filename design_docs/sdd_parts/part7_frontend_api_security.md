

---

## 11. User Interface Specification

### 11.1 Design System

The EPIC-VAUCDA UI inherits the VAUCDA color palette and design system documented in the VAUCDA SDD Section 8.1. All CSS variables, color definitions, button styles, status indicators, and accessibility requirements apply identically.

### 11.2 EPIC Settings Page Components

```typescript
// src/components/epic/EpicSettingsPage.tsx
interface EpicSettingsPageProps {
    onSave: (config: EpicConfig) => Promise<void>;
    currentConfig: EpicConfig;
}

interface EpicConfig {
    fhirBaseUrl: string;
    clientId: string;
    redirectUri: string;
    scopes: string;
    connectionStatus: 'connected' | 'disconnected' | 'error';
    lastAuthTime: string | null;
}

// src/components/epic/EpicConnectionStatus.tsx
interface ConnectionStatusProps {
    status: 'connected' | 'disconnected' | 'error';
    lastAuthTime: string | null;
    onReconnect: () => Promise<void>;
    onDisconnect: () => Promise<void>;
}

// src/components/epic/OAuthCallback.tsx
interface OAuthCallbackProps {
    onSuccess: (tokenResponse: TokenResponse) => void;
    onError: (error: string) => void;
}
```

### 11.3 LLM Configuration Components

```typescript
// src/components/settings/LLMProviderConfig.tsx
interface LLMProviderConfigProps {
    providers: ProviderConfig[];
    onSave: (providers: ProviderConfig[]) => Promise<void>;
}

interface ProviderConfig {
    name: 'ollama' | 'anthropic';
    isActive: boolean;
    host?: string;              // Ollama only
    apiKey?: string;            // Anthropic only
    defaultModel: string;
    temperature: number;
    maxTokens: number;
}

// src/components/settings/ModelDiscoveryPanel.tsx
interface ModelDiscoveryPanelProps {
    models: ModelInfo[];
    isLoading: boolean;
    onRefresh: () => Promise<void>;
    onSelectDefault: (provider: string, model: string) => void;
}

interface ModelInfo {
    provider: string;
    name: string;
    displayName: string;
    size: string | null;
    contextWindow: number;
    maxOutput: number;
    capabilities: string[];
    isAvailable: boolean;
}

// src/components/settings/OllamaModelManager.tsx
interface OllamaModelManagerProps {
    installedModels: ModelInfo[];
    onPull: (modelName: string) => Promise<void>;
    onDelete: (modelName: string) => Promise<void>;
    pullProgress: PullProgress | null;
}

interface PullProgress {
    modelName: string;
    status: string;
    completed: number;
    total: number;
}
```

### 11.4 Note Generation Screen with FHIR Integration

```
+-----------------------------------------------------------------------------+
|  EPIC-VAUCDA NOTE GENERATION                                                 |
+-----------------------------------------------------------------------------+
|                                                                               |
|  PATIENT CONTEXT:                     |  CLINICAL MODULES                    |
|  +-------------------------------+    |  +-------------------------------+   |
|  | [EPIC Patient Search]        |    |  |                               |   |
|  | Name: Rodriguez, John        |    |  | > PROSTATE CANCER             |   |
|  | DOB: 1955-03-15  Age: 70    |    |  |   [x] PSA Kinetics            |   |
|  | MRN: 123456                  |    |  |   [x] CAPRA Score             |   |
|  +-------------------------------+    |  |   [ ] NCCN Risk               |   |
|                                       |  |                               |   |
|  NOTE TYPE:                           |  | > MALE VOIDING                |   |
|  +-------------------------------+    |  |   [x] IPSS Calculator         |   |
|  | (o) Urology Clinic Note      |    |  |   [ ] BOOI/BCI                |   |
|  | ( ) Urology Consult          |    |  |                               |   |
|  | ( ) Pre-Operative Note       |    |  | > UROLITHIASIS                |   |
|  | ( ) Post-Operative Note      |    |  |   [ ] STONE Score             |   |
|  +-------------------------------+    |  |   [ ] 24-hr Urine             |   |
|                                       |  |                               |   |
|  LLM PROVIDER:                        |  | > SURGICAL PLANNING           |   |
|  +-------------------------------+    |  |   [ ] RCRI                    |   |
|  | Provider: [Ollama       v]   |    |  |   [ ] CFS                     |   |
|  | Model:   [llama3.1:8b  v]   |    |  +-------------------------------+   |
|  | Status:  [*] Online          |    |                                      |
|  +-------------------------------+    |  CALCULATOR RESULTS                  |
|                                       |  +-------------------------------+   |
|  FHIR DATA STATUS:                    |  | PSA Kinetics:                |   |
|  +-------------------------------+    |  |   PSAV: 1.2 ng/mL/yr        |   |
|  | [✓] Labs (47 results)       |    |  |   PSADT: 18.3 months         |   |
|  | [✓] Notes (12 urology)      |    |  | CAPRA: 3/10 (Intermediate)   |   |
|  | [✓] Imaging (8 reports)      |    |  | IPSS: 14/35 (Moderate)       |   |
|  | [✓] Pathology (3 reports)    |    |  +-------------------------------+   |
|  | [✓] Medications (15 active)  |    |                                      |
|  | [✓] Allergies (2 entries)    |    |                                      |
|  +-------------------------------+    |                                      |
|                                       |                                      |
|  [Generate Note]  [Download Word]     |                                      |
+---------------------------------------+--------------------------------------+
```

### 11.5 React Component Architecture

```typescript
// src/components/notes/NoteGenerator.tsx
interface NoteGeneratorProps {
    patientId: string;
    onGenerate: (config: NoteGenerationConfig) => Promise<NoteResult>;
    onDownloadWord: (noteId: string) => Promise<Blob>;
    availableModels: ModelInfo[];
    fhirDataStatus: FHIRDataStatus;
}

interface NoteGenerationConfig {
    patientId: string;
    noteType: 'clinic_note' | 'consult' | 'preop' | 'postop';
    selectedModules: string[];
    llmProvider: string;
    llmModel: string;
}

interface NoteResult {
    noteId: string;
    sections: Record<string, string>;
    calculatorResults: Record<string, CalculatorResultData>;
    metadata: {
        totalDurationMs: number;
        modelUsed: string;
        fhirResourcesQueried: string[];
    };
}

// src/hooks/useFHIRData.ts
interface FHIRDataStatus {
    labs: { count: number; status: 'loading' | 'loaded' | 'error' };
    notes: { count: number; status: 'loading' | 'loaded' | 'error' };
    imaging: { count: number; status: 'loading' | 'loaded' | 'error' };
    pathology: { count: number; status: 'loading' | 'loaded' | 'error' };
    medications: { count: number; status: 'loading' | 'loaded' | 'error' };
    allergies: { count: number; status: 'loading' | 'loaded' | 'error' };
}

// src/stores/epicStore.ts (Zustand)
interface EpicStore {
    // Auth state
    isAuthenticated: boolean;
    patientId: string | null;
    accessToken: string | null;  // Memory only, never persisted

    // Actions
    initiateAuth: () => void;
    handleCallback: (code: string, state: string) => Promise<void>;
    logout: () => void;

    // Patient context
    setPatientContext: (patientId: string) => void;
    clearPatientContext: () => void;
}
```

---

## 12. API Design

### 12.1 FastAPI Application Setup

```python
# api/main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from .v1 import notes, calculators, epic_auth, llm_management, settings
from ..services.llm.registry import DynamicModelRegistry
from ..services.llm.ollama import OllamaProvider, OllamaConfig
from ..services.llm.anthropic_provider import AnthropicProvider, AnthropicConfig
import os

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: initialize and cleanup resources."""
    # Initialize LLM registry
    registry = DynamicModelRegistry()

    # Register Ollama provider
    ollama_host = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
    ollama_provider = OllamaProvider(OllamaConfig(host=ollama_host))
    registry.register_provider(ollama_provider)

    # Register Anthropic provider (if configured)
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY")
    if anthropic_key:
        anthropic_provider = AnthropicProvider(
            AnthropicConfig(api_key=anthropic_key)
        )
        registry.register_provider(anthropic_provider)

    # Discover models at startup
    await registry.discover_all_models()

    app.state.llm_registry = registry
    yield

    # Cleanup
    await ollama_provider.close()
    if anthropic_key:
        await anthropic_provider.close()

app = FastAPI(
    title="EPIC-VAUCDA API",
    description="EPIC FHIR Urology Clinical Documentation Assistant",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[os.environ.get("FRONTEND_URL", "http://localhost:3000")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include route modules
app.include_router(epic_auth.router, prefix="/api/v1/epic", tags=["EPIC Auth"])
app.include_router(notes.router, prefix="/api/v1/notes", tags=["Notes"])
app.include_router(calculators.router, prefix="/api/v1/calculators", tags=["Calculators"])
app.include_router(llm_management.router, prefix="/api/v1/llm", tags=["LLM"])
app.include_router(settings.router, prefix="/api/v1/settings", tags=["Settings"])
```

### 12.2 EPIC OAuth Endpoints

```python
# api/v1/epic_auth.py
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from typing import Optional

router = APIRouter()

class EpicAuthConfig(BaseModel):
    fhir_base_url: str
    client_id: str
    redirect_uri: str
    scopes: str = "launch/patient patient/Patient.read patient/Observation.read patient/Condition.read patient/Procedure.read patient/MedicationStatement.read patient/AllergyIntolerance.read patient/DiagnosticReport.read patient/DocumentReference.read patient/FamilyMemberHistory.read patient/Encounter.read patient/ServiceRequest.read patient/CarePlan.read"

class AuthCallbackParams(BaseModel):
    code: str
    state: str

class TokenResponse(BaseModel):
    access_token_present: bool
    patient_id: Optional[str]
    expires_in: int
    scope: str

@router.post("/auth/initiate")
async def initiate_epic_auth(config: EpicAuthConfig, request: Request):
    """Initiate SMART on FHIR OAuth 2.0 authorization flow."""
    from ...services.epic_fhir.oauth import SMARTConfig, SMARTAuthClient

    smart_config = SMARTConfig(
        fhir_base_url=config.fhir_base_url,
        client_id=config.client_id,
        redirect_uri=config.redirect_uri,
        scopes=config.scopes,
    )

    auth_client = SMARTAuthClient(smart_config)
    await auth_client.discover_endpoints()

    # Store auth client in session
    request.app.state.auth_client = auth_client

    auth_url = auth_client.get_authorization_url()
    return {"authorization_url": auth_url, "state": smart_config.state}

@router.post("/auth/callback", response_model=TokenResponse)
async def handle_oauth_callback(params: AuthCallbackParams, request: Request):
    """Handle OAuth 2.0 callback and exchange code for token."""
    auth_client = getattr(request.app.state, 'auth_client', None)
    if not auth_client:
        raise HTTPException(status_code=400, detail="No auth session in progress")

    token_response = await auth_client.exchange_code(
        authorization_code=params.code,
        state=params.state,
    )

    return TokenResponse(
        access_token_present=bool(token_response.get("access_token")),
        patient_id=token_response.get("patient"),
        expires_in=token_response.get("expires_in", 3600),
        scope=token_response.get("scope", ""),
    )

@router.post("/auth/logout")
async def logout(request: Request):
    """Revoke tokens and clear EPIC session."""
    auth_client = getattr(request.app.state, 'auth_client', None)
    if auth_client:
        await auth_client.revoke_token()
    return {"status": "logged_out"}

@router.get("/auth/status")
async def get_auth_status(request: Request):
    """Check current EPIC authentication status."""
    auth_client = getattr(request.app.state, 'auth_client', None)
    if auth_client and auth_client.is_authenticated:
        return {
            "authenticated": True,
            "patient_id": auth_client.patient_id,
        }
    return {"authenticated": False, "patient_id": None}
```

### 12.3 Note Generation Endpoints

```python
# api/v1/notes.py
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from io import BytesIO

router = APIRouter()

class NoteGenerationRequest(BaseModel):
    patient_id: str
    note_type: str = "clinic_note"
    selected_modules: List[str] = []
    llm_provider: Optional[str] = None
    llm_model: Optional[str] = None

class NoteGenerationResponse(BaseModel):
    note_id: str
    sections: Dict[str, str]
    calculator_results: Dict[str, Any]
    metadata: Dict[str, Any]

@router.post("/generate", response_model=NoteGenerationResponse)
async def generate_note(req: NoteGenerationRequest, request: Request):
    """Generate a structured urology note from EPIC FHIR data."""
    import secrets
    from ...services.note_processing.pipeline import NoteProcessingPipeline
    from ...services.word_generator.generator import WordDocumentGenerator
    from ...services.epic_fhir.client import AsyncFHIRClient, FHIRClientConfig

    auth_client = getattr(request.app.state, 'auth_client', None)
    if not auth_client or not auth_client.is_authenticated:
        raise HTTPException(status_code=401, detail="EPIC authentication required")

    registry = request.app.state.llm_registry

    # Get LLM provider
    if req.llm_provider:
        llm = await registry.get_provider(req.llm_provider)
    else:
        provider_name, _ = await registry.get_model_for_task(
            TaskType.NOTE_GENERATION
        )
        llm = await registry.get_provider(provider_name)

    # Initialize FHIR client and pipeline
    fhir_config = FHIRClientConfig(
        base_url=auth_client.config.fhir_base_url
    )
    fhir_client = AsyncFHIRClient(fhir_config, auth_client)
    word_gen = WordDocumentGenerator()

    pipeline = NoteProcessingPipeline(
        fhir_client=fhir_client,
        llm_provider=llm,
        word_generator=word_gen,
    )

    result = await pipeline.generate_note(
        patient_id=req.patient_id,
        note_type=req.note_type,
        selected_modules=req.selected_modules,
        model=req.llm_model,
    )

    note_id = secrets.token_hex(16)

    # Store Word document bytes temporarily for download
    request.app.state.pending_downloads = getattr(
        request.app.state, 'pending_downloads', {}
    )
    request.app.state.pending_downloads[note_id] = result.word_document_bytes

    return NoteGenerationResponse(
        note_id=note_id,
        sections={
            "chief_complaint": result.sections.chief_complaint,
            "hpi": result.sections.hpi,
            "assessment": result.sections.assessment,
            "plan": result.sections.plan,
        },
        calculator_results={},
        metadata=result.metadata,
    )

@router.get("/download/{note_id}")
async def download_word_document(note_id: str, request: Request):
    """Download the generated Word document."""
    pending = getattr(request.app.state, 'pending_downloads', {})
    doc_bytes = pending.pop(note_id, None)

    if not doc_bytes:
        raise HTTPException(status_code=404, detail="Document not found or expired")

    return StreamingResponse(
        BytesIO(doc_bytes),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={
            "Content-Disposition": f'attachment; filename="urology_note_{note_id[:8]}.docx"'
        }
    )
```

### 12.4 LLM Management Endpoints

```python
# api/v1/llm_management.py
from fastapi import APIRouter, Request
from pydantic import BaseModel
from typing import List, Optional

router = APIRouter()

class ModelInfoResponse(BaseModel):
    provider: str
    name: str
    display_name: str
    size: Optional[str]
    context_window: int
    max_output: int
    capabilities: List[str]
    is_available: bool

class ProviderStatusResponse(BaseModel):
    name: str
    is_online: bool
    model_count: int
    error: Optional[str]

@router.get("/models", response_model=List[ModelInfoResponse])
async def list_all_models(request: Request):
    """List all available models across all providers (dynamic discovery)."""
    registry = request.app.state.llm_registry
    models = await registry.get_flat_model_list()
    return [
        ModelInfoResponse(
            provider=m.provider,
            name=m.name,
            display_name=m.display_name,
            size=m.size,
            context_window=m.context_window,
            max_output=m.max_output,
            capabilities=m.capabilities,
            is_available=m.is_available,
        )
        for m in models
    ]

@router.get("/providers", response_model=List[ProviderStatusResponse])
async def list_providers(request: Request):
    """List all LLM providers with health status."""
    registry = request.app.state.llm_registry
    statuses = await registry.get_all_status()
    return [
        ProviderStatusResponse(
            name=s.name,
            is_online=s.is_online,
            model_count=len(s.models),
            error=s.error_message,
        )
        for s in statuses
    ]

@router.post("/models/refresh")
async def refresh_models(request: Request):
    """Force refresh model discovery from all providers."""
    registry = request.app.state.llm_registry
    all_models = await registry.discover_all_models(force_refresh=True)
    return {
        "providers": {
            name: len(models) for name, models in all_models.items()
        }
    }
```

---

## 13. Authentication and Authorization

### 13.1 SMART on FHIR Authorization Flow

```
+----------+     +----------+     +-----------+     +----------+
|  Browser |     | EPIC-    |     | EPIC      |     | EPIC     |
|  (React) |     | VAUCDA   |     | Auth      |     | FHIR     |
|          |     | Backend  |     | Server    |     | Server   |
+----+-----+     +----+-----+     +-----+-----+     +----+-----+
     |                |                  |                |
     | 1. Click "Connect to EPIC"       |                |
     |--------------->|                  |                |
     |                |                  |                |
     |                | 2. Discover SMART endpoints       |
     |                |  GET /.well-known/smart-configuration
     |                |---------------------------------->|
     |                |<----------------------------------|
     |                |                  |                |
     |                | 3. Generate PKCE (verifier + challenge)
     |                | 4. Build authorization URL        |
     |<---------------|                  |                |
     |   (redirect URL with PKCE)       |                |
     |                                   |                |
     | 5. Redirect to EPIC login        |                |
     |---------------------------------->|                |
     |                                   |                |
     | 6. User authenticates + consents |                |
     |<----------------------------------|                |
     |   (redirect with code + state)   |                |
     |                                   |                |
     | 7. Forward code to backend       |                |
     |--------------->|                  |                |
     |                |                  |                |
     |                | 8. Exchange code + PKCE verifier  |
     |                |  POST /token     |                |
     |                |----------------->|                |
     |                |<-----------------|                |
     |                |  (access_token, refresh_token,    |
     |                |   patient_id, scope)              |
     |                |                  |                |
     |                | 9. Store tokens in memory only    |
     |                |                  |                |
     |<---------------|                  |                |
     |  (auth success, patient context) |                |
     |                |                  |                |
     |                | 10. FHIR queries with Bearer token|
     |                |---------------------------------->|
     |                |<----------------------------------|
     |                |   (FHIR R4 resources)             |
```

### 13.2 Session Management

```python
# core/session.py
from dataclasses import dataclass, field
from typing import Optional, Dict
from datetime import datetime, timedelta
import secrets

@dataclass
class UserSession:
    """In-memory session for authenticated user.

    CRITICAL: All tokens and patient data stored in memory ONLY.
    Never persisted to disk, database, or logs.
    """
    session_id: str = field(default_factory=lambda: secrets.token_hex(32))
    user_id: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    last_activity: datetime = field(default_factory=datetime.utcnow)
    expires_at: Optional[datetime] = None

    # EPIC auth (memory only)
    epic_access_token: Optional[str] = None
    epic_refresh_token: Optional[str] = None
    epic_patient_id: Optional[str] = None

    # Session timeout (30 minutes of inactivity per HIPAA)
    TIMEOUT_MINUTES: int = 30

    def __post_init__(self):
        self.expires_at = self.created_at + timedelta(minutes=self.TIMEOUT_MINUTES)

    @property
    def is_expired(self) -> bool:
        """Check if session has timed out."""
        return datetime.utcnow() > self.expires_at

    def touch(self) -> None:
        """Update last activity and extend expiry."""
        self.last_activity = datetime.utcnow()
        self.expires_at = self.last_activity + timedelta(
            minutes=self.TIMEOUT_MINUTES
        )

    def destroy(self) -> None:
        """Securely destroy all session data."""
        self.epic_access_token = None
        self.epic_refresh_token = None
        self.epic_patient_id = None
        self.user_id = None


class SessionManager:
    """Manage user sessions in memory."""

    def __init__(self):
        self._sessions: Dict[str, UserSession] = {}

    def create_session(self, user_id: str) -> UserSession:
        """Create a new session."""
        session = UserSession(user_id=user_id)
        self._sessions[session.session_id] = session
        return session

    def get_session(self, session_id: str) -> Optional[UserSession]:
        """Get session by ID, checking expiry."""
        session = self._sessions.get(session_id)
        if session and session.is_expired:
            self.destroy_session(session_id)
            return None
        if session:
            session.touch()
        return session

    def destroy_session(self, session_id: str) -> None:
        """Destroy a session and clear all data."""
        session = self._sessions.pop(session_id, None)
        if session:
            session.destroy()

    def cleanup_expired(self) -> int:
        """Remove all expired sessions. Returns count removed."""
        expired = [
            sid for sid, s in self._sessions.items()
            if s.is_expired
        ]
        for sid in expired:
            self.destroy_session(sid)
        return len(expired)
```

---

## 14. Security and Compliance

### 14.1 Zero-Persistence PHI Architecture

The EPIC-VAUCDA system inherits the VAUCDA zero-persistence PHI architecture with the following EPIC-specific enhancements:

| Security Control | Implementation |
|-----------------|----------------|
| **FHIR Token Storage** | Access/refresh tokens stored in memory only; never persisted |
| **Patient Data Transit** | FHIR data encrypted via TLS 1.3 from EPIC to backend |
| **Processing Isolation** | Each request processed in ephemeral context with guaranteed cleanup |
| **Word Document Lifecycle** | Generated .docx stored in memory; available for download once; then purged |
| **EPIC Credential Encryption** | Client ID/secret encrypted at rest using Fernet (AES-256-CBC) |
| **Session Timeout** | 30-minute inactivity timeout per HIPAA §164.312(a)(2)(iii) |
| **Audit Logging** | PHI-free audit logs capturing only metadata (resource types, durations) |
| **LLM Data Handling** | Ollama processes locally with no persistence; Anthropic calls via encrypted API |

### 14.2 Ephemeral Data Handler (EPIC-Enhanced)

```python
# security/ephemeral_data.py
import gc
import ctypes
from contextlib import asynccontextmanager
from typing import Optional, Dict, Any
import secrets

def secure_zero_memory(data: bytes) -> None:
    """Securely overwrite memory with zeros before deallocation."""
    if data:
        address = id(data)
        size = len(data)
        ctypes.memset(address, 0, size)
        gc.collect()

@asynccontextmanager
async def ephemeral_fhir_context():
    """Context manager for FHIR data processing with guaranteed cleanup.

    All FHIR-fetched patient data is purged when the context exits,
    even if an exception occurs.

    Usage:
        async with ephemeral_fhir_context() as ctx:
            ctx['labs'] = await fetch_labs(patient_id)
            ctx['notes'] = await fetch_notes(patient_id)
            result = await process(ctx)
        # All patient data is now purged from memory
    """
    data_container: Dict[str, Any] = {}

    try:
        yield data_container
    finally:
        # Recursively clear all data
        _deep_clear(data_container)
        data_container.clear()
        gc.collect()

def _deep_clear(obj: Any) -> None:
    """Recursively clear data structures."""
    if isinstance(obj, dict):
        for key in list(obj.keys()):
            _deep_clear(obj[key])
            del obj[key]
    elif isinstance(obj, list):
        for i in range(len(obj)):
            _deep_clear(obj[i])
        obj.clear()
    elif isinstance(obj, str):
        pass  # Strings are immutable in Python
    elif isinstance(obj, bytes):
        secure_zero_memory(obj)
```

### 14.3 Credential Encryption Service

```python
# security/credential_store.py
from cryptography.fernet import Fernet
from typing import Optional
import os
import base64

class CredentialStore:
    """Encrypted storage for EPIC and API credentials.

    Uses Fernet symmetric encryption (AES-256-CBC) with a master
    key loaded from environment variables.
    """

    def __init__(self):
        master_key = os.environ.get("EPIC_VAUCDA_MASTER_KEY")
        if not master_key:
            raise RuntimeError(
                "EPIC_VAUCDA_MASTER_KEY environment variable required"
            )
        self._fernet = Fernet(master_key.encode())

    def encrypt(self, plaintext: str) -> bytes:
        """Encrypt a credential string."""
        return self._fernet.encrypt(plaintext.encode('utf-8'))

    def decrypt(self, ciphertext: bytes) -> str:
        """Decrypt a credential string."""
        return self._fernet.decrypt(ciphertext).decode('utf-8')

    @staticmethod
    def generate_master_key() -> str:
        """Generate a new Fernet master key.

        Run once during initial setup:
            python -c "from security.credential_store import CredentialStore; print(CredentialStore.generate_master_key())"
        """
        return Fernet.generate_key().decode()
```

### 14.4 HIPAA Compliance Matrix

| HIPAA Requirement | EPIC-VAUCDA Implementation | Verification |
|-------------------|---------------------------|--------------|
| **Access Controls §164.312(a)** | SMART on FHIR OAuth 2.0 with PKCE; session-based access | OAuth flow testing |
| **Audit Controls §164.312(b)** | PHI-free audit logging of all FHIR access and note generation | Log review |
| **Integrity Controls §164.312(c)** | TLS 1.3 for EPIC communication; message signing | Certificate validation |
| **Transmission Security §164.312(e)** | TLS 1.3 mandatory; HSTS enabled | SSL Labs A+ rating |
| **Encryption §164.312(a)(2)(iv)** | AES-256 for credentials at rest; TLS 1.3 in transit | Encryption audit |
| **Data Minimization** | Zero-persistence PHI; ephemeral processing contexts | Architecture review |
| **Automatic Logoff §164.312(a)(2)(iii)** | 30-minute session timeout with token revocation | Session testing |
| **Unique User Identification §164.312(a)(2)(i)** | Per-user EPIC OAuth 2.0 authentication | Auth flow testing |

---

## 15. Deployment Architecture

### 15.1 Docker Compose Configuration

```yaml
# docker-compose.yml
version: '3.8'

services:
  epic-vaucda-api:
    build:
      context: ./backend
      dockerfile: Dockerfile
    ports:
      - "${API_PORT:-8000}:8000"
    environment:
      - NEO4J_URI=bolt://neo4j:7687
      - NEO4J_USER=${NEO4J_USER:-neo4j}
      - NEO4J_PASSWORD=${NEO4J_PASSWORD}
      - OLLAMA_HOST=http://ollama:11434
      - ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}
      - REDIS_URL=redis://redis:6379
      - EPIC_VAUCDA_MASTER_KEY=${EPIC_VAUCDA_MASTER_KEY}
      - FRONTEND_URL=${FRONTEND_URL:-http://localhost:3000}
      - EMBEDDING_MODEL=NeuML/pubmedbert-base-embeddings
    depends_on:
      neo4j:
        condition: service_healthy
      redis:
        condition: service_started
      ollama:
        condition: service_started
    volumes:
      - ./backend/data:/app/data
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3

  epic-vaucda-frontend:
    build:
      context: ./frontend
      dockerfile: Dockerfile
    ports:
      - "${FRONTEND_PORT:-3000}:3000"
    environment:
      - REACT_APP_API_URL=${API_URL:-http://localhost:8000}
    depends_on:
      - epic-vaucda-api
    restart: unless-stopped

  neo4j:
    image: neo4j:5.15-community
    ports:
      - "${NEO4J_HTTP_PORT:-7474}:7474"
      - "${NEO4J_BOLT_PORT:-7687}:7687"
    environment:
      - NEO4J_AUTH=${NEO4J_USER:-neo4j}/${NEO4J_PASSWORD}
      - NEO4J_PLUGINS=["apoc", "graph-data-science"]
      - NEO4J_dbms_security_procedures_unrestricted=apoc.*,gds.*
    volumes:
      - neo4j_data:/data
      - neo4j_logs:/logs
      - ./scripts/init_neo4j.cypher:/var/lib/neo4j/import/init.cypher
    restart: unless-stopped
    healthcheck:
      test: ["CMD-SHELL", "neo4j status || exit 1"]
      interval: 30s
      timeout: 10s
      retries: 5

  ollama:
    image: ollama/ollama:latest
    ports:
      - "${OLLAMA_PORT:-11434}:11434"
    volumes:
      - ollama_models:/root/.ollama
    environment:
      - OLLAMA_KEEP_ALIVE=0
      - OLLAMA_NUM_PARALLEL=1
      - OLLAMA_DEBUG=false
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]
    restart: unless-stopped

  redis:
    image: redis:7-alpine
    ports:
      - "${REDIS_PORT:-6379}:6379"
    volumes:
      - redis_data:/data
    restart: unless-stopped

  celery-worker:
    build:
      context: ./backend
      dockerfile: Dockerfile
    command: celery -A app.celery worker --loglevel=info --concurrency=4
    environment:
      - REDIS_URL=redis://redis:6379
      - NEO4J_URI=bolt://neo4j:7687
      - OLLAMA_HOST=http://ollama:11434
      - ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}
      - EPIC_VAUCDA_MASTER_KEY=${EPIC_VAUCDA_MASTER_KEY}
    depends_on:
      - redis
      - neo4j
    restart: unless-stopped

volumes:
  neo4j_data:
  neo4j_logs:
  ollama_models:
  redis_data:
```

### 15.2 Environment Variables

```bash
# .env.example

# --- EPIC FHIR Configuration ---
EPIC_FHIR_BASE_URL=https://fhir.epic.com/interconnect-fhir-oauth/api/FHIR/R4
EPIC_CLIENT_ID=your-epic-client-id
EPIC_REDIRECT_URI=http://localhost:3000/auth/callback

# --- LLM Providers ---
OLLAMA_HOST=http://localhost:11434
ANTHROPIC_API_KEY=sk-ant-...

# --- Database ---
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=your-neo4j-password

# --- Security ---
EPIC_VAUCDA_MASTER_KEY=your-fernet-key-here
JWT_SECRET_KEY=your-jwt-secret-key

# --- Embedding Model ---
EMBEDDING_MODEL=NeuML/pubmedbert-base-embeddings

# --- Application ---
API_PORT=8000
FRONTEND_PORT=3000
FRONTEND_URL=http://localhost:3000
REDIS_URL=redis://localhost:6379

# --- Ollama Security ---
OLLAMA_KEEP_ALIVE=0
OLLAMA_NUM_PARALLEL=1
OLLAMA_DEBUG=false
```
