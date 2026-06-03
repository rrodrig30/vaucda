import apiClient from './client'
import type {
  LLMProvider,
  LLMModel,
  PullModelRequest,
  PullModelResponse,
  PullModelStatus,
  ModelContextSizeResponse,
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

  /**
   * Look up the published training context window (n_ctx_train) for a model.
   * Used to populate the num_ctx input default in Settings when a user picks a model.
   */
  getModelContextSize: async (model: string): Promise<ModelContextSizeResponse> => {
    const response = await apiClient.get<ModelContextSizeResponse>('/llm/model-context-size', {
      params: { model },
    })
    return response.data
  },
}
