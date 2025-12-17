import React, { useState, useEffect } from 'react'
import { Card } from '@/components/common/Card'
import { Button } from '@/components/common/Button'
import { FiCheckCircle, FiAlertTriangle, FiInfo, FiChevronDown, FiChevronUp, FiCheck } from 'react-icons/fi'
import type { CalculatorSuggestion, ExtractedEntity } from '@/types/api.types'
import { calculatorsApi } from '@/api'
import clsx from 'clsx'

interface InputMetadata {
  field_name: string
  display_name: string
  input_type: 'numeric' | 'enum' | 'boolean' | 'text' | 'date'
  required: boolean
  description: string
  unit?: string
  min_value?: number
  max_value?: number
  allowed_values?: any[]
  default_value?: any
  example?: string
  help_text?: string
}

interface CalculatorSuggestionPanelProps {
  suggestions: CalculatorSuggestion[]
  extractedEntities: ExtractedEntity[]
  selectedCalculators: string[]
  onCalculatorToggle: (calculatorId: string) => void
  onAdditionalInputChange: (field: string, value: any) => void
  additionalInputs: Record<string, any>
}

export const CalculatorSuggestionPanel: React.FC<CalculatorSuggestionPanelProps> = ({
  suggestions,
  extractedEntities,
  selectedCalculators,
  onCalculatorToggle,
  onAdditionalInputChange,
  additionalInputs
}) => {
  const [expandedCalculators, setExpandedCalculators] = useState<Set<string>>(new Set())
  const [inputSchemas, setInputSchemas] = useState<Record<string, InputMetadata[]>>({})

  const toggleExpanded = async (calculatorId: string) => {
    console.log(`[CalculatorPanel] toggleExpanded called for: ${calculatorId}`)

    setExpandedCalculators(prev => {
      const next = new Set(prev)
      if (next.has(calculatorId)) {
        console.log(`[CalculatorPanel] Collapsing ${calculatorId}`)
        next.delete(calculatorId)
      } else {
        console.log(`[CalculatorPanel] Expanding ${calculatorId}`)
        next.add(calculatorId)

        // Fetch input schema when expanding
        if (!inputSchemas[calculatorId]) {
          console.log(`[CalculatorPanel] Schema not cached, fetching for ${calculatorId}`)
          fetchInputSchema(calculatorId)
        } else {
          console.log(`[CalculatorPanel] Schema already cached for ${calculatorId}`)
        }
      }
      return next
    })
  }

  const fetchInputSchema = async (calculatorId: string) => {
    try {
      console.log(`[CalculatorPanel] Fetching input schema for: ${calculatorId}`)

      const data = await calculatorsApi.getCalculatorInputSchema(calculatorId)
      console.log(`[CalculatorPanel] Schema received:`, data)
      console.log(`[CalculatorPanel] Input schema fields: ${data.input_schema?.length || 0}`)

      setInputSchemas(prev => {
        const updated = {
          ...prev,
          [calculatorId]: data.input_schema
        }
        console.log(`[CalculatorPanel] Updated inputSchemas state for ${calculatorId}`)
        return updated
      })
    } catch (error: any) {
      console.error('[CalculatorPanel] Error fetching input schema:', error)
      console.error('[CalculatorPanel] Error details:', {
        message: error?.message || error?.detail || 'Unknown error',
        detail: error?.detail
      })
    }
  }

  const renderInputField = (
    calculatorId: string,
    fieldName: string,
    inputMeta: InputMetadata
  ) => {
    const value = additionalInputs[fieldName]
    const hasValue = value !== undefined && value !== null && value !== ''

    // Input wrapper with visual feedback
    const inputWrapperClass = clsx(
      'relative flex items-center space-x-2',
      hasValue && 'has-value'
    )

    const handleChange = (newValue: any) => {
      // Convert boolean string values to actual booleans
      if (inputMeta.input_type === 'boolean') {
        onAdditionalInputChange(fieldName, newValue === 'true' || newValue === true)
      } else if (inputMeta.input_type === 'numeric') {
        onAdditionalInputChange(fieldName, parseFloat(newValue) || 0)
      } else {
        onAdditionalInputChange(fieldName, newValue)
      }
    }

    // Render based on input type
    switch (inputMeta.input_type) {
      case 'boolean':
        return (
          <div key={fieldName} className={inputWrapperClass}>
            <label className="text-sm text-gray-700 dark:text-gray-300 flex-1">
              {inputMeta.display_name}:
            </label>
            <div className="flex items-center space-x-2">
              <select
                value={value === true ? 'true' : value === false ? 'false' : ''}
                onChange={(e) => handleChange(e.target.value)}
                className={clsx(
                  'px-3 py-1.5 border rounded-md text-sm focus:ring-2 focus:ring-primary focus:border-transparent',
                  hasValue
                    ? 'border-success bg-success/5 dark:bg-success/10'
                    : 'border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800',
                  'text-gray-900 dark:text-white'
                )}
              >
                <option value="">Select...</option>
                <option value="true">Yes</option>
                <option value="false">No</option>
              </select>
              {hasValue && (
                <FiCheck className="h-4 w-4 text-success flex-shrink-0" />
              )}
            </div>
          </div>
        )

      case 'numeric':
        return (
          <div key={fieldName} className={inputWrapperClass}>
            <label className="text-sm text-gray-700 dark:text-gray-300 flex-1">
              {inputMeta.display_name}{inputMeta.unit ? ` (${inputMeta.unit})` : ''}:
            </label>
            <div className="flex items-center space-x-2">
              <input
                type="number"
                placeholder={inputMeta.example || `Enter ${inputMeta.display_name.toLowerCase()}`}
                value={value || ''}
                onChange={(e) => handleChange(e.target.value)}
                min={inputMeta.min_value}
                max={inputMeta.max_value}
                step="any"
                className={clsx(
                  'px-3 py-1.5 border rounded-md text-sm focus:ring-2 focus:ring-primary focus:border-transparent w-32',
                  hasValue
                    ? 'border-success bg-success/5 dark:bg-success/10'
                    : 'border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800',
                  'text-gray-900 dark:text-white'
                )}
              />
              {hasValue && (
                <FiCheck className="h-4 w-4 text-success flex-shrink-0" />
              )}
            </div>
          </div>
        )

      case 'enum':
        return (
          <div key={fieldName} className={inputWrapperClass}>
            <label className="text-sm text-gray-700 dark:text-gray-300 flex-1">
              {inputMeta.display_name}:
            </label>
            <div className="flex items-center space-x-2">
              <select
                value={value || ''}
                onChange={(e) => handleChange(e.target.value)}
                className={clsx(
                  'px-3 py-1.5 border rounded-md text-sm focus:ring-2 focus:ring-primary focus:border-transparent',
                  hasValue
                    ? 'border-success bg-success/5 dark:bg-success/10'
                    : 'border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800',
                  'text-gray-900 dark:text-white'
                )}
              >
                <option value="">Select...</option>
                {inputMeta.allowed_values?.map((val) => (
                  <option key={val} value={val}>
                    {val}
                  </option>
                ))}
              </select>
              {hasValue && (
                <FiCheck className="h-4 w-4 text-success flex-shrink-0" />
              )}
            </div>
          </div>
        )

      case 'text':
      default:
        return (
          <div key={fieldName} className={inputWrapperClass}>
            <label className="text-sm text-gray-700 dark:text-gray-300 flex-1">
              {inputMeta.display_name}:
            </label>
            <div className="flex items-center space-x-2">
              <input
                type="text"
                placeholder={inputMeta.example || `Enter ${inputMeta.display_name.toLowerCase()}`}
                value={value || ''}
                onChange={(e) => handleChange(e.target.value)}
                className={clsx(
                  'px-3 py-1.5 border rounded-md text-sm focus:ring-2 focus:ring-primary focus:border-transparent flex-1',
                  hasValue
                    ? 'border-success bg-success/5 dark:bg-success/10'
                    : 'border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800',
                  'text-gray-900 dark:text-white'
                )}
              />
              {hasValue && (
                <FiCheck className="h-4 w-4 text-success flex-shrink-0" />
              )}
            </div>
          </div>
        )
    }
  }

  const getConfidenceBadge = (confidence: 'high' | 'medium' | 'low') => {
    const styles = {
      high: 'bg-success/10 text-success border-success',
      medium: 'bg-warning/10 text-warning border-warning',
      low: 'bg-gray-100 text-gray-600 border-gray-300 dark:bg-gray-800 dark:text-gray-400 dark:border-gray-600'
    }

    const icons = {
      high: <FiCheckCircle className="h-3 w-3" />,
      medium: <FiAlertTriangle className="h-3 w-3" />,
      low: <FiInfo className="h-3 w-3" />
    }

    return (
      <span className={clsx(
        'inline-flex items-center space-x-1 px-2 py-1 text-xs font-medium rounded border',
        styles[confidence]
      )}>
        {icons[confidence]}
        <span>{confidence.toUpperCase()}</span>
      </span>
    )
  }

  const getCategoryColor = (category: string) => {
    const colors: Record<string, string> = {
      prostate: 'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-300',
      kidney: 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-300',
      bladder: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-300',
      voiding: 'bg-purple-100 text-purple-800 dark:bg-purple-900/30 dark:text-purple-300',
      surgical: 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-300'
    }
    return colors[category] || 'bg-gray-100 text-gray-800 dark:bg-gray-800 dark:text-gray-300'
  }

  if (suggestions.length === 0) {
    return (
      <Card className="p-6">
        <div className="text-center">
          <FiInfo className="h-12 w-12 text-gray-400 mx-auto mb-3" />
          <h3 className="text-lg font-medium text-gray-900 dark:text-white mb-2">
            No Calculator Suggestions
          </h3>
          <p className="text-sm text-gray-600 dark:text-gray-400">
            Not enough clinical data detected to suggest calculators.
            <br />
            Continue with ambient listening or paste additional clinical data.
          </p>
        </div>
      </Card>
    )
  }

  const highConfidence = suggestions.filter(s => s.confidence === 'high')
  const mediumConfidence = suggestions.filter(s => s.confidence === 'medium')
  const lowConfidence = suggestions.filter(s => s.confidence === 'low')

  return (
    <Card className="p-6">
      <div className="space-y-4">
        {/* Header */}
        <div>
          <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-1">
            Suggested Calculators
          </h3>
          <p className="text-sm text-gray-600 dark:text-gray-400">
            Based on {extractedEntities.length} extracted clinical {extractedEntities.length === 1 ? 'entity' : 'entities'}
          </p>
        </div>

        {/* Summary Stats */}
        <div className="grid grid-cols-3 gap-3">
          <div className="p-3 bg-success/10 border border-success rounded-lg">
            <div className="text-2xl font-bold text-success">{highConfidence.length}</div>
            <div className="text-xs text-gray-600 dark:text-gray-400">High Confidence</div>
          </div>
          <div className="p-3 bg-warning/10 border border-warning rounded-lg">
            <div className="text-2xl font-bold text-warning">{mediumConfidence.length}</div>
            <div className="text-xs text-gray-600 dark:text-gray-400">Medium Confidence</div>
          </div>
          <div className="p-3 bg-gray-100 dark:bg-gray-800 border border-gray-300 dark:border-gray-600 rounded-lg">
            <div className="text-2xl font-bold text-gray-600 dark:text-gray-400">{lowConfidence.length}</div>
            <div className="text-xs text-gray-600 dark:text-gray-400">Low Confidence</div>
          </div>
        </div>

        {/* Calculator List */}
        <div className="space-y-2">
          {suggestions.map(suggestion => {
            const isSelected = selectedCalculators.includes(suggestion.calculator_id)
            const isExpanded = expandedCalculators.has(suggestion.calculator_id)

            return (
              <div
                key={suggestion.calculator_id}
                className={clsx(
                  'border rounded-lg transition-all',
                  isSelected
                    ? 'border-primary bg-primary/5'
                    : 'border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800'
                )}
              >
                {/* Calculator Header */}
                <div className="p-4">
                  <div className="flex items-start space-x-3">
                    {/* Checkbox */}
                    <input
                      type="checkbox"
                      checked={isSelected}
                      onChange={() => onCalculatorToggle(suggestion.calculator_id)}
                      className="mt-1 h-4 w-4 text-primary border-gray-300 rounded focus:ring-primary"
                    />

                    {/* Calculator Info */}
                    <div className="flex-1 min-w-0">
                      <div className="flex items-start justify-between">
                        <div className="flex-1">
                          <div className="flex items-center space-x-2 mb-1">
                            <h4 className="text-base font-semibold text-gray-900 dark:text-white">
                              {suggestion.calculator_name}
                            </h4>
                            <span className={clsx(
                              'px-2 py-0.5 text-xs font-medium rounded',
                              getCategoryColor(suggestion.category)
                            )}>
                              {suggestion.category}
                            </span>
                          </div>
                          <p className="text-sm text-gray-600 dark:text-gray-400 mb-2">
                            {suggestion.reason}
                          </p>
                        </div>

                        <div className="flex items-center space-x-2 ml-3">
                          {getConfidenceBadge(suggestion.confidence)}
                          <button
                            onClick={() => toggleExpanded(suggestion.calculator_id)}
                            className="p-1 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300"
                          >
                            {isExpanded ? <FiChevronUp /> : <FiChevronDown />}
                          </button>
                        </div>
                      </div>

                      {/* Quick Stats */}
                      <div className="flex items-center space-x-4 text-xs text-gray-500 dark:text-gray-400">
                        <span>
                          ✓ {suggestion.available_inputs.length}/{suggestion.required_inputs.length} inputs
                        </span>
                        {suggestion.missing_inputs.length > 0 && (
                          <span className="text-warning">
                            ⚠ {suggestion.missing_inputs.length} missing
                          </span>
                        )}
                      </div>
                    </div>
                  </div>

                  {/* Expanded Details */}
                  {isExpanded && (
                    <div className="mt-4 pt-4 border-t border-gray-200 dark:border-gray-700 space-y-3">
                      {/* Detected Values */}
                      {suggestion.available_inputs.length > 0 && (
                        <div>
                          <h5 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                            Detected Values:
                          </h5>
                          <div className="grid grid-cols-2 gap-2">
                            {suggestion.available_inputs.map(input => (
                              <div
                                key={input}
                                className="p-2 bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 rounded text-sm"
                              >
                                <div className="font-medium text-gray-700 dark:text-gray-300">
                                  {input.replace(/_/g, ' ')}
                                </div>
                                <div className="text-gray-900 dark:text-white font-semibold">
                                  {suggestion.detected_entities[input] !== undefined
                                    ? String(suggestion.detected_entities[input])
                                    : '-'}
                                </div>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}

                      {/* Missing Inputs */}
                      {suggestion.missing_inputs.length > 0 && (
                        <div>
                          <h5 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                            Missing Inputs (manual entry required):
                          </h5>
                          <div className="space-y-3">
                            {(() => {
                              const hasSchema = inputSchemas[suggestion.calculator_id]
                              console.log(`[CalculatorPanel] Rendering missing inputs for ${suggestion.calculator_id}:`, {
                                hasSchema: !!hasSchema,
                                schemaFieldCount: hasSchema ? hasSchema.length : 0,
                                missingInputs: suggestion.missing_inputs
                              })
                              return hasSchema
                            })() ? (
                              // Use schema-based rendering with appropriate input types
                              suggestion.missing_inputs.map(fieldName => {
                                const inputMeta = inputSchemas[suggestion.calculator_id].find(
                                  meta => meta.field_name === fieldName
                                )
                                console.log(`[CalculatorPanel] Rendering field ${fieldName}:`, {
                                  found: !!inputMeta,
                                  type: inputMeta?.input_type
                                })
                                if (inputMeta) {
                                  return renderInputField(suggestion.calculator_id, fieldName, inputMeta)
                                }
                                // Fallback to simple text input if schema not found
                                return (
                                  <div key={fieldName} className="flex items-center space-x-2">
                                    <label className="text-sm text-gray-700 dark:text-gray-300 flex-1">
                                      {fieldName.replace(/_/g, ' ')}:
                                    </label>
                                    <input
                                      type="text"
                                      placeholder="Enter value"
                                      value={additionalInputs[fieldName] || ''}
                                      onChange={(e) => onAdditionalInputChange(fieldName, e.target.value)}
                                      className="px-3 py-1.5 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-800 text-gray-900 dark:text-white text-sm focus:ring-2 focus:ring-primary focus:border-transparent"
                                    />
                                  </div>
                                )
                              })
                            ) : (
                              // Loading state while schema is being fetched
                              <div className="text-xs text-gray-500 dark:text-gray-400 italic">
                                Loading input fields...
                              </div>
                            )}
                          </div>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              </div>
            )
          })}
        </div>

        {/* Info Footer */}
        <div className="p-3 bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg">
          <p className="text-sm text-blue-800 dark:text-blue-300">
            <strong>Tip:</strong> High-confidence calculators are auto-selected. Review medium/low confidence suggestions and provide missing inputs if needed.
          </p>
        </div>
      </div>
    </Card>
  )
}
