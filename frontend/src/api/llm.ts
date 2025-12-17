import apiClient from './client'
import type {
  LLMProvider,
  LLMModel,
  PullModelRequest,
  PullModelResponse,
  PullModelStatus,
} from '@/types/api.types'

export const llmApi = {
  /**
   * Get all available LLM providers and their status
   */
  getProviders: async (): Promise<LLMProvider[]> => {
    const response = await apiClient.get<{ providers: LLMProvider[] }>('/llm/providers')
    return response.data.providers
  },

  /**
   * Get Ollama models available locally
   */
  getOllamaModels: async (): Promise<LLMModel[]> => {
    const response = await apiClient.get<{ models: LLMModel[] }>('/llm/ollama/models')
    return response.data.models
  },

  /**
   * Pull a new Ollama model (admin only)
   */
  pullOllamaModel: async (request: PullModelRequest): Promise<PullModelResponse> => {
    const response = await apiClient.post<PullModelResponse>('/llm/ollama/pull', request)
    return response.data
  },

  /**
   * Get model pull status
   */
  getPullStatus: async (taskId: string): Promise<PullModelStatus> => {
    const response = await apiClient.get<PullModelStatus>(`/llm/ollama/pull/${taskId}`)
    return response.data
  },
}
