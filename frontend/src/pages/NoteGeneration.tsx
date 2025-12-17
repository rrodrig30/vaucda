import React, { useState, useEffect } from 'react'
import { Card } from '@/components/common/Card'
import { Button } from '@/components/common/Button'
import { Textarea } from '@/components/common/Textarea'
import { Select } from '@/components/common/Select'
import { AmbientListening } from '@/components/notes/AmbientListening'
import { CalculatorSuggestionPanel } from '@/components/notes/CalculatorSuggestionPanel'
import { NoteEditor } from '@/components/notes/NoteEditor'
import { notesApi, llmApi, settingsApi } from '@/api'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import rehypeHighlight from 'rehype-highlight'
import { FiCopy, FiDownload, FiSave, FiPlay, FiCheckCircle, FiChevronRight, FiEdit } from 'react-icons/fi'
import type {
  InitialNoteRequest,
  InitialNoteResponse,
  FinalNoteRequest,
  FinalNoteResponse,
  ExtractedEntity,
  CalculatorSuggestion
} from '@/types/api.types'

const MAX_CHAR_LIMIT = 1000000  // 1 million characters (~1MB) for extensive clinical data
const AUTO_SAVE_INTERVAL = 30000

const NOTE_TYPES = [
  { value: 'urology_clinic', label: 'Urology Clinic' },
  { value: 'urology_consult', label: 'Urology Consult' },
]

const LLM_PROVIDERS = [
  { value: 'ollama', label: 'Ollama (Local)' },
  { value: 'anthropic', label: 'Anthropic Claude' },
  { value: 'openai', label: 'OpenAI GPT' },
]

export const NoteGeneration: React.FC = () => {
  // ========== Configuration State ==========
  const [noteType, setNoteType] = useState<string>('urology_clinic')
  const [llmProvider, setLlmProvider] = useState<'ollama' | 'anthropic' | 'openai'>('ollama')
  const [selectedModel, setSelectedModel] = useState<string>('')
  const [availableModels, setAvailableModels] = useState<string[]>([])
  const [useRAG, setUseRAG] = useState(true)
  const [temperature, setTemperature] = useState(0.3)

  // ========== Clinical Input State ==========
  const [clinicalInput, setClinicalInput] = useState('')
  const [ambientTranscription, setAmbientTranscription] = useState('')

  // ========== Patient Information State ==========
  const [patientName, setPatientName] = useState('')
  const [ssnLast4, setSsnLast4] = useState('')

  // ========== Stage 1 State ==========
  const [isGeneratingInitial, setIsGeneratingInitial] = useState(false)
  const [preliminaryNote, setPreliminaryNote] = useState('')
  const [isEditingStage1, setIsEditingStage1] = useState(false)
  const [extractedEntities, setExtractedEntities] = useState<ExtractedEntity[]>([])
  const [suggestedCalculators, setSuggestedCalculators] = useState<CalculatorSuggestion[]>([])
  const [stage1Metadata, setStage1Metadata] = useState<any>(null)

  // ========== Stage 2 State ==========
  const [isGeneratingFinal, setIsGeneratingFinal] = useState(false)
  const [selectedCalculators, setSelectedCalculators] = useState<string[]>([])
  const [additionalInputs, setAdditionalInputs] = useState<Record<string, any>>({})
  const [finalNote, setFinalNote] = useState('')
  const [isEditingStage2, setIsEditingStage2] = useState(false)
  const [calculatorResults, setCalculatorResults] = useState<any[]>([])
  const [ragSources, setRagSources] = useState<any[]>([])
  const [stage2Metadata, setStage2Metadata] = useState<any>(null)

  // ========== Stage 3 State (Ambient Augmented) ==========
  const [isAmbientActive, setIsAmbientActive] = useState(false)
  const [isGeneratingAmbient, setIsGeneratingAmbient] = useState(false)
  const [ambientAugmentedNote, setAmbientAugmentedNote] = useState('')
  const [stage3Metadata, setStage3Metadata] = useState<any>(null)

  // ========== Workflow State ==========
  const [currentStage, setCurrentStage] = useState<'input' | 'preliminary' | 'final' | 'ambient'>('input')

  // ========== Initialization ==========
  useEffect(() => {
    loadInitialData()

    // HIPAA COMPLIANCE: Do NOT load saved clinical input from localStorage
    // Patient data should NOT persist across sessions
    // Clear any leftover PHI data from previous sessions
    localStorage.removeItem('vaucda_clinical_input')
    localStorage.removeItem('vaucda_draft_note')
    localStorage.removeItem('vaucda_draft_note_ambient')

    // Load saved model selection (non-PHI, safe to persist)
    const savedModel = localStorage.getItem('vaucda_selected_model')
    if (savedModel) {
      setSelectedModel(savedModel)
    }

    // HIPAA COMPLIANCE: NO auto-save of clinical input to localStorage
    // Patient data should only exist in memory during active session

    // HIPAA COMPLIANCE: Clear all PHI data when navigating away or closing browser
    const handleBeforeUnload = () => {
      localStorage.removeItem('vaucda_clinical_input')
      localStorage.removeItem('vaucda_draft_note')
      localStorage.removeItem('vaucda_draft_note_ambient')
    }

    window.addEventListener('beforeunload', handleBeforeUnload)

    return () => {
      window.removeEventListener('beforeunload', handleBeforeUnload)
      // Clear PHI data on component unmount (navigation to another page)
      handleBeforeUnload()
    }
  }, [])

  useEffect(() => {
    loadModelsForProvider()
  }, [llmProvider])

  // Save selected model to localStorage
  useEffect(() => {
    if (selectedModel) {
      localStorage.setItem('vaucda_selected_model', selectedModel)
    }
  }, [selectedModel])

  // ========== Data Loading ==========
  const loadInitialData = async () => {
    try {
      // Try loading from localStorage first (for persistence without authentication)
      const savedSettings = localStorage.getItem('vaucda_settings')
      let settings

      if (savedSettings) {
        const parsed = JSON.parse(savedSettings)
        settings = {
          ...await settingsApi.getSettings(),
          ...parsed  // Override API defaults with localStorage values
        }
      } else {
        settings = await settingsApi.getSettings()
      }

      setLlmProvider(settings.default_llm)
      setNoteType(settings.default_template || 'clinic_note')
      setUseRAG(settings.use_rag !== undefined ? settings.use_rag : true)
      setTemperature(settings.temperature !== undefined ? settings.temperature : 0.3)

      // If settings has a default_model, use it (but don't override localStorage selection)
      if (settings.default_model && !localStorage.getItem('vaucda_selected_model')) {
        setSelectedModel(settings.default_model)
      }
    } catch (error) {
      console.error('Error loading initial data:', error)
    }
  }

  const loadModelsForProvider = async () => {
    try {
      const providers = await llmApi.getProviders()
      const provider = providers.find(p => p.name.toLowerCase() === llmProvider)

      if (provider && provider.models) {
        const modelNames = provider.models.map(m => m.name)
        setAvailableModels(modelNames)

        // If no model selected, or saved model not available for this provider, use first model
        if (modelNames.length > 0) {
          if (!selectedModel || !modelNames.includes(selectedModel)) {
            setSelectedModel(modelNames[0])
          }
        }
      }
    } catch (error) {
      console.error('Error loading models:', error)
      setAvailableModels([])
    }
  }

  // ========== Ambient Listening Callbacks ==========
  const handleTranscription = (text: string) => {
    setAmbientTranscription(prev => (prev ? `${prev} ${text}` : text))
  }

  const handleEntitiesExtracted = (entities: ExtractedEntity[]) => {
    setExtractedEntities(prev => {
      const merged = [...prev]
      entities.forEach(entity => {
        const existingIndex = merged.findIndex(e => e.field === entity.field)
        if (existingIndex >= 0) {
          if (entity.confidence > merged[existingIndex].confidence) {
            merged[existingIndex] = entity
          }
        } else {
          merged.push(entity)
        }
      })
      return merged
    })
  }

  const handleClinicalInputUpdate = (fullText: string) => {
    setClinicalInput(prev => {
      const manual = prev.replace(ambientTranscription, '').trim()
      return manual ? `${manual}\n\n${fullText}` : fullText
    })
  }

  // ========== Stage 1: Generate Preliminary Note ==========
  const handleGenerateInitial = async () => {
    const combinedInput = [clinicalInput, ambientTranscription].filter(Boolean).join('\n\n')

    if (!combinedInput.trim()) {
      alert('Please enter clinical input or use ambient listening')
      return
    }

    if (!selectedModel) {
      alert('Please select a model')
      return
    }

    setIsGeneratingInitial(true)

    try {
      const request: InitialNoteRequest = {
        clinical_input: combinedInput,
        note_type: noteType as 'clinic_note' | 'consult' | 'urology_clinic',
        patient_name: patientName || undefined,
        ssn_last4: ssnLast4 || undefined,
        llm_provider: llmProvider,
        llm_model: selectedModel || undefined,
        temperature: temperature,
        use_rag: useRAG
      }

      // Debug logging
      console.log('Stage 1 Request:', {
        note_type: noteType,
        note_type_from_request: request.note_type,
        clinical_input_length: combinedInput.length,
        llm_provider: llmProvider,
        llm_model: selectedModel
      })

      const response: InitialNoteResponse = await notesApi.generateInitialNote(request)

      setPreliminaryNote(response.preliminary_note)
      setExtractedEntities(response.extracted_entities)
      setSuggestedCalculators(response.suggested_calculators)
      setStage1Metadata(response.metadata)

      // Auto-populate patient demographics from extracted entities
      const patientNameEntity = response.extracted_entities.find(e => e.field === 'patient_name')
      const ssnEntity = response.extracted_entities.find(e => e.field === 'ssn')

      if (patientNameEntity && patientNameEntity.value) {
        setPatientName(String(patientNameEntity.value))
      }
      if (ssnEntity && ssnEntity.value) {
        // Extract last 4 digits if full SSN was extracted
        const ssnValue = String(ssnEntity.value)
        const last4Match = ssnValue.match(/\d{4}$/)
        if (last4Match) {
          setSsnLast4(last4Match[0])
        }
      }

      // Auto-select high-confidence calculators
      const autoSelected = response.suggested_calculators
        .filter(s => s.auto_selected)
        .map(s => s.calculator_id)
      setSelectedCalculators(autoSelected)

      setCurrentStage('preliminary')
    } catch (error: any) {
      alert(`Error generating preliminary note: ${error.detail || error.message || 'Unknown error'}`)
      console.error('Stage 1 error:', error)
    } finally {
      setIsGeneratingInitial(false)
    }
  }

  // ========== Stage 2: Generate Final Note ==========
  const handleGenerateFinal = async () => {
    if (!preliminaryNote) {
      alert('Please generate preliminary note first')
      return
    }

    setIsGeneratingFinal(true)

    try {
      const combinedInput = [clinicalInput, ambientTranscription].filter(Boolean).join('\n\n')

      const request: FinalNoteRequest = {
        preliminary_note: preliminaryNote,
        clinical_input: combinedInput,
        selected_calculators: selectedCalculators,
        additional_inputs: additionalInputs,
        use_rag: useRAG,
        llm_provider: llmProvider,
        llm_model: selectedModel,
        temperature,
        note_type: noteType,
        patient_name: patientName || undefined,
        ssn_last4: ssnLast4 || undefined
      }

      const response: FinalNoteResponse = await notesApi.generateFinalNote(request)

      setFinalNote(response.final_note)
      setCalculatorResults(response.calculator_results)
      setRagSources(response.rag_sources)
      setStage2Metadata(response.metadata)

      setCurrentStage('final')
    } catch (error: any) {
      alert(`Error generating final note: ${error.detail || error.message || 'Unknown error'}`)
      console.error('Stage 2 error:', error)
    } finally {
      setIsGeneratingFinal(false)
    }
  }

  // ========== Stage 3: Generate Ambient-Augmented Note ==========
  const handleGenerateAmbientAugmented = async () => {
    if (!finalNote) {
      alert('Please generate Stage 2 note first')
      return
    }

    if (!ambientTranscription) {
      alert('No ambient transcription available. Please use ambient listening first.')
      return
    }

    setIsGeneratingAmbient(true)

    try {
      // Call Stage 3 endpoint with ambient augmentation
      const response = await fetch(`${import.meta.env.VITE_API_BASE_URL}/api/v1/notes/ambient-augment`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${localStorage.getItem('access_token')}`
        },
        body: JSON.stringify({
          stage2_note: finalNote,
          transcription: ambientTranscription,
          speaker_map: {} // TODO: Get from ambient listening component
        })
      })

      if (!response.ok) {
        throw new Error('Stage 3 generation failed')
      }

      const data = await response.json()

      setAmbientAugmentedNote(data.final_note)
      setStage3Metadata(data.metadata)
      setCurrentStage('ambient')

      alert('Ambient-augmented note generated successfully!')
    } catch (error: any) {
      alert(`Error generating ambient-augmented note: ${error.message || 'Unknown error'}`)
      console.error('Stage 3 error:', error)
    } finally {
      setIsGeneratingAmbient(false)
    }
  }

  // ========== Calculator Management ==========
  const handleCalculatorToggle = (calculatorId: string) => {
    setSelectedCalculators(prev =>
      prev.includes(calculatorId)
        ? prev.filter(id => id !== calculatorId)
        : [...prev, calculatorId]
    )
  }

  const handleAdditionalInputChange = (field: string, value: any) => {
    setAdditionalInputs(prev => ({ ...prev, [field]: value }))
  }

  // ========== Utility Functions ==========
  const handleCopy = async (text: string) => {
    try {
      // Try modern Clipboard API first (requires HTTPS or localhost)
      if (navigator.clipboard && navigator.clipboard.writeText) {
        await navigator.clipboard.writeText(text)
        alert('Copied to clipboard')
      } else {
        // Fallback for HTTP (non-secure contexts) like network access
        copyToClipboardFallback(text)
      }
    } catch (err) {
      // If modern API fails, use fallback
      copyToClipboardFallback(text)
    }
  }

  // Fallback copy method for non-HTTPS contexts
  const copyToClipboardFallback = (text: string) => {
    const textArea = document.createElement('textarea')
    textArea.value = text
    textArea.style.position = 'fixed'
    textArea.style.left = '-999999px'
    textArea.style.top = '-999999px'
    document.body.appendChild(textArea)
    textArea.focus()
    textArea.select()
    try {
      document.execCommand('copy')
      textArea.remove()
      alert('Copied to clipboard')
    } catch (err) {
      textArea.remove()
      alert('Failed to copy. Please copy manually.')
    }
  }

  const handleDownload = (text: string, filename: string) => {
    const blob = new Blob([text], { type: 'text/plain' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = filename
    a.click()
    URL.revokeObjectURL(url)
  }

  const handleRestart = () => {
    if (confirm('Start a new note? This will clear all current progress.')) {
      // Clear all clinical input and context (CRITICAL for patient data separation)
      setClinicalInput('')
      setAmbientTranscription('')

      // Clear all generated notes
      setPreliminaryNote('')
      setFinalNote('')
      setAmbientAugmentedNote('')
      setIsEditingStage1(false)
      setIsEditingStage2(false)

      // Clear all extracted data and suggestions
      setExtractedEntities([])
      setSuggestedCalculators([])
      setSelectedCalculators([])
      setCalculatorResults([])
      setRagSources([])
      setAdditionalInputs({})

      // Clear Stage 3 state
      setIsAmbientActive(false)

      // Clear metadata
      setStage1Metadata(null)
      setStage2Metadata(null)
      setStage3Metadata(null)

      // Clear localStorage to prevent persistence
      localStorage.removeItem('vaucda_clinical_input')

      // Reset to input stage
      setCurrentStage('input')
    }
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold text-gray-900 dark:text-white">
            Clinical Note Generation
          </h1>
          <p className="text-sm text-gray-600 dark:text-gray-400 mt-1">
            Two-stage workflow with ambient listening and intelligent calculator suggestions
          </p>
        </div>

        {currentStage !== 'input' && (
          <Button variant="outline" onClick={handleRestart}>
            Start New Note
          </Button>
        )}
      </div>

      {/* Workflow Progress Indicator */}
      <Card className="bg-gradient-to-r from-primary/10 to-medical/10 border-primary/20">
        <div className="flex items-center justify-center space-x-4 p-2">
          <div className={`flex items-center space-x-2 ${currentStage === 'input' ? 'text-primary font-semibold' : 'text-gray-500'}`}>
            <div className={`w-8 h-8 rounded-full flex items-center justify-center border-2 ${currentStage === 'input' ? 'border-primary bg-primary text-white' : 'border-gray-300 bg-gray-100'}`}>
              1
            </div>
            <span>Clinical Data</span>
          </div>

          <FiChevronRight className="text-gray-400" />

          <div className={`flex items-center space-x-2 ${currentStage === 'preliminary' ? 'text-primary font-semibold' : 'text-gray-500'}`}>
            <div className={`w-8 h-8 rounded-full flex items-center justify-center border-2 ${currentStage === 'preliminary' ? 'border-primary bg-primary text-white' : currentStage === 'final' ? 'border-success bg-success text-white' : 'border-gray-300 bg-gray-100'}`}>
              {currentStage === 'final' ? <FiCheckCircle /> : '2'}
            </div>
            <span>Preliminary Note</span>
          </div>

          <FiChevronRight className="text-gray-400" />

          <div className={`flex items-center space-x-2 ${currentStage === 'final' ? 'text-success font-semibold' : 'text-gray-500'}`}>
            <div className={`w-8 h-8 rounded-full flex items-center justify-center border-2 ${currentStage === 'final' ? 'border-success bg-success text-white' : 'border-gray-300 bg-gray-100'}`}>
              {currentStage === 'final' ? <FiCheckCircle /> : '3'}
            </div>
            <span>Final Note</span>
          </div>
        </div>
      </Card>

      <div className="max-w-7xl mx-auto">
        {/* Main Content Area - Full Width */}
        <div className="space-y-6">
          {/* STAGE 1: Clinical Data Collection */}
          {currentStage === 'input' && (
            <>
              {/* Ambient Listening */}
              <AmbientListening
                onTranscription={handleTranscription}
                onEntitiesExtracted={handleEntitiesExtracted}
                onClinicalInputUpdate={handleClinicalInputUpdate}
              />

              {/* Clinical Input */}
              <Card title="Clinical Input" description="Enter or paste clinical data (labs, imaging, history)">
                <Textarea
                  value={clinicalInput}
                  onChange={(e) => setClinicalInput(e.target.value)}
                  placeholder="Enter clinical information here...&#10;&#10;Example:&#10;72yo M with PSA 8.5 ng/mL&#10;Gleason 3+4=7 on biopsy&#10;4/12 cores positive&#10;Clinical stage T1c&#10;&#10;Discussed treatment options including active surveillance, prostatectomy, and radiation. Patient prefers surgery. Counseled regarding surgical risks, incontinence, erectile dysfunction. Reviewed CAPRA score and recurrence risk. Patient wishes to proceed with robotic-assisted laparoscopic prostatectomy."
                  className="min-h-[300px] font-mono text-sm"
                  showCharCount
                  maxCharCount={MAX_CHAR_LIMIT}
                  maxLength={MAX_CHAR_LIMIT}
                />

                <div className="mt-4 flex justify-between items-center">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => {
                      setClinicalInput('')
                      setAmbientTranscription('')
                      localStorage.removeItem('vaucda_clinical_input')
                    }}
                  >
                    Clear Input
                  </Button>

                  <div className="flex items-center gap-3">
                    <Select
                      label="Note Type"
                      value={noteType}
                      onChange={(e) => setNoteType(e.target.value)}
                      options={NOTE_TYPES}
                      className="w-48"
                    />
                    <Button
                      variant="medical"
                      size="lg"
                      icon={<FiPlay />}
                      onClick={handleGenerateInitial}
                      isLoading={isGeneratingInitial}
                      disabled={(!clinicalInput.trim() && !ambientTranscription) || !selectedModel || isGeneratingInitial}
                    >
                      {isGeneratingInitial ? 'Generating...' : 'Generate Note'}
                    </Button>
                  </div>
                </div>
              </Card>
            </>
          )}

          {/* STAGE 2: Preliminary Note & Calculator Suggestions */}
          {currentStage === 'preliminary' && (
            <>
              {/* Preliminary Note Display */}
              <Card
                title="Preliminary Clinical Note"
                description="Organized clinical data (editable before generating final note)"
                footer={
                  <div className="flex gap-2">
                    <Button
                      variant="outline"
                      size="sm"
                      icon={<FiEdit />}
                      onClick={() => setIsEditingStage1(true)}
                    >
                      Edit
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      icon={<FiCopy />}
                      onClick={() => handleCopy(preliminaryNote)}
                    >
                      Copy
                    </Button>
                  </div>
                }
              >
                <div className="prose prose-sm dark:prose-invert max-w-none">
                  <ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeHighlight]}>
                    {preliminaryNote}
                  </ReactMarkdown>
                </div>

                {stage1Metadata && (
                  <div className="mt-4 pt-4 border-t border-gray-200 dark:border-gray-700 text-xs text-gray-600 dark:text-gray-400 grid grid-cols-3 gap-2">
                    <div>Time: {stage1Metadata.generation_time_seconds}s</div>
                    <div>Entities: {stage1Metadata.entities_extracted}</div>
                    <div>Suggestions: {stage1Metadata.calculators_suggested}</div>
                  </div>
                )}
              </Card>

              {/* Extracted Entities */}
              {extractedEntities.length > 0 && (
                <Card title="Extracted Clinical Data" description={`${extractedEntities.length} clinical entities detected`}>
                  <div className="grid grid-cols-3 gap-2">
                    {extractedEntities.map((entity, idx) => (
                      <div key={idx} className="p-2 bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 rounded">
                        <div className="text-xs font-medium text-gray-600 dark:text-gray-400">
                          {entity.field.replace(/_/g, ' ').toUpperCase()}
                        </div>
                        <div className="text-sm font-semibold text-gray-900 dark:text-white">
                          {typeof entity.value === 'number' ? entity.value.toFixed(2) : entity.value}
                        </div>
                        <div className="text-xs text-gray-500 dark:text-gray-400">
                          {Math.round(entity.confidence * 100)}% confidence
                        </div>
                      </div>
                    ))}
                  </div>
                </Card>
              )}

              {/* Calculator Suggestions */}
              <CalculatorSuggestionPanel
                suggestions={suggestedCalculators}
                extractedEntities={extractedEntities}
                selectedCalculators={selectedCalculators}
                onCalculatorToggle={handleCalculatorToggle}
                onAdditionalInputChange={handleAdditionalInputChange}
                additionalInputs={additionalInputs}
              />

              {/* Patient information is now auto-extracted from clinical input */}

              {/* Generate Final Note Button */}
              <Card className="bg-gradient-to-r from-medical/10 to-primary/10 border-medical/30">
                <div className="flex items-center justify-between p-4">
                  <div>
                    <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-1">
                      Ready for Final Note?
                    </h3>
                    <p className="text-sm text-gray-600 dark:text-gray-400">
                      {selectedCalculators.length} calculator{selectedCalculators.length !== 1 ? 's' : ''} selected • RAG {useRAG ? 'enabled' : 'disabled'}
                    </p>
                  </div>
                  <Button
                    variant="medical"
                    size="lg"
                    icon={<FiPlay />}
                    onClick={handleGenerateFinal}
                    isLoading={isGeneratingFinal}
                    disabled={isGeneratingFinal}
                  >
                    {isGeneratingFinal ? 'Generating...' : 'Generate Final Note'}
                  </Button>
                </div>
              </Card>
            </>
          )}

          {/* STAGE 3: Final Note with Assessment & Plan */}
          {currentStage === 'final' && (
            <>
              {/* Final Note Display */}
              <Card
                title="Final Clinical Note"
                description="Complete note with Assessment & Plan"
                footer={
                  <div className="flex gap-2">
                    <Button
                      variant="outline"
                      size="sm"
                      icon={<FiEdit />}
                      onClick={() => setIsEditingStage2(true)}
                    >
                      Edit
                    </Button>
                    <Button variant="outline" size="sm" icon={<FiCopy />} onClick={() => handleCopy(finalNote)}>
                      Copy
                    </Button>
                    <Button variant="outline" size="sm" icon={<FiDownload />} onClick={() => handleDownload(finalNote, `clinical-note-${new Date().toISOString().split('T')[0]}.txt`)}>
                      Download
                    </Button>
                    {/* HIPAA COMPLIANCE: Removed "Save Draft" button
                        Patient data should NOT be saved to localStorage
                        Future: Implement secure server-side draft storage */}
                  </div>
                }
              >
                <div className="prose prose-sm dark:prose-invert max-w-none">
                  <ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeHighlight]}>
                    {finalNote}
                  </ReactMarkdown>
                </div>

                {stage2Metadata && (
                  <div className="mt-4 pt-4 border-t border-gray-200 dark:border-gray-700 text-xs text-gray-600 dark:text-gray-400 grid grid-cols-4 gap-2">
                    <div>Time: {stage2Metadata.generation_time_seconds}s</div>
                    <div>Calculators: {stage2Metadata.calculators_executed}</div>
                    <div>RAG Sources: {stage2Metadata.rag_sources_count}</div>
                    <div>RAG: {stage2Metadata.rag_enabled ? 'Enabled' : 'Disabled'}</div>
                  </div>
                )}
              </Card>

              {/* Calculator Results */}
              {calculatorResults.length > 0 && (
                <Card title="Calculator Results" description={`${calculatorResults.length} clinical calculator${calculatorResults.length !== 1 ? 's' : ''} executed`}>
                  <div className="space-y-3">
                    {calculatorResults.map((result, idx) => (
                      <div key={idx} className="p-4 border border-primary/20 bg-primary/5 rounded-lg">
                        <h4 className="font-semibold text-gray-900 dark:text-white mb-2">
                          {result.calculator_name}
                        </h4>
                        <p className="text-sm text-gray-700 dark:text-gray-300 mb-2">
                          {result.interpretation}
                        </p>
                        {result.recommendations.length > 0 && (
                          <ul className="text-sm text-gray-600 dark:text-gray-400 space-y-1">
                            {result.recommendations.map((rec: string, ridx: number) => (
                              <li key={ridx}>• {rec}</li>
                            ))}
                          </ul>
                        )}
                      </div>
                    ))}
                  </div>
                </Card>
              )}

              {/* RAG Sources */}
              {ragSources.length > 0 && (
                <Card title="Evidence Sources" description={`${ragSources.length} evidence-based guideline${ragSources.length !== 1 ? 's' : ''} referenced`}>
                  <div className="space-y-2">
                    {ragSources.map((source, idx) => (
                      <div key={idx} className="p-3 bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded">
                        <div className="font-medium text-sm text-gray-900 dark:text-white">
                          {source.title}
                        </div>
                        <div className="text-xs text-gray-600 dark:text-gray-400">
                          Source: {source.source}
                        </div>
                      </div>
                    ))}
                  </div>
                </Card>
              )}

              {/* Ambient Listening Stage 3 Option */}
              {ambientTranscription && (
                <Card className="bg-gradient-to-r from-purple-500/10 to-primary/10 border-purple-500/30">
                  <div className="flex items-center justify-between p-4">
                    <div>
                      <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-1">
                        Ready for Ambient-Augmented Note?
                      </h3>
                      <p className="text-sm text-gray-600 dark:text-gray-400">
                        Merge ambient transcription into final note with section-aware intelligence
                      </p>
                    </div>
                    <Button
                      variant="primary"
                      size="lg"
                      icon={<FiPlay />}
                      onClick={handleGenerateAmbientAugmented}
                      isLoading={isGeneratingAmbient}
                      disabled={isGeneratingAmbient}
                    >
                      {isGeneratingAmbient ? 'Merging...' : 'Generate Stage 3 Note'}
                    </Button>
                  </div>
                </Card>
              )}
            </>
          )}

          {/* STAGE 3: Ambient-Augmented Final Note */}
          {currentStage === 'ambient' && (
            <>
              {/* Ambient-Augmented Note Display */}
              <Card
                title="Ambient-Augmented Clinical Note (Stage 3)"
                description="Final note with intelligent section-aware transcription merging"
                footer={
                  <div className="flex gap-2">
                    <Button variant="outline" size="sm" icon={<FiCopy />} onClick={() => handleCopy(ambientAugmentedNote)}>
                      Copy
                    </Button>
                    <Button variant="outline" size="sm" icon={<FiDownload />} onClick={() => handleDownload(ambientAugmentedNote, `clinical-note-ambient-${new Date().toISOString().split('T')[0]}.txt`)}>
                      Download
                    </Button>
                    {/* HIPAA COMPLIANCE: Removed "Save Draft" button
                        Patient data should NOT be saved to localStorage
                        Future: Implement secure server-side draft storage */}
                  </div>
                }
              >
                <div className="prose prose-sm dark:prose-invert max-w-none">
                  <ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeHighlight]}>
                    {ambientAugmentedNote}
                  </ReactMarkdown>
                </div>

                {stage3Metadata && (
                  <div className="mt-4 pt-4 border-t border-gray-200 dark:border-gray-700 text-xs text-gray-600 dark:text-gray-400 grid grid-cols-3 gap-2">
                    <div>Workflow: {stage3Metadata.workflow}</div>
                    <div>Transcription: {stage3Metadata.transcription_length} chars</div>
                    <div>Segments: {stage3Metadata.segments_merged}</div>
                  </div>
                )}
              </Card>

              {/* Show Original Stage 2 Note for Comparison */}
              <Card
                title="Original Stage 2 Note (Before Ambient Merging)"
                description="Compare with ambient-augmented version above"
              >
                <div className="prose prose-sm dark:prose-invert max-w-none opacity-70">
                  <ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeHighlight]}>
                    {finalNote}
                  </ReactMarkdown>
                </div>
              </Card>
            </>
          )}
        </div>
      </div>

      {/* NoteEditor Modals */}
      {isEditingStage1 && (
        <NoteEditor
          note={preliminaryNote}
          noteType="Stage 1"
          onSave={(editedNote) => {
            setPreliminaryNote(editedNote)
            setIsEditingStage1(false)
          }}
          onClose={() => setIsEditingStage1(false)}
        />
      )}

      {isEditingStage2 && (
        <NoteEditor
          note={finalNote}
          noteType="Stage 2"
          onSave={(editedNote) => {
            setFinalNote(editedNote)
            setIsEditingStage2(false)
          }}
          onClose={() => setIsEditingStage2(false)}
        />
      )}
    </div>
  )
}
