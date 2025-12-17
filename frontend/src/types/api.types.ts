// API Response Types
export interface ApiResponse<T> {
  data: T
  message?: string
  success: boolean
}

export interface PaginatedResponse<T> {
  items: T[]
  total: number
  page: number
  page_size: number
  total_pages: number
  has_next: boolean
  has_prev: boolean
}

export interface ApiError {
  detail: string
  error_code?: string
  errors?: Array<{
    loc: string[]
    msg: string
    type: string
  }>
}

// Authentication Types
export interface LoginRequest {
  username: string
  password: string
}

export interface LoginResponse {
  access_token: string
  token_type: string
  expires_in: number
}

export interface RegisterRequest {
  email: string
  password: string
  first_name: string
  last_name: string
  initials: string
  position: 'Physician-Faculty' | 'Physician-Fellow' | 'Physician-Resident' | 'APP-PA' | 'APP-NP' | 'Staff'
  specialty: 'Urology' | 'ENT' | 'Hospital Medicine'
  openevidence_username?: string
  openevidence_password?: string
}

export interface RegisterResponse {
  user_id: string
  email: string
  first_name: string
  last_name: string
  full_name: string
  initials: string
  position: string
  specialty: string
  role: 'user' | 'admin'
  is_active: boolean
  created_at: string
  last_login?: string
}

export interface User {
  user_id: string
  email: string
  first_name?: string
  last_name?: string
  full_name?: string
  initials?: string
  position?: string
  specialty?: string
  role: 'user' | 'admin'
  is_active: boolean
  created_at: string
  last_login?: string
}

// Note Generation Types
export interface NoteGenerationRequest {
  clinical_input: string
  note_type: 'clinic_note' | 'consult' | 'preop' | 'postop'
  template_id?: string
  selected_modules?: string[]
  llm_config: LLMConfig
}

export interface LLMConfig {
  provider: 'ollama' | 'anthropic' | 'openai'
  model: string
  temperature?: number
  max_tokens?: number
}

export interface NoteSection {
  name: string
  content: string
}

export interface CalculatorResult {
  module_name: string
  category: string
  results: Record<string, any>
}

export interface NoteGenerationResponse {
  note_id: string
  generated_note: string
  sections: NoteSection[]
  appendices: CalculatorResult[]
  metadata: {
    model_used: string
    provider: string
    tokens_used: number
    generation_time_ms: number
    modules_executed: number
    created_at: string
  }
}

export interface SavedNote {
  note_id: string
  generated_note: string
  created_at: string
  expires_at: string
}

// Calculator Types
export interface CalculatorCategory {
  [category: string]: Calculator[]
}

export interface Calculator {
  id: string
  name: string
  description: string
  category: string
  inputs: CalculatorInput[]
  references: string[]
  version?: string
  interpretation_guide?: Record<string, string>
}

export interface CalculatorInput {
  name: string
  type: 'int' | 'float' | 'choice' | 'list' | 'boolean'
  description: string
  required: boolean
  min_value?: number
  max_value?: number
  unit?: string
  choices?: string[] | number[]
  default?: any
}

export interface CalculatorExecutionRequest {
  inputs: Record<string, any>
}

export interface CalculatorExecutionResponse {
  calculator_id: string
  score?: number
  interpretation: string
  risk_level?: string
  recommendations?: string[]
  breakdown?: Record<string, any>
  references: string[]
  computation_time_ms: number
}

export interface BatchCalculatorRequest {
  calculators: Array<{
    calculator_id: string
    inputs: Record<string, any>
  }>
}

export interface BatchCalculatorResponse {
  results: Array<{
    calculator_id: string
    status: 'success' | 'error'
    result?: CalculatorExecutionResponse
    error?: string
  }>
  total_calculators: number
  successful: number
  failed: number
}

// Template Types
export interface Template {
  id: string
  name: string
  type: 'clinic_note' | 'consult' | 'preop' | 'postop'
  active: boolean
  sections: string[]
  content?: string
  created_at: string
  created_by?: string
  version: string
}

export interface CreateTemplateRequest {
  name: string
  type: 'clinic_note' | 'consult' | 'preop' | 'postop'
  content: string
  sections: string[]
  active: boolean
}

export interface UpdateTemplateRequest {
  content?: string
  active?: boolean
}

// Settings Types
export interface UserSettings {
  user_id: string
  default_llm: 'ollama' | 'anthropic' | 'openai'
  default_model: string
  default_template: string
  module_defaults: ModuleDefaults
  display_preferences: DisplayPreferences
}

export interface ModuleDefaults {
  prostate_cancer?: {
    default_calculator?: string
    auto_calculate_psa_kinetics?: boolean
    include_nccn_risk?: boolean
  }
  kidney_cancer?: {
    default_nephrometry?: string
    survival_model?: string
  }
  [key: string]: any
}

export interface DisplayPreferences {
  show_confidence_intervals: boolean
  include_guideline_citations: boolean
  display_calculation_breakdown: boolean
  highlight_abnormal_values: boolean
  generate_visual_diagrams: boolean
}

export interface UpdateSettingsRequest {
  default_llm?: 'ollama' | 'anthropic' | 'openai'
  default_model?: string
  default_template?: string
  llm_temperature?: number
  llm_max_tokens?: number
  llm_top_p?: number
  llm_frequency_penalty?: number
  llm_presence_penalty?: number
  module_defaults?: Partial<ModuleDefaults>
  display_preferences?: Partial<DisplayPreferences>
}

// LLM Provider Types
export interface LLMProvider {
  name: string
  status: 'online' | 'offline' | 'configured'
  host?: string
  api_key_set?: boolean
  models: LLMModel[]
}

export interface LLMModel {
  name: string
  size?: number
  size_human?: string
  modified_at?: string
  digest?: string
  format?: string
}

export interface PullModelRequest {
  model: string
}

export interface PullModelResponse {
  task_id: string
  status: 'pulling' | 'completed' | 'failed'
  model: string
  message: string
}

export interface PullModelStatus {
  task_id: string
  status: 'pulling' | 'completed' | 'failed'
  progress: number
  model: string
  size_pulled?: number
  size_total?: number
  completed_at?: string
  error?: string
}

// RAG/Evidence Search Types
export interface EvidenceSearchRequest {
  query: string
  category?: string
  k?: number
  include_references?: boolean
}

export interface EvidenceSearchResult {
  document_id: string
  title: string
  source: string
  content: string
  relevance_score: number
  metadata: {
    document_type: 'guideline' | 'reference' | 'calculator'
    category: string
    publication_date?: string
  }
}

export interface EvidenceSearchResponse {
  query: string
  results: EvidenceSearchResult[]
  total_results: number
  search_time_ms: number
}

export interface DocumentIngestionRequest {
  file: File
  title: string
  source: string
  document_type: 'guideline' | 'reference' | 'calculator'
  category: string
}

export interface DocumentIngestionResponse {
  task_id: string
  status: 'processing' | 'completed' | 'failed'
  message: string
}

// Health Check Types
export interface HealthCheck {
  status: 'healthy' | 'unhealthy' | 'degraded'
  version?: string
  timestamp: string
  uptime_seconds?: number
}

export interface DetailedHealthCheck extends HealthCheck {
  services: {
    api: ServiceHealth
    neo4j: ServiceHealth
    ollama: ServiceHealth
    redis: ServiceHealth
    sqlite: ServiceHealth
  }
}

export interface ServiceHealth {
  status: 'healthy' | 'unhealthy' | 'degraded'
  connection?: 'active' | 'inactive'
  response_time_ms?: number
  models_available?: number
  path?: string
}

// WebSocket Message Types
export interface WSMessage<T = any> {
  type: string
  payload: T
}

export interface WSGenerationStart {
  type: 'start_generation'
  payload: NoteGenerationRequest
}

export interface WSGenerationProgress {
  type: 'generation_progress'
  payload: {
    chunk: string
    progress: number
  }
}

export interface WSModuleProgress {
  type: 'module_progress'
  payload: {
    module: string
    status: 'executing' | 'completed' | 'failed'
  }
}

export interface WSGenerationComplete {
  type: 'generation_complete'
  payload: {
    note_id: string
    total_tokens: number
    generation_time_ms: number
    modules_executed: number
  }
}

export interface WSError {
  type: 'error'
  payload: {
    error_code: string
    message: string
  }
}

// Dashboard/Stats Types
export interface UsageStats {
  total_notes_generated: number
  total_calculators_used: number
  total_searches: number
  recent_notes: SavedNote[]
  popular_calculators: Array<{
    calculator_id: string
    name: string
    usage_count: number
  }>
  recent_searches: Array<{
    query: string
    timestamp: string
  }>
}

// ============================================================================
// TWO-STAGE WORKFLOW TYPES (Improved Clinical Workflow)
// ============================================================================

// Extracted Clinical Entity
export interface ExtractedEntity {
  field: string
  value: any
  confidence: number
  source_text: string
  extraction_method?: 'regex' | 'llm'
}

// Calculator Suggestion
export interface CalculatorSuggestion {
  calculator_id: string
  calculator_name: string
  category: string
  confidence: 'high' | 'medium' | 'low'
  auto_selected: boolean
  reason: string
  required_inputs: string[]
  available_inputs: string[]
  missing_inputs: string[]
  detected_entities: Record<string, any>
  description?: string
}

// Stage 1: Initial Note Request
export interface InitialNoteRequest {
  clinical_input: string
  note_type?: 'clinic_note' | 'consult' | 'preop' | 'postop' | 'procedure_note'
  patient_name?: string
  ssn_last4?: string
  llm_provider?: 'ollama' | 'anthropic' | 'openai'
  llm_model?: string
  temperature?: number
  use_rag?: boolean
}

// Stage 1: Initial Note Response
export interface InitialNoteResponse {
  preliminary_note: string
  extracted_entities: ExtractedEntity[]
  suggested_calculators: CalculatorSuggestion[]
  metadata: {
    generation_time_seconds: number
    entities_extracted: number
    calculators_suggested: number
    note_type: string
    llm_provider: string
  }
}

// Stage 2: Final Note Request
export interface FinalNoteRequest {
  preliminary_note: string
  clinical_input: string
  selected_calculators: string[]
  additional_inputs: Record<string, any>
  use_rag: boolean
  llm_provider: 'ollama' | 'anthropic' | 'openai'
  llm_model?: string
  temperature?: number
  note_type?: string
  patient_name?: string
  ssn_last4?: string
}

// Calculator Result Schema (for final note)
export interface CalculatorResultSchema {
  calculator_id: string
  calculator_name: string
  result: any
  interpretation: string
  recommendations: string[]
  formatted_output: string
}

// Stage 2: Final Note Response
export interface FinalNoteResponse {
  final_note: string
  calculator_results: CalculatorResultSchema[]
  rag_sources: Array<{
    id?: string
    title: string
    source: string
    category?: string
    content?: string
  }>
  metadata: {
    generation_time_seconds: number
    calculators_executed: number
    rag_enabled: boolean
    rag_sources_count: number
  }
}

// ============================================================================
// AMBIENT LISTENING WEBSOCKET TYPES
// ============================================================================

// WebSocket Message for Audio Stream
export interface WSAudioMessage {
  type: 'audio'
  data: string  // base64-encoded audio chunk
  format?: 'wav' | 'webm'
  sample_rate?: number
}

// WebSocket Message for Transcription
export interface WSTranscriptionMessage {
  type: 'transcription'
  text: string
  timestamp: number
  confidence: number
}

// WebSocket Message for Entities
export interface WSEntitiesMessage {
  type: 'entities'
  entities: ExtractedEntity[]
}

// WebSocket Message for Stop Command
export interface WSStopMessage {
  type: 'stop'
}

// WebSocket Message for Stopped Confirmation
export interface WSStoppedMessage {
  type: 'stopped'
  message: string
}

// Union type for all ambient listening WebSocket messages
export type AmbientWSMessage =
  | WSAudioMessage
  | WSTranscriptionMessage
  | WSEntitiesMessage
  | WSStopMessage
  | WSStoppedMessage
  | WSError
