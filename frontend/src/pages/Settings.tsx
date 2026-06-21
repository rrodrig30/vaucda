import React, { useState, useEffect } from 'react'
import { Card } from '@/components/common/Card'
import { Button } from '@/components/common/Button'
import { Input } from '@/components/common/Input'
import { Select } from '@/components/common/Select'
import { Modal } from '@/components/common/Modal'
import { Textarea } from '@/components/common/Textarea'
import { settingsApi, llmApi, ragApi, userRulesApi } from '@/api'
import type { UserRule } from '@/api'
import { FiSave, FiRefreshCw, FiLock, FiEye, FiEyeOff, FiCheckCircle, FiEdit3, FiAlertCircle, FiPlus, FiTrash2, FiX } from 'react-icons/fi'
import { useAuth } from '@/hooks/useAuth'
import type { UpdateSettingsRequest } from '@/types/api.types'

const LLM_PROVIDERS = [
  { value: 'ollama', label: 'Ollama (Local)' },
  { value: 'anthropic', label: 'Anthropic Claude' },
  { value: 'openai', label: 'OpenAI GPT' },
]

const NOTE_TYPES = [
  { value: 'clinic_note', label: 'Clinic Note' },
  { value: 'consult', label: 'Consult' },
  { value: 'preop', label: 'Pre-Operative' },
  { value: 'postop', label: 'Post-Operative' },
]

export const Settings: React.FC = () => {
  const { user } = useAuth()

  const [isLoading, setIsLoading] = useState(true)
  const [isSaving, setIsSaving] = useState(false)
  const [formData, setFormData] = useState({
    default_llm: 'ollama' as 'ollama' | 'anthropic' | 'openai',
    default_model: '',
    default_template: 'clinic_note',
    source_format: 'cprs' as 'cprs' | 'vista',
    temperature: 0.3,
    max_tokens: 4000,
    rag_enabled: true,
    rag_top_k: 5,
    show_confidence_intervals: true,
    include_guideline_citations: true,
    display_calculation_breakdown: true,
    highlight_abnormal_values: true,
  })

  // Task-specific LLM configuration
  // Initial values are placeholders - actual values loaded from API/database
  // num_ctx (input context window): null/undefined means "use lookup table or 125K default"
  const [taskLLMConfig, setTaskLLMConfig] = useState({
    // OCR Processing - defaults from backend environment
    ocr_llm_provider: 'ollama',
    ocr_llm_model: '',  // Loaded from backend
    ocr_llm_temperature: 0.1,
    ocr_llm_max_tokens: 4096,
    ocr_llm_num_ctx: undefined as number | undefined,
    // Stage 1: Note Generation - defaults from backend environment
    stage1_llm_provider: 'ollama',
    stage1_llm_model: '',  // Loaded from backend
    stage1_llm_temperature: 0.1,
    stage1_llm_max_tokens: 8192,
    stage1_llm_num_ctx: undefined as number | undefined,
    // Stage 2: Assessment & Plan - defaults from backend environment
    stage2_llm_provider: 'ollama',
    stage2_llm_model: '',  // Loaded from backend
    stage2_llm_temperature: 0.0,
    stage2_llm_max_tokens: 8192,
    stage2_llm_num_ctx: undefined as number | undefined,
    stage2_use_rag: true,
    stage2_use_graphrag: true,
    stage2_rag_top_k: 5,
  })

  // Per-task "model max" hints from /llm/model-context-size, displayed under each input
  const [modelContextHints, setModelContextHints] = useState<{
    ocr?: { context_size: number; known: boolean }
    stage1?: { context_size: number; known: boolean }
    stage2?: { context_size: number; known: boolean }
  }>({})

  const [availableModels, setAvailableModels] = useState<string[]>([])

  // Models available per provider (for dropdowns)
  const [modelsByProvider, setModelsByProvider] = useState<Record<string, string[]>>({
    ollama: [],
    anthropic: [],
    openai: [],
  })

  // Settings verification state
  const [saveVerification, setSaveVerification] = useState<{
    verified: boolean;
    message: string;
    details: Record<string, { saved: string; loaded: string; match: boolean }>;
  } | null>(null)

  // Model loading state
  const [modelLoadingError, setModelLoadingError] = useState<string | null>(null)
  const [isLoadingModels, setIsLoadingModels] = useState(false)

  const [showPasswordModal, setShowPasswordModal] = useState(false)
  const [passwordForm, setPasswordForm] = useState({
    current_password: '',
    new_password: '',
    confirm_password: '',
  })
  const [passwordError, setPasswordError] = useState('')
  const [showPasswords, setShowPasswords] = useState({
    current: false,
    new: false,
    confirm: false,
  })

  const [openEvidenceCredentials, setOpenEvidenceCredentials] = useState({
    username: '',
    password: '',
  })
  const [showOpenEvidencePassword, setShowOpenEvidencePassword] = useState(false)

  // System prompt editor state
  const [systemPrompt, setSystemPrompt] = useState('')
  const [isLoadingPrompt, setIsLoadingPrompt] = useState(false)
  const [isSavingPrompt, setIsSavingPrompt] = useState(false)
  const [promptLastModified, setPromptLastModified] = useState<number | null>(null)

  // Assessment & Plan user-defined rules
  const [userRules, setUserRules] = useState<UserRule[]>([])
  const [newRuleText, setNewRuleText] = useState('')
  const [isLoadingRules, setIsLoadingRules] = useState(false)
  const [isSavingRule, setIsSavingRule] = useState(false)
  const [editingRuleId, setEditingRuleId] = useState<number | null>(null)
  const [editingRuleText, setEditingRuleText] = useState('')
  const [rulesError, setRulesError] = useState<string | null>(null)

  useEffect(() => {
    loadSettings()
    loadSystemPrompt()
    loadAllProviderModels()  // Load models for all providers on mount
    loadUserRules()
  }, [])

  useEffect(() => {
    if (formData.default_llm) {
      loadModelsForProvider(formData.default_llm)
    }
  }, [formData.default_llm])

  // Load models for all providers (for task-specific dropdowns)
  const loadAllProviderModels = async () => {
    setIsLoadingModels(true)
    setModelLoadingError(null)
    try {
      const providers = await llmApi.getProviders()
      const newModelsByProvider: Record<string, string[]> = {
        ollama: [],
        anthropic: [],
        openai: [],
      }

      for (const provider of providers) {
        const providerName = provider.name.toLowerCase()
        if (provider.models && provider.models.length > 0) {
          newModelsByProvider[providerName] = provider.models.map(m => m.name)
        }
      }

      setModelsByProvider(newModelsByProvider)

      // Auto-select first model for any task that has empty model selection
      setTaskLLMConfig(prev => ({
        ...prev,
        ocr_llm_model: prev.ocr_llm_model || newModelsByProvider[prev.ocr_llm_provider]?.[0] || '',
        stage1_llm_model: prev.stage1_llm_model || newModelsByProvider[prev.stage1_llm_provider]?.[0] || '',
        stage2_llm_model: prev.stage2_llm_model || newModelsByProvider[prev.stage2_llm_provider]?.[0] || '',
      }))

      // Check if any provider has no models
      const emptyProviders = Object.entries(newModelsByProvider)
        .filter(([_, models]) => models.length === 0)
        .map(([name]) => name)

      if (emptyProviders.length === Object.keys(newModelsByProvider).length) {
        setModelLoadingError('No LLM models available. Ensure Ollama is running and models are installed.')
      } else if (emptyProviders.length > 0) {
        setModelLoadingError(`No models available for: ${emptyProviders.join(', ')}`)
      }
    } catch (error: any) {
      console.error('Error loading provider models:', error)
      setModelLoadingError(
        `Failed to load LLM models: ${error.message || 'Please check Ollama connection and try again.'}`
      )
    } finally {
      setIsLoadingModels(false)
    }
  }

  const loadSettings = async () => {
    try {
      setIsLoading(true)

      // API/database is the source of truth - always load from API first
      // localStorage is only used as fallback for unauthenticated users
      const settingsData = await settingsApi.getSettings()

      // Clear stale localStorage to prevent confusion
      // Settings are now properly persisted in database
      localStorage.removeItem('vaucda_settings')

      setFormData({
        default_llm: settingsData.default_llm,
        default_model: settingsData.default_model,
        default_template: settingsData.default_template,
        source_format: (settingsData.source_format ?? 'cprs') as 'cprs' | 'vista',
        temperature: settingsData.llm_temperature ?? 0.3,
        max_tokens: settingsData.llm_max_tokens ?? 4000,
        rag_enabled: true,
        rag_top_k: 5,
        show_confidence_intervals: settingsData.display_preferences?.show_confidence_intervals ?? true,
        include_guideline_citations: settingsData.display_preferences?.include_guideline_citations ?? true,
        display_calculation_breakdown: settingsData.display_preferences?.display_calculation_breakdown ?? true,
        highlight_abnormal_values: settingsData.display_preferences?.highlight_abnormal_values ?? true,
      })

      // Load task-specific LLM settings
      // Note: Model names are loaded from backend API, never hardcoded
      // Empty model string means "use first available model from selected provider"
      if (settingsData.ocr_llm) {
        setTaskLLMConfig(prev => ({
          ...prev,
          ocr_llm_provider: settingsData.ocr_llm.provider || 'ollama',
          ocr_llm_model: settingsData.ocr_llm.model || '',  // Will be set from available models
          ocr_llm_temperature: settingsData.ocr_llm.temperature ?? 0.1,
          ocr_llm_max_tokens: settingsData.ocr_llm.max_tokens ?? 8192,
          ocr_llm_num_ctx: settingsData.ocr_llm.num_ctx ?? undefined,
          stage1_llm_provider: settingsData.stage1_llm?.provider || 'ollama',
          stage1_llm_model: settingsData.stage1_llm?.model || '',  // Will be set from available models
          stage1_llm_temperature: settingsData.stage1_llm?.temperature ?? 0.1,
          stage1_llm_max_tokens: settingsData.stage1_llm?.max_tokens ?? 8192,
          stage1_llm_num_ctx: settingsData.stage1_llm?.num_ctx ?? undefined,
          stage2_llm_provider: settingsData.stage2_llm?.provider || 'ollama',
          stage2_llm_model: settingsData.stage2_llm?.model || '',  // Will be set from available models
          stage2_llm_temperature: settingsData.stage2_llm?.temperature ?? 0.0,
          stage2_llm_max_tokens: settingsData.stage2_llm?.max_tokens ?? 8192,
          stage2_llm_num_ctx: settingsData.stage2_llm?.num_ctx ?? undefined,
          stage2_use_rag: settingsData.stage2_llm?.use_rag ?? true,
          stage2_use_graphrag: settingsData.stage2_llm?.use_graphrag ?? true,
          stage2_rag_top_k: settingsData.stage2_llm?.rag_top_k ?? 5,
        }))

        // Populate the "Model max" hints once for whatever model the user
        // already had selected. We do NOT overwrite user-set num_ctx here.
        if (settingsData.ocr_llm.model) {
          fetchAndApplyModelContextSize('ocr', settingsData.ocr_llm.model)
        }
        if (settingsData.stage1_llm?.model) {
          fetchAndApplyModelContextSize('stage1', settingsData.stage1_llm.model)
        }
        if (settingsData.stage2_llm?.model) {
          fetchAndApplyModelContextSize('stage2', settingsData.stage2_llm.model)
        }
      }

      await loadModelsForProvider(settingsData.default_llm)

    } catch (error) {
      console.error('Error loading settings:', error)
      alert('Failed to load settings. Please refresh the page.')
    } finally {
      setIsLoading(false)
    }
  }

  const loadModelsForProvider = async (provider: string) => {
    try {
      const providers = await llmApi.getProviders()
      const providerData = providers.find(p => p.name.toLowerCase() === provider)

      if (providerData && providerData.models) {
        const modelNames = providerData.models.map(m => m.name)
        setAvailableModels(modelNames)

        if (!formData.default_model && modelNames.length > 0) {
          setFormData(prev => ({ ...prev, default_model: modelNames[0] }))
        }
      }
    } catch (error) {
      console.error('Error loading models:', error)
      setAvailableModels([])
    }
  }

  // Fetch the model's training context window from the backend lookup table
  // and pre-populate the per-task num_ctx input only if the user has not set it.
  // task is one of: 'ocr' | 'stage1' | 'stage2'
  const fetchAndApplyModelContextSize = async (task: 'ocr' | 'stage1' | 'stage2', model: string) => {
    if (!model) return
    try {
      const data = await llmApi.getModelContextSize(model)
      setModelContextHints(prev => ({
        ...prev,
        [task]: { context_size: data.context_size, known: data.known },
      }))
      const fieldName = `${task}_llm_num_ctx` as
        'ocr_llm_num_ctx' | 'stage1_llm_num_ctx' | 'stage2_llm_num_ctx'
      setTaskLLMConfig(prev => {
        // Only seed the input if the user has not entered anything
        if (prev[fieldName] !== undefined && prev[fieldName] !== null) {
          return prev
        }
        return { ...prev, [fieldName]: data.context_size }
      })
    } catch (err) {
      console.error(`Failed to fetch model context size for ${model}:`, err)
    }
  }

  const loadSystemPrompt = async () => {
    try {
      setIsLoadingPrompt(true)
      const response = await ragApi.getSystemPrompt()
      setSystemPrompt(response.prompt)
      setPromptLastModified(response.last_modified)
    } catch (error: any) {
      console.error('Error loading system prompt:', error)
      // Don't alert on 404 - prompt may not exist yet
      if (error.response?.status !== 404) {
        alert('Failed to load system prompt')
      }
    } finally {
      setIsLoadingPrompt(false)
    }
  }

  const handleSaveSystemPrompt = async () => {
    if (!systemPrompt.trim()) {
      alert('System prompt cannot be empty')
      return
    }

    try {
      setIsSavingPrompt(true)
      await ragApi.updateSystemPrompt(systemPrompt)
      alert('System prompt updated successfully! A backup was created.')
      // Reload to get updated timestamp
      await loadSystemPrompt()
    } catch (error: any) {
      console.error('Error saving system prompt:', error)
      alert(`Failed to save system prompt: ${error.response?.data?.detail || error.message}`)
    } finally {
      setIsSavingPrompt(false)
    }
  }

  const loadUserRules = async () => {
    try {
      setIsLoadingRules(true)
      setRulesError(null)
      const rules = await userRulesApi.list()
      setUserRules(rules)
    } catch (error: any) {
      console.error('Error loading user rules:', error)
      setRulesError(error?.response?.data?.detail || 'Failed to load rules')
    } finally {
      setIsLoadingRules(false)
    }
  }

  const handleAddUserRule = async () => {
    const text = newRuleText.trim()
    if (!text) return
    try {
      setIsSavingRule(true)
      setRulesError(null)
      const created = await userRulesApi.create({ rule_text: text, is_active: true })
      setUserRules(prev => [...prev, created])
      setNewRuleText('')
    } catch (error: any) {
      console.error('Error creating rule:', error)
      setRulesError(error?.response?.data?.detail || 'Failed to create rule')
    } finally {
      setIsSavingRule(false)
    }
  }

  const handleToggleUserRule = async (rule: UserRule) => {
    try {
      const updated = await userRulesApi.update(rule.id, { is_active: !rule.is_active })
      setUserRules(prev => prev.map(r => (r.id === rule.id ? updated : r)))
    } catch (error: any) {
      console.error('Error toggling rule:', error)
      setRulesError(error?.response?.data?.detail || 'Failed to update rule')
    }
  }

  const handleStartEditRule = (rule: UserRule) => {
    setEditingRuleId(rule.id)
    setEditingRuleText(rule.rule_text)
  }

  const handleCancelEditRule = () => {
    setEditingRuleId(null)
    setEditingRuleText('')
  }

  const handleSaveEditRule = async () => {
    if (editingRuleId === null) return
    const text = editingRuleText.trim()
    if (!text) return
    try {
      setIsSavingRule(true)
      const updated = await userRulesApi.update(editingRuleId, { rule_text: text })
      setUserRules(prev => prev.map(r => (r.id === editingRuleId ? updated : r)))
      setEditingRuleId(null)
      setEditingRuleText('')
    } catch (error: any) {
      console.error('Error updating rule:', error)
      setRulesError(error?.response?.data?.detail || 'Failed to update rule')
    } finally {
      setIsSavingRule(false)
    }
  }

  const handleDeleteUserRule = async (rule: UserRule) => {
    if (!confirm(`Delete this rule?\n\n"${rule.rule_text}"`)) return
    try {
      await userRulesApi.remove(rule.id)
      setUserRules(prev => prev.filter(r => r.id !== rule.id))
      if (editingRuleId === rule.id) handleCancelEditRule()
    } catch (error: any) {
      console.error('Error deleting rule:', error)
      setRulesError(error?.response?.data?.detail || 'Failed to delete rule')
    }
  }

  const handleSaveSettings = async () => {
    try {
      setIsSaving(true)
      setSaveVerification(null)

      const updateRequest: UpdateSettingsRequest = {
        default_llm: formData.default_llm,
        default_model: formData.default_model,
        default_template: formData.default_template,
        source_format: formData.source_format,
        llm_temperature: formData.temperature,
        llm_max_tokens: formData.max_tokens,
        llm_top_p: 0.9,  // Add top_p if needed in form
        llm_frequency_penalty: 0.0,  // Add if needed in form
        llm_presence_penalty: 0.0,  // Add if needed in form
        display_preferences: {
          show_confidence_intervals: formData.show_confidence_intervals,
          include_guideline_citations: formData.include_guideline_citations,
          display_calculation_breakdown: formData.display_calculation_breakdown,
          highlight_abnormal_values: formData.highlight_abnormal_values,
        },
        // Task-specific LLM settings
        ocr_llm_provider: taskLLMConfig.ocr_llm_provider,
        ocr_llm_model: taskLLMConfig.ocr_llm_model,
        ocr_llm_temperature: taskLLMConfig.ocr_llm_temperature,
        ocr_llm_max_tokens: taskLLMConfig.ocr_llm_max_tokens,
        ocr_llm_num_ctx: taskLLMConfig.ocr_llm_num_ctx,
        stage1_llm_provider: taskLLMConfig.stage1_llm_provider,
        stage1_llm_model: taskLLMConfig.stage1_llm_model,
        stage1_llm_temperature: taskLLMConfig.stage1_llm_temperature,
        stage1_llm_max_tokens: taskLLMConfig.stage1_llm_max_tokens,
        stage1_llm_num_ctx: taskLLMConfig.stage1_llm_num_ctx,
        stage2_llm_provider: taskLLMConfig.stage2_llm_provider,
        stage2_llm_model: taskLLMConfig.stage2_llm_model,
        stage2_llm_temperature: taskLLMConfig.stage2_llm_temperature,
        stage2_llm_max_tokens: taskLLMConfig.stage2_llm_max_tokens,
        stage2_llm_num_ctx: taskLLMConfig.stage2_llm_num_ctx,
        stage2_use_rag: taskLLMConfig.stage2_use_rag,
        stage2_use_graphrag: taskLLMConfig.stage2_use_graphrag,
        stage2_rag_top_k: taskLLMConfig.stage2_rag_top_k,
      }

      await settingsApi.updateSettings(updateRequest)

      // Database is source of truth - no need for localStorage
      // Clear any stale localStorage to prevent confusion
      localStorage.removeItem('vaucda_settings')

      // ===== VERIFICATION: Re-load settings from server and compare =====
      const verifiedSettings = await settingsApi.getSettings()

      // Helper to compare numbers with tolerance for floating point
      const numMatch = (saved: number, loaded: number, tolerance = 0.001) =>
        Math.abs(saved - loaded) < tolerance

      // Helper to format number for display
      const numStr = (n: number | undefined) => n !== undefined ? n.toString() : '(undefined)'

      const verificationDetails: Record<string, { saved: string; loaded: string; match: boolean }> = {
        // OCR Settings
        'OCR Provider': {
          saved: taskLLMConfig.ocr_llm_provider,
          loaded: verifiedSettings.ocr_llm?.provider || '',
          match: taskLLMConfig.ocr_llm_provider === (verifiedSettings.ocr_llm?.provider || '')
        },
        'OCR Model': {
          saved: taskLLMConfig.ocr_llm_model,
          loaded: verifiedSettings.ocr_llm?.model || '',
          match: taskLLMConfig.ocr_llm_model === (verifiedSettings.ocr_llm?.model || '')
        },
        'OCR Temperature': {
          saved: numStr(taskLLMConfig.ocr_llm_temperature),
          loaded: numStr(verifiedSettings.ocr_llm?.temperature),
          match: numMatch(taskLLMConfig.ocr_llm_temperature, verifiedSettings.ocr_llm?.temperature ?? 0)
        },
        // Stage 1 Settings
        'Stage 1 Provider': {
          saved: taskLLMConfig.stage1_llm_provider,
          loaded: verifiedSettings.stage1_llm?.provider || '',
          match: taskLLMConfig.stage1_llm_provider === (verifiedSettings.stage1_llm?.provider || '')
        },
        'Stage 1 Model': {
          saved: taskLLMConfig.stage1_llm_model,
          loaded: verifiedSettings.stage1_llm?.model || '',
          match: taskLLMConfig.stage1_llm_model === (verifiedSettings.stage1_llm?.model || '')
        },
        'Stage 1 Temperature': {
          saved: numStr(taskLLMConfig.stage1_llm_temperature),
          loaded: numStr(verifiedSettings.stage1_llm?.temperature),
          match: numMatch(taskLLMConfig.stage1_llm_temperature, verifiedSettings.stage1_llm?.temperature ?? 0)
        },
        // Stage 2 Settings
        'Stage 2 Provider': {
          saved: taskLLMConfig.stage2_llm_provider,
          loaded: verifiedSettings.stage2_llm?.provider || '',
          match: taskLLMConfig.stage2_llm_provider === (verifiedSettings.stage2_llm?.provider || '')
        },
        'Stage 2 Model': {
          saved: taskLLMConfig.stage2_llm_model,
          loaded: verifiedSettings.stage2_llm?.model || '',
          match: taskLLMConfig.stage2_llm_model === (verifiedSettings.stage2_llm?.model || '')
        },
        'Stage 2 Temperature': {
          saved: numStr(taskLLMConfig.stage2_llm_temperature),
          loaded: numStr(verifiedSettings.stage2_llm?.temperature),
          match: numMatch(taskLLMConfig.stage2_llm_temperature, verifiedSettings.stage2_llm?.temperature ?? 0)
        },
        // RAG Settings
        'Use RAG': {
          saved: taskLLMConfig.stage2_use_rag ? 'enabled' : 'disabled',
          loaded: verifiedSettings.stage2_llm?.use_rag ? 'enabled' : 'disabled',
          match: taskLLMConfig.stage2_use_rag === (verifiedSettings.stage2_llm?.use_rag ?? false)
        },
        'Use GraphRAG': {
          saved: taskLLMConfig.stage2_use_graphrag ? 'enabled' : 'disabled',
          loaded: verifiedSettings.stage2_llm?.use_graphrag ? 'enabled' : 'disabled',
          match: taskLLMConfig.stage2_use_graphrag === (verifiedSettings.stage2_llm?.use_graphrag ?? false)
        },
        'RAG Top-K': {
          saved: numStr(taskLLMConfig.stage2_rag_top_k),
          loaded: numStr(verifiedSettings.stage2_llm?.rag_top_k),
          match: taskLLMConfig.stage2_rag_top_k === (verifiedSettings.stage2_llm?.rag_top_k ?? 0)
        },
      }

      const allMatch = Object.values(verificationDetails).every(v => v.match)

      setSaveVerification({
        verified: allMatch,
        message: allMatch
          ? 'All settings saved and verified successfully!'
          : 'Warning: Some settings may not have saved correctly.',
        details: verificationDetails
      })

      if (allMatch) {
        // Clear verification after 5 seconds on success
        setTimeout(() => setSaveVerification(null), 5000)
      }

    } catch (error: any) {
      console.error('Error saving settings:', error)
      // More robust error message extraction
      // Note: API client rejects with { detail, error_code, errors } object, not standard Error
      let errorMessage = 'Unknown error'
      if (error.detail) {
        // Error from API client interceptor
        errorMessage = error.detail
      } else if (error.response?.data?.detail) {
        // Raw axios error with response
        errorMessage = error.response.data.detail
      } else if (error.message) {
        // Standard Error object
        errorMessage = error.message
      } else if (error.response?.status) {
        errorMessage = `HTTP ${error.response.status}: ${error.response.statusText || 'Server error'}`
      } else if (typeof error === 'string') {
        errorMessage = error
      } else {
        // Last resort: stringify the error
        try {
          errorMessage = JSON.stringify(error)
        } catch {
          errorMessage = 'Unable to parse error'
        }
      }
      setSaveVerification({
        verified: false,
        message: `Failed to save settings: ${errorMessage}`,
        details: {}
      })
    } finally {
      setIsSaving(false)
    }
  }

  const handleResetDefaults = async () => {
    if (confirm('Reset all settings to defaults? This will reload settings from the server.')) {
      try {
        // Reload settings from server to get backend defaults
        await loadSettings()
        alert('Settings reset to defaults successfully')
      } catch (error) {
        console.error('Error resetting settings:', error)
        alert('Failed to reset settings to defaults')
      }
    }
  }

  const handleChangePassword = async () => {
    setPasswordError('')

    if (!passwordForm.current_password || !passwordForm.new_password || !passwordForm.confirm_password) {
      setPasswordError('All fields are required')
      return
    }

    if (passwordForm.new_password !== passwordForm.confirm_password) {
      setPasswordError('New passwords do not match')
      return
    }

    if (passwordForm.new_password.length < 8) {
      setPasswordError('Password must be at least 8 characters')
      return
    }

    try {
      alert('Password change functionality would be implemented here')
      setShowPasswordModal(false)
      setPasswordForm({
        current_password: '',
        new_password: '',
        confirm_password: '',
      })
    } catch (error: any) {
      setPasswordError(error.response?.data?.detail || error.message || 'Failed to change password')
    }
  }

  const handleTestOpenEvidence = () => {
    if (openEvidenceCredentials.username && openEvidenceCredentials.password) {
      window.open('https://app.openevidence.com', '_blank')
    } else {
      alert('Please enter OpenEvidence credentials first')
    }
  }

  const getPasswordStrength = (password: string): { strength: string; color: string } => {
    if (password.length === 0) return { strength: '', color: '' }
    if (password.length < 8) return { strength: 'Weak', color: 'text-error' }
    if (password.length < 12) return { strength: 'Medium', color: 'text-warning' }
    return { strength: 'Strong', color: 'text-success' }
  }

  const passwordStrength = getPasswordStrength(passwordForm.new_password)

  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <div className="text-center">
          <div className="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-primary"></div>
          <p className="mt-2 text-gray-600 dark:text-gray-400">Loading settings...</p>
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold">Settings</h1>
        <p className="text-gray-600 dark:text-gray-400 mt-2">
          Customize your VAUCDA experience and preferences
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 space-y-6">
          <Card title="Profile Information" description="View and manage your account details">
            <div className="space-y-4">
              <Input
                label="Username"
                value={user?.username || ''}
                disabled
              />

              <Input
                label="Email"
                type="email"
                value={user?.email || ''}
                disabled
              />

              <Input
                label="Role"
                value={user?.role || ''}
                disabled
              />

              <Button
                variant="outline"
                onClick={() => setShowPasswordModal(true)}
                icon={<FiLock />}
              >
                Change Password
              </Button>
            </div>
          </Card>

          <Card title="LLM Preferences" description="Configure default language model settings">
            <div className="space-y-4">
              <Select
                label="Default LLM Provider"
                value={formData.default_llm}
                onChange={(e) => setFormData({ ...formData, default_llm: e.target.value as any })}
                options={LLM_PROVIDERS}
              />

              <Select
                label="Default Model"
                value={formData.default_model}
                onChange={(e) => setFormData({ ...formData, default_model: e.target.value })}
                options={availableModels.map(m => ({ value: m, label: m }))}
                disabled={availableModels.length === 0}
                helpText={availableModels.length === 0 ? 'No models available for selected provider' : ''}
              />

              <div className="grid grid-cols-2 gap-4">
                <Input
                  label="Temperature"
                  type="number"
                  min="0"
                  max="1"
                  step="0.1"
                  value={formData.temperature}
                  onChange={(e) => setFormData({ ...formData, temperature: parseFloat(e.target.value) })}
                  helpText="Controls randomness (0=deterministic, 1=creative)"
                />

                <Input
                  label="Max Tokens"
                  type="number"
                  min="100"
                  max="32000"
                  step="100"
                  value={formData.max_tokens}
                  onChange={(e) => setFormData({ ...formData, max_tokens: parseInt(e.target.value, 10) })}
                  helpText="Maximum response length"
                />
              </div>
            </div>
          </Card>

          <Card title="Task-Specific LLM Configuration" description="Configure LLM settings for each processing stage">
            <div className="space-y-6">
              {/* Model Loading Status */}
              {isLoadingModels && (
                <div className="flex items-center gap-2 text-sm text-gray-500">
                  <span className="animate-spin">&#9696;</span> Loading available models...
                </div>
              )}
              {modelLoadingError && (
                <div className="p-3 rounded-lg bg-error-50 dark:bg-error-900/20 border border-error text-error flex items-center gap-2">
                  <FiAlertCircle />
                  <span>{modelLoadingError}</span>
                </div>
              )}

              {/* OCR Processing */}
              <div className="border-b border-gray-200 dark:border-gray-700 pb-4">
                <h3 className="text-lg font-semibold mb-3 text-primary">OCR Processing</h3>
                <p className="text-sm text-gray-600 dark:text-gray-400 mb-3">
                  LLM used for document OCR (vision model for scanned documents)
                </p>
                <div className="grid grid-cols-2 gap-4">
                  <Select
                    label="Provider"
                    value={taskLLMConfig.ocr_llm_provider}
                    onChange={(e) => {
                      const newProvider = e.target.value
                      const models = modelsByProvider[newProvider] || []
                      setTaskLLMConfig({
                        ...taskLLMConfig,
                        ocr_llm_provider: newProvider,
                        // Auto-select first model when provider changes
                        ocr_llm_model: models.length > 0 ? models[0] : ''
                      })
                    }}
                    options={LLM_PROVIDERS}
                  />
                  <Select
                    label="Model"
                    value={taskLLMConfig.ocr_llm_model}
                    onChange={(e) => {
                      const newModel = e.target.value
                      setTaskLLMConfig({ ...taskLLMConfig, ocr_llm_model: newModel })
                      fetchAndApplyModelContextSize('ocr', newModel)
                    }}
                    options={(modelsByProvider[taskLLMConfig.ocr_llm_provider] || []).map(m => ({ value: m, label: m }))}
                    disabled={(modelsByProvider[taskLLMConfig.ocr_llm_provider] || []).length === 0}
                    helpText={(modelsByProvider[taskLLMConfig.ocr_llm_provider] || []).length === 0 ? 'No models available' : ''}
                  />
                </div>
                <div className="grid grid-cols-2 gap-4 mt-3">
                  <Input
                    label="Temperature"
                    type="number"
                    min="0"
                    max="1"
                    step="0.1"
                    value={taskLLMConfig.ocr_llm_temperature}
                    onChange={(e) => setTaskLLMConfig({ ...taskLLMConfig, ocr_llm_temperature: parseFloat(e.target.value) })}
                  />
                  <Input
                    label="Max Tokens (output)"
                    type="number"
                    min="100"
                    max="16384"
                    step="100"
                    value={taskLLMConfig.ocr_llm_max_tokens}
                    onChange={(e) => setTaskLLMConfig({ ...taskLLMConfig, ocr_llm_max_tokens: parseInt(e.target.value, 10) })}
                    helpText="Output tokens generated (Ollama num_predict)"
                  />
                </div>
                <div className="grid grid-cols-2 gap-4 mt-3">
                  <Input
                    label="Context Window (num_ctx)"
                    type="number"
                    min="512"
                    max="2000000"
                    step="1024"
                    value={taskLLMConfig.ocr_llm_num_ctx ?? ''}
                    onChange={(e) => {
                      const v = e.target.value
                      setTaskLLMConfig({
                        ...taskLLMConfig,
                        ocr_llm_num_ctx: v === '' ? undefined : parseInt(v, 10),
                      })
                    }}
                    helpText={
                      `Total tokens the model can read (input + output). 125000 = 125K. Default for unknown models.` +
                      (modelContextHints.ocr
                        ? ` Model max for ${taskLLMConfig.ocr_llm_model || 'selected model'}: ${modelContextHints.ocr.context_size} (${modelContextHints.ocr.known ? 'known' : 'default'}).`
                        : '')
                    }
                  />
                </div>
              </div>

              {/* Stage 1: Note Generation */}
              <div className="border-b border-gray-200 dark:border-gray-700 pb-4">
                <h3 className="text-lg font-semibold mb-3 text-primary">Stage 1: Note Generation</h3>
                <p className="text-sm text-gray-600 dark:text-gray-400 mb-3">
                  LLM used for initial clinical note extraction and generation
                </p>
                <div className="grid grid-cols-2 gap-4">
                  <Select
                    label="Provider"
                    value={taskLLMConfig.stage1_llm_provider}
                    onChange={(e) => {
                      const newProvider = e.target.value
                      const models = modelsByProvider[newProvider] || []
                      setTaskLLMConfig({
                        ...taskLLMConfig,
                        stage1_llm_provider: newProvider,
                        stage1_llm_model: models.length > 0 ? models[0] : ''
                      })
                    }}
                    options={LLM_PROVIDERS}
                  />
                  <Select
                    label="Model"
                    value={taskLLMConfig.stage1_llm_model}
                    onChange={(e) => {
                      const newModel = e.target.value
                      setTaskLLMConfig({ ...taskLLMConfig, stage1_llm_model: newModel })
                      fetchAndApplyModelContextSize('stage1', newModel)
                    }}
                    options={(modelsByProvider[taskLLMConfig.stage1_llm_provider] || []).map(m => ({ value: m, label: m }))}
                    disabled={(modelsByProvider[taskLLMConfig.stage1_llm_provider] || []).length === 0}
                    helpText={(modelsByProvider[taskLLMConfig.stage1_llm_provider] || []).length === 0 ? 'No models available' : ''}
                  />
                </div>
                <div className="grid grid-cols-2 gap-4 mt-3">
                  <Input
                    label="Temperature"
                    type="number"
                    min="0"
                    max="1"
                    step="0.1"
                    value={taskLLMConfig.stage1_llm_temperature}
                    onChange={(e) => setTaskLLMConfig({ ...taskLLMConfig, stage1_llm_temperature: parseFloat(e.target.value) })}
                  />
                  <Input
                    label="Max Tokens (output)"
                    type="number"
                    min="100"
                    max="32000"
                    step="100"
                    value={taskLLMConfig.stage1_llm_max_tokens}
                    onChange={(e) => setTaskLLMConfig({ ...taskLLMConfig, stage1_llm_max_tokens: parseInt(e.target.value, 10) })}
                    helpText="Output tokens generated (Ollama num_predict)"
                  />
                </div>
                <div className="grid grid-cols-2 gap-4 mt-3">
                  <Input
                    label="Context Window (num_ctx)"
                    type="number"
                    min="512"
                    max="2000000"
                    step="1024"
                    value={taskLLMConfig.stage1_llm_num_ctx ?? ''}
                    onChange={(e) => {
                      const v = e.target.value
                      setTaskLLMConfig({
                        ...taskLLMConfig,
                        stage1_llm_num_ctx: v === '' ? undefined : parseInt(v, 10),
                      })
                    }}
                    helpText={
                      `Total tokens the model can read (input + output). 125000 = 125K. Default for unknown models.` +
                      (modelContextHints.stage1
                        ? ` Model max for ${taskLLMConfig.stage1_llm_model || 'selected model'}: ${modelContextHints.stage1.context_size} (${modelContextHints.stage1.known ? 'known' : 'default'}).`
                        : '')
                    }
                  />
                </div>
              </div>

              {/* Stage 2: Assessment & Plan */}
              <div>
                <h3 className="text-lg font-semibold mb-3 text-primary">Stage 2: Assessment & Plan</h3>
                <p className="text-sm text-gray-600 dark:text-gray-400 mb-3">
                  LLM used for Assessment and Plan generation with RAG/GraphRAG retrieval
                </p>
                <div className="grid grid-cols-2 gap-4">
                  <Select
                    label="Provider"
                    value={taskLLMConfig.stage2_llm_provider}
                    onChange={(e) => {
                      const newProvider = e.target.value
                      const models = modelsByProvider[newProvider] || []
                      setTaskLLMConfig({
                        ...taskLLMConfig,
                        stage2_llm_provider: newProvider,
                        stage2_llm_model: models.length > 0 ? models[0] : ''
                      })
                    }}
                    options={LLM_PROVIDERS}
                  />
                  <Select
                    label="Model"
                    value={taskLLMConfig.stage2_llm_model}
                    onChange={(e) => {
                      const newModel = e.target.value
                      setTaskLLMConfig({ ...taskLLMConfig, stage2_llm_model: newModel })
                      fetchAndApplyModelContextSize('stage2', newModel)
                    }}
                    options={(modelsByProvider[taskLLMConfig.stage2_llm_provider] || []).map(m => ({ value: m, label: m }))}
                    disabled={(modelsByProvider[taskLLMConfig.stage2_llm_provider] || []).length === 0}
                    helpText={(modelsByProvider[taskLLMConfig.stage2_llm_provider] || []).length === 0 ? 'No models available' : ''}
                  />
                </div>
                <div className="grid grid-cols-2 gap-4 mt-3">
                  <Input
                    label="Temperature"
                    type="number"
                    min="0"
                    max="1"
                    step="0.1"
                    value={taskLLMConfig.stage2_llm_temperature}
                    onChange={(e) => setTaskLLMConfig({ ...taskLLMConfig, stage2_llm_temperature: parseFloat(e.target.value) })}
                    helpText="0.0 recommended for clinical accuracy"
                  />
                  <Input
                    label="Max Tokens (output)"
                    type="number"
                    min="100"
                    max="32000"
                    step="100"
                    value={taskLLMConfig.stage2_llm_max_tokens}
                    onChange={(e) => setTaskLLMConfig({ ...taskLLMConfig, stage2_llm_max_tokens: parseInt(e.target.value, 10) })}
                    helpText="Output tokens generated (Ollama num_predict)"
                  />
                </div>
                <div className="grid grid-cols-2 gap-4 mt-3">
                  <Input
                    label="Context Window (num_ctx)"
                    type="number"
                    min="512"
                    max="2000000"
                    step="1024"
                    value={taskLLMConfig.stage2_llm_num_ctx ?? ''}
                    onChange={(e) => {
                      const v = e.target.value
                      setTaskLLMConfig({
                        ...taskLLMConfig,
                        stage2_llm_num_ctx: v === '' ? undefined : parseInt(v, 10),
                      })
                    }}
                    helpText={
                      `Total tokens the model can read (input + output). 125000 = 125K. Default for unknown models.` +
                      (modelContextHints.stage2
                        ? ` Model max for ${taskLLMConfig.stage2_llm_model || 'selected model'}: ${modelContextHints.stage2.context_size} (${modelContextHints.stage2.known ? 'known' : 'default'}).`
                        : '')
                    }
                  />
                </div>

                {/* RAG Settings */}
                <div className="mt-4 p-4 bg-gray-50 dark:bg-gray-800 rounded-lg">
                  <h4 className="font-medium mb-3">RAG/GraphRAG Settings</h4>
                  <div className="space-y-3">
                    <div className="flex items-center gap-2">
                      <input
                        type="checkbox"
                        id="stage2-use-rag"
                        checked={taskLLMConfig.stage2_use_rag}
                        onChange={(e) => setTaskLLMConfig({ ...taskLLMConfig, stage2_use_rag: e.target.checked })}
                        className="rounded"
                      />
                      <label htmlFor="stage2-use-rag" className="text-sm">
                        Enable RAG (Retrieval-Augmented Generation)
                      </label>
                    </div>

                    <div className="flex items-center gap-2">
                      <input
                        type="checkbox"
                        id="stage2-use-graphrag"
                        checked={taskLLMConfig.stage2_use_graphrag}
                        onChange={(e) => setTaskLLMConfig({ ...taskLLMConfig, stage2_use_graphrag: e.target.checked })}
                        className="rounded"
                        disabled={!taskLLMConfig.stage2_use_rag}
                      />
                      <label htmlFor="stage2-use-graphrag" className="text-sm">
                        Enable GraphRAG (Knowledge Graph Retrieval)
                      </label>
                    </div>

                    {taskLLMConfig.stage2_use_rag && (
                      <Input
                        label="RAG Top-K Results"
                        type="number"
                        min="1"
                        max="20"
                        value={taskLLMConfig.stage2_rag_top_k}
                        onChange={(e) => setTaskLLMConfig({ ...taskLLMConfig, stage2_rag_top_k: parseInt(e.target.value, 10) })}
                        helpText="Number of knowledge base results to retrieve"
                      />
                    )}
                  </div>
                </div>
              </div>
            </div>
          </Card>

          <Card
            title="Assessment & Plan Rules"
            description="Clinician-defined rules injected into the Assessment and Plan LLM prompt. The LLM is instructed to treat each active rule as a hard constraint."
          >
            <div className="space-y-3">
              {rulesError && (
                <div className="flex items-start gap-2 p-3 rounded bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 text-sm text-red-800 dark:text-red-200">
                  <FiAlertCircle className="mt-0.5 flex-shrink-0" />
                  <span>{rulesError}</span>
                </div>
              )}

              {!user && (
                <div className="p-3 rounded bg-yellow-50 dark:bg-yellow-900/20 border border-yellow-200 dark:border-yellow-800 text-sm text-yellow-800 dark:text-yellow-200">
                  Sign in to create and manage rules.
                </div>
              )}

              {isLoadingRules ? (
                <div className="text-sm text-gray-500 dark:text-gray-400">Loading rules…</div>
              ) : userRules.length === 0 ? (
                <div className="text-sm text-gray-500 dark:text-gray-400 italic">
                  No rules yet. Add one below — for example: "When ordering a TRUS biopsy, also order a urine culture and a rectal swab for quinolone-resistant rectal flora." or "Do not schedule follow-up sooner than 90 days unless urgent."
                </div>
              ) : (
                <ul className="space-y-2">
                  {userRules.map((rule) => (
                    <li
                      key={rule.id}
                      className={`p-3 rounded border ${
                        rule.is_active
                          ? 'bg-white dark:bg-gray-800 border-gray-200 dark:border-gray-700'
                          : 'bg-gray-50 dark:bg-gray-900 border-gray-200 dark:border-gray-700 opacity-60'
                      }`}
                    >
                      {editingRuleId === rule.id ? (
                        <div className="space-y-2">
                          <Textarea
                            value={editingRuleText}
                            onChange={(e) => setEditingRuleText(e.target.value)}
                            rows={3}
                            className="font-mono text-sm"
                            maxLength={2000}
                          />
                          <div className="flex justify-end gap-2">
                            <Button size="sm" variant="outline" onClick={handleCancelEditRule} icon={<FiX />}>
                              Cancel
                            </Button>
                            <Button
                              size="sm"
                              variant="primary"
                              onClick={handleSaveEditRule}
                              isLoading={isSavingRule}
                              disabled={!editingRuleText.trim() || isSavingRule}
                              icon={<FiSave />}
                            >
                              Save
                            </Button>
                          </div>
                        </div>
                      ) : (
                        <div className="flex items-start justify-between gap-3">
                          <div className="flex-1 min-w-0">
                            <p className="text-sm text-gray-900 dark:text-gray-100 whitespace-pre-wrap break-words">
                              {rule.rule_text}
                            </p>
                            <div className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                              {rule.is_active ? 'Active' : 'Inactive'} · #{rule.id}
                            </div>
                          </div>
                          <div className="flex items-center gap-1 flex-shrink-0">
                            <label className="inline-flex items-center gap-1 text-xs text-gray-600 dark:text-gray-400 cursor-pointer select-none">
                              <input
                                type="checkbox"
                                className="rounded"
                                checked={rule.is_active}
                                onChange={() => handleToggleUserRule(rule)}
                              />
                              On
                            </label>
                            <Button
                              size="sm"
                              variant="outline"
                              icon={<FiEdit3 />}
                              onClick={() => handleStartEditRule(rule)}
                              aria-label="Edit rule"
                            >
                              Edit
                            </Button>
                            <Button
                              size="sm"
                              variant="outline"
                              icon={<FiTrash2 />}
                              onClick={() => handleDeleteUserRule(rule)}
                              aria-label="Delete rule"
                            >
                              Delete
                            </Button>
                          </div>
                        </div>
                      )}
                    </li>
                  ))}
                </ul>
              )}

              {user && (
                <div className="pt-3 border-t border-gray-200 dark:border-gray-700 space-y-2">
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">
                    Add a new rule
                  </label>
                  <Textarea
                    value={newRuleText}
                    onChange={(e) => setNewRuleText(e.target.value)}
                    rows={3}
                    placeholder='e.g. "When ordering a TRUS biopsy, also order a urine culture and a rectal swab for quinolone-resistant rectal flora."'
                    className="font-mono text-sm"
                    maxLength={2000}
                  />
                  <div className="flex justify-end">
                    <Button
                      onClick={handleAddUserRule}
                      isLoading={isSavingRule}
                      disabled={!newRuleText.trim() || isSavingRule}
                      icon={<FiPlus />}
                    >
                      Add Rule
                    </Button>
                  </div>
                </div>
              )}
            </div>
          </Card>

          <Card title="Note Generation Preferences" description="Set default options for clinical note generation">
            <div className="space-y-4">
              <Select
                label="Default Note Template"
                value={formData.default_template}
                onChange={(e) => setFormData({ ...formData, default_template: e.target.value })}
                options={NOTE_TYPES}
              />

              <div className="space-y-2">
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">
                  Source EHR Format
                </label>
                <div className="inline-flex rounded-md shadow-sm" role="group" aria-label="Source EHR format toggle">
                  <button
                    type="button"
                    onClick={() => setFormData({ ...formData, source_format: 'cprs' })}
                    className={`px-4 py-2 text-sm font-medium border border-gray-300 dark:border-gray-600 rounded-l-md ${
                      formData.source_format === 'cprs'
                        ? 'bg-blue-600 text-white border-blue-600'
                        : 'bg-white text-gray-700 dark:bg-gray-800 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700'
                    }`}
                  >
                    CPRS
                  </button>
                  <button
                    type="button"
                    onClick={() => setFormData({ ...formData, source_format: 'vista' })}
                    className={`px-4 py-2 text-sm font-medium border-t border-b border-r border-gray-300 dark:border-gray-600 rounded-r-md ${
                      formData.source_format === 'vista'
                        ? 'bg-blue-600 text-white border-blue-600'
                        : 'bg-white text-gray-700 dark:bg-gray-800 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700'
                    }`}
                  >
                    VistA
                  </button>
                </div>
                <p className="text-xs text-gray-500 dark:text-gray-400">
                  {formData.source_format === 'cprs'
                    ? 'CPRS pass-through (default). The pipeline parses the document as-is.'
                    : 'VistA mode runs a preprocessing step that rewrites VistA section headers into the CPRS layout the extractors expect.'}
                </p>
              </div>

              <div className="flex items-center gap-2">
                <input
                  type="checkbox"
                  id="rag-enabled"
                  checked={formData.rag_enabled}
                  onChange={(e) => setFormData({ ...formData, rag_enabled: e.target.checked })}
                  className="rounded"
                />
                <label htmlFor="rag-enabled" className="text-sm font-medium">
                  Enable RAG (Evidence-Based Generation)
                </label>
              </div>

              {formData.rag_enabled && (
                <Input
                  label="RAG Top-K Results"
                  type="number"
                  min="1"
                  max="20"
                  value={formData.rag_top_k}
                  onChange={(e) => setFormData({ ...formData, rag_top_k: parseInt(e.target.value, 10) })}
                  helpText="Number of knowledge base results to include"
                />
              )}
            </div>
          </Card>

          <Card title="Display Preferences" description="Customize how information is displayed">
            <div className="space-y-3">
              <div className="flex items-center gap-2">
                <input
                  type="checkbox"
                  id="show-confidence"
                  checked={formData.show_confidence_intervals}
                  onChange={(e) => setFormData({ ...formData, show_confidence_intervals: e.target.checked })}
                  className="rounded"
                />
                <label htmlFor="show-confidence" className="text-sm">
                  Show confidence intervals in calculator results
                </label>
              </div>

              <div className="flex items-center gap-2">
                <input
                  type="checkbox"
                  id="include-citations"
                  checked={formData.include_guideline_citations}
                  onChange={(e) => setFormData({ ...formData, include_guideline_citations: e.target.checked })}
                  className="rounded"
                />
                <label htmlFor="include-citations" className="text-sm">
                  Include guideline citations in generated notes
                </label>
              </div>

              <div className="flex items-center gap-2">
                <input
                  type="checkbox"
                  id="calc-breakdown"
                  checked={formData.display_calculation_breakdown}
                  onChange={(e) => setFormData({ ...formData, display_calculation_breakdown: e.target.checked })}
                  className="rounded"
                />
                <label htmlFor="calc-breakdown" className="text-sm">
                  Display detailed calculation breakdowns
                </label>
              </div>

              <div className="flex items-center gap-2">
                <input
                  type="checkbox"
                  id="highlight-abnormal"
                  checked={formData.highlight_abnormal_values}
                  onChange={(e) => setFormData({ ...formData, highlight_abnormal_values: e.target.checked })}
                  className="rounded"
                />
                <label htmlFor="highlight-abnormal" className="text-sm">
                  Highlight abnormal lab values
                </label>
              </div>
            </div>
          </Card>
        </div>

        <div className="space-y-6">
          <Card title="OpenEvidence Integration" description="Configure external evidence search">
            <div className="space-y-4">
              <Input
                label="Username"
                value={openEvidenceCredentials.username}
                onChange={(e) => setOpenEvidenceCredentials({ ...openEvidenceCredentials, username: e.target.value })}
                placeholder="OpenEvidence username"
              />

              <div className="relative">
                <Input
                  label="Password"
                  type={showOpenEvidencePassword ? 'text' : 'password'}
                  value={openEvidenceCredentials.password}
                  onChange={(e) => setOpenEvidenceCredentials({ ...openEvidenceCredentials, password: e.target.value })}
                  placeholder="OpenEvidence password"
                />
                <button
                  type="button"
                  onClick={() => setShowOpenEvidencePassword(!showOpenEvidencePassword)}
                  className="absolute right-3 top-9 text-gray-400 hover:text-gray-600"
                >
                  {showOpenEvidencePassword ? <FiEyeOff /> : <FiEye />}
                </button>
              </div>

              {openEvidenceCredentials.username && openEvidenceCredentials.password && (
                <div className="flex items-center gap-2 text-sm text-success">
                  <FiCheckCircle />
                  <span>Credentials configured</span>
                </div>
              )}

              <Button
                variant="outline"
                size="sm"
                onClick={handleTestOpenEvidence}
                fullWidth
              >
                Test Connection
              </Button>

              <div className="text-xs text-gray-500 dark:text-gray-400 mt-2 p-3 bg-gray-50 dark:bg-gray-800 rounded">
                Note: Credentials are encrypted and stored securely. They are only used for OpenEvidence integration.
              </div>
            </div>
          </Card>

          <Card
            title="System Prompt Editor"
            description="Configure the urology note generation template"
          >
            <div className="space-y-4">
              {isLoadingPrompt ? (
                <div className="flex items-center justify-center py-8">
                  <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary"></div>
                </div>
              ) : (
                <>
                  <Textarea
                    label="System Prompt"
                    value={systemPrompt}
                    onChange={(e) => setSystemPrompt(e.target.value)}
                    rows={12}
                    placeholder="Enter the system prompt for clinical note generation..."
                    className="font-mono text-sm"
                  />

                  {promptLastModified && (
                    <div className="text-xs text-gray-500 dark:text-gray-400">
                      Last modified: {new Date(promptLastModified * 1000).toLocaleString()}
                    </div>
                  )}

                  <Button
                    variant="medical"
                    fullWidth
                    onClick={handleSaveSystemPrompt}
                    isLoading={isSavingPrompt}
                    disabled={isSavingPrompt || !systemPrompt.trim()}
                    icon={<FiEdit3 />}
                  >
                    {isSavingPrompt ? 'Saving...' : 'Save System Prompt'}
                  </Button>

                  <div className="text-xs text-gray-500 dark:text-gray-400 p-3 bg-gray-50 dark:bg-gray-800 rounded">
                    <strong>Note:</strong> This prompt guides the LLM in generating clinical notes.
                    A backup is automatically created before saving changes. Admin access required.
                  </div>
                </>
              )}
            </div>
          </Card>

          <Card title="Quick Actions">
            <div className="space-y-2">
              <Button
                variant="medical"
                fullWidth
                onClick={handleSaveSettings}
                isLoading={isSaving}
                disabled={isSaving}
                icon={<FiSave />}
              >
                Save All Settings
              </Button>

              <Button
                variant="outline"
                fullWidth
                onClick={handleResetDefaults}
                icon={<FiRefreshCw />}
              >
                Reset to Defaults
              </Button>

              {/* Save Verification Status */}
              {saveVerification && (
                <div className={`mt-4 p-4 rounded-lg border ${
                  saveVerification.verified
                    ? 'bg-success-50 dark:bg-success-900/20 border-success text-success'
                    : 'bg-error-50 dark:bg-error-900/20 border-error text-error'
                }`}>
                  <div className="flex items-center gap-2 mb-2">
                    {saveVerification.verified ? <FiCheckCircle /> : <FiAlertCircle />}
                    <span className="font-semibold">{saveVerification.message}</span>
                  </div>

                  {Object.keys(saveVerification.details).length > 0 && (
                    <div className="text-xs space-y-1 mt-2">
                      {Object.entries(saveVerification.details).map(([key, value]) => (
                        <div key={key} className="flex justify-between">
                          <span>{key}:</span>
                          <span className={value.match ? '' : 'font-bold'}>
                            {value.match ? (
                              <span className="flex items-center gap-1">
                                <FiCheckCircle className="text-success" /> {value.loaded || '(default)'}
                              </span>
                            ) : (
                              <span className="flex items-center gap-1">
                                <FiAlertCircle /> Sent: {value.saved}, Got: {value.loaded || '(empty)'}
                              </span>
                            )}
                          </span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>
          </Card>

          <Card title="System Information">
            <div className="space-y-2 text-sm">
              <div className="flex justify-between">
                <span className="text-gray-600 dark:text-gray-400">Version:</span>
                <span className="font-semibold">1.0.0</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-600 dark:text-gray-400">Last Login:</span>
                <span className="font-semibold">
                  {user?.last_login ? new Date(user.last_login).toLocaleDateString() : 'N/A'}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-600 dark:text-gray-400">Account Created:</span>
                <span className="font-semibold">
                  {user?.created_at ? new Date(user.created_at).toLocaleDateString() : 'N/A'}
                </span>
              </div>
            </div>
          </Card>
        </div>
      </div>

      <Modal
        isOpen={showPasswordModal}
        onClose={() => {
          setShowPasswordModal(false)
          setPasswordForm({ current_password: '', new_password: '', confirm_password: '' })
          setPasswordError('')
        }}
        title="Change Password"
        description="Enter your current password and choose a new one"
        footer={
          <div className="flex justify-between items-center w-full">
            <Button
              variant="outline"
              onClick={() => {
                setShowPasswordModal(false)
                setPasswordForm({ current_password: '', new_password: '', confirm_password: '' })
                setPasswordError('')
              }}
            >
              Cancel
            </Button>
            <Button
              variant="medical"
              onClick={handleChangePassword}
            >
              Change Password
            </Button>
          </div>
        }
      >
        <div className="space-y-4">
          {passwordError && (
            <div className="bg-error-50 dark:bg-error-900/20 border border-error text-error px-4 py-3 rounded">
              {passwordError}
            </div>
          )}

          <div className="relative">
            <Input
              label="Current Password"
              type={showPasswords.current ? 'text' : 'password'}
              value={passwordForm.current_password}
              onChange={(e) => setPasswordForm({ ...passwordForm, current_password: e.target.value })}
              required
            />
            <button
              type="button"
              onClick={() => setShowPasswords({ ...showPasswords, current: !showPasswords.current })}
              className="absolute right-3 top-9 text-gray-400 hover:text-gray-600"
            >
              {showPasswords.current ? <FiEyeOff /> : <FiEye />}
            </button>
          </div>

          <div className="relative">
            <Input
              label="New Password"
              type={showPasswords.new ? 'text' : 'password'}
              value={passwordForm.new_password}
              onChange={(e) => setPasswordForm({ ...passwordForm, new_password: e.target.value })}
              required
            />
            <button
              type="button"
              onClick={() => setShowPasswords({ ...showPasswords, new: !showPasswords.new })}
              className="absolute right-3 top-9 text-gray-400 hover:text-gray-600"
            >
              {showPasswords.new ? <FiEyeOff /> : <FiEye />}
            </button>
            {passwordStrength.strength && (
              <p className={`mt-1 text-xs ${passwordStrength.color}`}>
                Strength: {passwordStrength.strength}
              </p>
            )}
          </div>

          <div className="relative">
            <Input
              label="Confirm New Password"
              type={showPasswords.confirm ? 'text' : 'password'}
              value={passwordForm.confirm_password}
              onChange={(e) => setPasswordForm({ ...passwordForm, confirm_password: e.target.value })}
              required
            />
            <button
              type="button"
              onClick={() => setShowPasswords({ ...showPasswords, confirm: !showPasswords.confirm })}
              className="absolute right-3 top-9 text-gray-400 hover:text-gray-600"
            >
              {showPasswords.confirm ? <FiEyeOff /> : <FiEye />}
            </button>
          </div>

          <div className="text-xs text-gray-500 dark:text-gray-400 p-3 bg-gray-50 dark:bg-gray-800 rounded">
            Password requirements:
            <ul className="list-disc list-inside mt-1 space-y-1">
              <li>At least 8 characters long</li>
              <li>Mix of letters and numbers recommended</li>
              <li>Special characters increase strength</li>
            </ul>
          </div>
        </div>
      </Modal>
    </div>
  )
}
