import apiClient from './client'
import type {
  Calculator,
  CalculatorCategory,
  CalculatorExecutionRequest,
  CalculatorExecutionResponse,
  BatchCalculatorRequest,
  BatchCalculatorResponse,
} from '@/types/api.types'

export const calculatorsApi = {
  /**
   * Get all available calculators organized by category
   */
  getAllCalculators: async (): Promise<{ calculators: CalculatorCategory; total: number }> => {
    const response = await apiClient.get<{ calculators: CalculatorCategory; total: number }>('/calculators')
    return response.data
  },

  /**
   * Get detailed information about a specific calculator
   */
  getCalculator: async (calculatorId: string): Promise<Calculator> => {
    const response = await apiClient.get<Calculator>(`/calculators/${calculatorId}`)
    return response.data
  },

  /**
   * Execute a specific calculator
   */
  executeCalculator: async (
    calculatorId: string,
    request: CalculatorExecutionRequest
  ): Promise<CalculatorExecutionResponse> => {
    const response = await apiClient.post<CalculatorExecutionResponse>(
      `/calculators/${calculatorId}/calculate`,
      request
    )
    return response.data
  },

  /**
   * Execute multiple calculators in a single request
   */
  executeBatch: async (request: BatchCalculatorRequest): Promise<BatchCalculatorResponse> => {
    const response = await apiClient.post<BatchCalculatorResponse>('/calculators/batch', request)
    return response.data
  },

  /**
   * Get calculator input schema
   */
  getCalculatorInputSchema: async (calculatorId: string): Promise<any> => {
    const response = await apiClient.get(`/calculators/${calculatorId}/input-schema`)
    return response.data
  },

  /**
   * Get popular calculators
   */
  getPopularCalculators: async (limit: number = 5): Promise<Array<{ calculator_id: string; name: string; usage_count: number }>> => {
    const response = await apiClient.get('/calculators/popular', {
      params: { limit },
    })
    return response.data
  },
}
