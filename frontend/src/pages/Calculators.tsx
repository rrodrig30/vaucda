import React, { useState, useEffect } from 'react'
import { Card } from '@/components/common/Card'
import { Button } from '@/components/common/Button'
import { Input } from '@/components/common/Input'
import { Select } from '@/components/common/Select'
import { Modal } from '@/components/common/Modal'
import { calculatorsApi } from '@/api'
import { FiSearch, FiX } from 'react-icons/fi'
import type {
  Calculator,
  CalculatorCategory,
  CalculatorExecutionResponse,
  CalculatorInput
} from '@/types/api.types'

export const Calculators: React.FC = () => {
  const [calculatorsByCategory, setCalculatorsByCategory] = useState<CalculatorCategory>({})
  const [allCalculators, setAllCalculators] = useState<Calculator[]>([])
  const [filteredCalculators, setFilteredCalculators] = useState<Calculator[]>([])
  const [searchTerm, setSearchTerm] = useState('')
  const [selectedCategory, setSelectedCategory] = useState<string>('all')
  const [isLoading, setIsLoading] = useState(true)

  const [selectedCalculator, setSelectedCalculator] = useState<Calculator | null>(null)
  const [isModalOpen, setIsModalOpen] = useState(false)
  const [calculatorInputs, setCalculatorInputs] = useState<Record<string, any>>({})
  const [calculatorResult, setCalculatorResult] = useState<CalculatorExecutionResponse | null>(null)
  const [isCalculating, setIsCalculating] = useState(false)
  const [calculationError, setCalculationError] = useState<string>('')

  useEffect(() => {
    loadCalculators()
  }, [])

  useEffect(() => {
    filterCalculators()
  }, [searchTerm, selectedCategory, allCalculators])

  const loadCalculators = async () => {
    try {
      setIsLoading(true)
      const response = await calculatorsApi.getAllCalculators()

      // Defensive check: ensure response is valid
      if (!response || typeof response !== 'object') {
        console.error('Invalid calculator data received:', response)
        setCalculatorsByCategory({})
        setAllCalculators([])
        setFilteredCalculators([])
        return
      }

      // Extract calculators from response
      const data = response.calculators || response

      setCalculatorsByCategory(data)

      const flatCalculators: Calculator[] = []
      Object.entries(data).forEach(([, calcs]) => {
        if (Array.isArray(calcs)) {
          flatCalculators.push(...(calcs as Calculator[]))
        }
      })
      setAllCalculators(flatCalculators)
      setFilteredCalculators(flatCalculators)
    } catch (error) {
      console.error('Error loading calculators:', error)
      // Ensure state is set to valid defaults on error
      setCalculatorsByCategory({})
      setAllCalculators([])
      setFilteredCalculators([])
      alert('Failed to load calculators. Please refresh the page.')
    } finally {
      setIsLoading(false)
    }
  }

  const filterCalculators = () => {
    let filtered = allCalculators

    if (selectedCategory !== 'all') {
      filtered = filtered.filter(calc => calc.category === selectedCategory)
    }

    if (searchTerm) {
      const term = searchTerm.toLowerCase()
      filtered = filtered.filter(calc =>
        calc.name.toLowerCase().includes(term) ||
        calc.description.toLowerCase().includes(term)
      )
    }

    setFilteredCalculators(filtered)
  }

  const getCategoryOptions = () => {
    const categories = Object.keys(calculatorsByCategory)
    return [
      { value: 'all', label: 'All Categories' },
      ...categories.map(cat => ({ value: cat, label: cat }))
    ]
  }

  const handleCalculatorClick = (calculator: Calculator) => {
    setSelectedCalculator(calculator)
    setCalculatorInputs({})
    setCalculatorResult(null)
    setCalculationError('')
    setIsModalOpen(true)
  }

  const handleCloseModal = () => {
    setIsModalOpen(false)
    setSelectedCalculator(null)
    setCalculatorInputs({})
    setCalculatorResult(null)
    setCalculationError('')
  }

  const handleInputChange = (inputName: string, value: any) => {
    setCalculatorInputs(prev => ({
      ...prev,
      [inputName]: value
    }))
  }

  const validateInputs = (): boolean => {
    if (!selectedCalculator) return false

    for (const input of selectedCalculator.inputs) {
      if (input.required && !calculatorInputs[input.name]) {
        setCalculationError(`${input.name} is required`)
        return false
      }

      const value = calculatorInputs[input.name]
      if (value !== undefined && value !== null && value !== '') {
        if (input.type === 'int' || input.type === 'float') {
          const numValue = Number(value)
          if (isNaN(numValue)) {
            setCalculationError(`${input.name} must be a number`)
            return false
          }
          if (input.min_value !== undefined && numValue < input.min_value) {
            setCalculationError(`${input.name} must be >= ${input.min_value}`)
            return false
          }
          if (input.max_value !== undefined && numValue > input.max_value) {
            setCalculationError(`${input.name} must be <= ${input.max_value}`)
            return false
          }
        }
      }
    }

    return true
  }

  const handleCalculate = async () => {
    if (!selectedCalculator) return

    setCalculationError('')

    if (!validateInputs()) {
      return
    }

    try {
      setIsCalculating(true)

      const processedInputs: Record<string, any> = {}
      Object.entries(calculatorInputs).forEach(([key, value]) => {
        const input = selectedCalculator.inputs.find(i => i.name === key)
        if (input) {
          if (input.type === 'int') {
            processedInputs[key] = parseInt(value as string, 10)
          } else if (input.type === 'float') {
            processedInputs[key] = parseFloat(value as string)
          } else if (input.type === 'boolean') {
            processedInputs[key] = value === 'true' || value === true
          } else {
            processedInputs[key] = value
          }
        }
      })

      const result = await calculatorsApi.executeCalculator(selectedCalculator.id, {
        inputs: processedInputs
      })

      setCalculatorResult(result)
    } catch (error: any) {
      console.error('Calculation error:', error)
      setCalculationError(error.response?.data?.detail || error.message || 'Calculation failed')
    } finally {
      setIsCalculating(false)
    }
  }

  const renderInput = (input: CalculatorInput) => {
    const value = calculatorInputs[input.name] || ''

    if (input.type === 'choice' && input.choices) {
      return (
        <Select
          key={input.name}
          label={`${input.description}${input.unit ? ` (${input.unit})` : ''}`}
          value={value}
          onChange={(e) => handleInputChange(input.name, e.target.value)}
          options={[
            { value: '', label: 'Select...' },
            ...input.choices.map(choice => ({
              value: String(choice),
              label: String(choice)
            }))
          ]}
          required={input.required}
        />
      )
    }

    if (input.type === 'boolean') {
      return (
        <div key={input.name} className="flex items-center gap-2">
          <input
            type="checkbox"
            id={input.name}
            checked={value === true || value === 'true'}
            onChange={(e) => handleInputChange(input.name, e.target.checked)}
            className="rounded"
          />
          <label htmlFor={input.name} className="text-sm">
            {input.description}
            {input.required && <span className="text-error ml-1">*</span>}
          </label>
        </div>
      )
    }

    return (
      <Input
        key={input.name}
        label={`${input.description}${input.unit ? ` (${input.unit})` : ''}`}
        type={input.type === 'int' || input.type === 'float' ? 'number' : 'text'}
        step={input.type === 'float' ? '0.1' : '1'}
        value={value}
        onChange={(e) => handleInputChange(input.name, e.target.value)}
        required={input.required}
        helpText={
          input.min_value !== undefined && input.max_value !== undefined
            ? `Range: ${input.min_value} - ${input.max_value}`
            : undefined
        }
      />
    )
  }

  const groupedCalculators = calculatorsByCategory && typeof calculatorsByCategory === 'object'
    ? Object.entries(calculatorsByCategory).reduce((acc, [category, calcs]) => {
        const filtered = Array.isArray(calcs)
          ? (calcs as Calculator[]).filter(calc =>
              filteredCalculators.some(fc => fc.id === calc.id)
            )
          : []
        if (filtered.length > 0) {
          acc[category] = filtered
        }
        return acc
      }, {} as CalculatorCategory)
    : {}

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold">Clinical Calculator Library</h1>
        <p className="text-gray-600 dark:text-gray-400 mt-2">
          Access 44+ specialized urology calculators for clinical decision support
        </p>
      </div>

      <Card>
        <div className="flex flex-col sm:flex-row gap-4">
          <div className="flex-1">
            <Input
              placeholder="Search calculators..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              icon={<FiSearch className="w-5 h-5 text-gray-400" />}
            />
          </div>
          <div className="w-full sm:w-64">
            <Select
              value={selectedCategory}
              onChange={(e) => setSelectedCategory(e.target.value)}
              options={getCategoryOptions()}
            />
          </div>
          {(searchTerm || selectedCategory !== 'all') && (
            <Button
              variant="outline"
              onClick={() => {
                setSearchTerm('')
                setSelectedCategory('all')
              }}
              icon={<FiX />}
            >
              Clear
            </Button>
          )}
        </div>
      </Card>

      {isLoading ? (
        <div className="text-center py-12">
          <div className="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-primary"></div>
          <p className="mt-2 text-gray-600 dark:text-gray-400">Loading calculators...</p>
        </div>
      ) : filteredCalculators.length === 0 ? (
        <Card>
          <div className="text-center py-12">
            <FiSearch className="w-12 h-12 mx-auto text-gray-400 mb-4" />
            <p className="text-gray-600 dark:text-gray-400">No calculators found</p>
          </div>
        </Card>
      ) : (
        <div className="space-y-8">
          {Object.entries(groupedCalculators).map(([category, calculators]) => (
            <div key={category}>
              <h2 className="text-xl font-semibold mb-4">
                {category}
                <span className="ml-2 text-sm text-gray-500">
                  ({(calculators as Calculator[]).length})
                </span>
              </h2>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
                {(calculators as Calculator[]).map((calculator) => (
                  <button
                    key={calculator.id}
                    onClick={() => handleCalculatorClick(calculator)}
                    className="card p-4 text-left hover:shadow-lg transition-shadow cursor-pointer border-2 border-transparent hover:border-primary"
                  >
                    <div className="flex items-start gap-3">
                      <FiSearch className="w-6 h-6 text-primary flex-shrink-0 mt-1" />
                      <div className="flex-1 min-w-0">
                        <h3 className="font-semibold text-sm mb-1 line-clamp-2">
                          {calculator.name}
                        </h3>
                        <p className="text-xs text-gray-600 dark:text-gray-400 line-clamp-2">
                          {calculator.description}
                        </p>
                      </div>
                    </div>
                  </button>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}

      {selectedCalculator && (
        <Modal
          isOpen={isModalOpen}
          onClose={handleCloseModal}
          title={selectedCalculator.name}
          description={selectedCalculator.description}
          size="lg"
          footer={
            <div className="flex justify-between items-center w-full">
              <Button variant="outline" onClick={handleCloseModal}>
                Close
              </Button>
              <Button
                variant="medical"
                onClick={handleCalculate}
                isLoading={isCalculating}
                disabled={isCalculating}
              >
                Calculate
              </Button>
            </div>
          }
        >
          <div className="space-y-6">
            {calculationError && (
              <div className="bg-error-50 dark:bg-error-900/20 border border-error text-error px-4 py-3 rounded">
                {calculationError}
              </div>
            )}

            {!calculatorResult ? (
              <div className="space-y-4">
                <h3 className="font-semibold">Input Parameters</h3>
                {selectedCalculator.inputs.map(input => renderInput(input))}
              </div>
            ) : (
              <div className="space-y-4">
                <div className="bg-success-50 dark:bg-success-900/20 border border-success rounded-lg p-4">
                  <h3 className="font-semibold text-lg mb-2">Results</h3>

                  {calculatorResult.score !== undefined && (
                    <div className="mb-3">
                      <span className="text-sm text-gray-600 dark:text-gray-400">Score:</span>
                      <span className="ml-2 text-2xl font-bold">{calculatorResult.score}</span>
                    </div>
                  )}

                  {calculatorResult.risk_level && (
                    <div className="mb-3">
                      <span className="text-sm text-gray-600 dark:text-gray-400">Risk Level:</span>
                      <span className="ml-2 font-semibold">{calculatorResult.risk_level}</span>
                    </div>
                  )}

                  <div className="mb-3">
                    <p className="font-medium text-sm mb-1">Interpretation:</p>
                    <p className="text-sm">{calculatorResult.interpretation}</p>
                  </div>

                  {calculatorResult.breakdown && Object.keys(calculatorResult.breakdown).length > 0 && (
                    <div className="mb-3">
                      <p className="font-medium text-sm mb-2">Detailed Breakdown:</p>
                      <div className="bg-white dark:bg-gray-800 rounded p-3 text-xs">
                        <pre className="whitespace-pre-wrap">
                          {JSON.stringify(calculatorResult.breakdown, null, 2)}
                        </pre>
                      </div>
                    </div>
                  )}

                  {calculatorResult.recommendations && calculatorResult.recommendations.length > 0 && (
                    <div>
                      <p className="font-medium text-sm mb-2">Recommendations:</p>
                      <ul className="list-disc list-inside space-y-1 text-sm">
                        {calculatorResult.recommendations.map((rec, index) => (
                          <li key={index}>{rec}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>

                {calculatorResult.references && calculatorResult.references.length > 0 && (
                  <div>
                    <h4 className="font-semibold text-sm mb-2">References:</h4>
                    <ul className="text-xs space-y-1 text-gray-600 dark:text-gray-400">
                      {calculatorResult.references.map((ref, index) => (
                        <li key={index}>{ref}</li>
                      ))}
                    </ul>
                  </div>
                )}

                <div className="flex gap-2 pt-4 border-t border-gray-200 dark:border-gray-700">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => {
                      setCalculatorResult(null)
                      setCalculationError('')
                    }}
                  >
                    Calculate Again
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => {
                      const text = `${selectedCalculator.name}\n\n${calculatorResult.interpretation}\n\n${calculatorResult.recommendations?.join('\n') || ''}`
                      navigator.clipboard.writeText(text)
                      alert('Results copied to clipboard')
                    }}
                  >
                    Copy Results
                  </Button>
                </div>
              </div>
            )}

            {selectedCalculator.references && selectedCalculator.references.length > 0 && !calculatorResult && (
              <div className="mt-6 pt-6 border-t border-gray-200 dark:border-gray-700">
                <h4 className="font-semibold text-sm mb-2">References:</h4>
                <ul className="text-xs space-y-1 text-gray-600 dark:text-gray-400">
                  {selectedCalculator.references.map((ref, index) => (
                    <li key={index}>{ref}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        </Modal>
      )}
    </div>
  )
}
