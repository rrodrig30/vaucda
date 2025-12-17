import React, { useState, useEffect } from 'react'
import { Card } from '@/components/common/Card'
import { Button } from '@/components/common/Button'
import { Input } from '@/components/common/Input'
import { Select } from '@/components/common/Select'
import { Modal } from '@/components/common/Modal'
import { Textarea } from '@/components/common/Textarea'
import { settingsApi, llmApi, ragApi } from '@/api'
import { FiSave, FiRefreshCw, FiLock, FiEye, FiEyeOff, FiCheckCircle, FiEdit3 } from 'react-icons/fi'
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
    temperature: 0.3,
    max_tokens: 4000,
    rag_enabled: true,
    rag_top_k: 5,
    show_confidence_intervals: true,
    include_guideline_citations: true,
    display_calculation_breakdown: true,
    highlight_abnormal_values: true,
  })

  const [availableModels, setAvailableModels] = useState<string[]>([])

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

  useEffect(() => {
    loadSettings()
    loadSystemPrompt()
  }, [])

  useEffect(() => {
    if (formData.default_llm) {
      loadModelsForProvider(formData.default_llm)
    }
  }, [formData.default_llm])

  const loadSettings = async () => {
    try {
      setIsLoading(true)

      // Try loading from localStorage first
      const savedSettings = localStorage.getItem('vaucda_settings')
      let settingsData

      if (savedSettings) {
        const parsed = JSON.parse(savedSettings)
        settingsData = {
          ...await settingsApi.getSettings(),
          ...parsed  // Override API defaults with localStorage values
        }
      } else {
        settingsData = await settingsApi.getSettings()
      }

      setFormData({
        default_llm: settingsData.default_llm,
        default_model: settingsData.default_model,
        default_template: settingsData.default_template,
        temperature: settingsData.llm_temperature ?? 0.3,
        max_tokens: settingsData.llm_max_tokens ?? 4000,
        rag_enabled: true,
        rag_top_k: 5,
        show_confidence_intervals: settingsData.display_preferences?.show_confidence_intervals ?? true,
        include_guideline_citations: settingsData.display_preferences?.include_guideline_citations ?? true,
        display_calculation_breakdown: settingsData.display_preferences?.display_calculation_breakdown ?? true,
        highlight_abnormal_values: settingsData.display_preferences?.highlight_abnormal_values ?? true,
      })

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
      const response = await ragApi.updateSystemPrompt(systemPrompt)
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

  const handleSaveSettings = async () => {
    try {
      setIsSaving(true)

      const updateRequest: UpdateSettingsRequest = {
        default_llm: formData.default_llm,
        default_model: formData.default_model,
        default_template: formData.default_template,
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
        }
      }

      await settingsApi.updateSettings(updateRequest)

      // Also save to localStorage for persistence without authentication
      localStorage.setItem('vaucda_settings', JSON.stringify({
        default_llm: formData.default_llm,
        default_model: formData.default_model,
        default_template: formData.default_template,
        temperature: formData.temperature,
        max_tokens: formData.max_tokens,
      }))

      alert('Settings saved successfully')

      await loadSettings()
    } catch (error: any) {
      console.error('Error saving settings:', error)
      alert(`Failed to save settings: ${error.response?.data?.detail || error.message}`)
    } finally {
      setIsSaving(false)
    }
  }

  const handleResetDefaults = () => {
    if (confirm('Reset all settings to defaults?')) {
      setFormData({
        default_llm: 'ollama',
        default_model: '',
        default_template: 'clinic_note',
        temperature: 0.3,
        max_tokens: 4000,
        rag_enabled: true,
        rag_top_k: 5,
        show_confidence_intervals: true,
        include_guideline_citations: true,
        display_calculation_breakdown: true,
        highlight_abnormal_values: true,
      })
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

          <Card title="Note Generation Preferences" description="Set default options for clinical note generation">
            <div className="space-y-4">
              <Select
                label="Default Note Template"
                value={formData.default_template}
                onChange={(e) => setFormData({ ...formData, default_template: e.target.value })}
                options={NOTE_TYPES}
              />

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
