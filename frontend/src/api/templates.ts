import apiClient from './client'
import type {
  Template,
  CreateTemplateRequest,
  UpdateTemplateRequest,
} from '@/types/api.types'

export const templatesApi = {
  /**
   * Get all templates
   */
  getAllTemplates: async (params?: {
    type?: 'clinic_note' | 'consult' | 'preop' | 'postop'
    active_only?: boolean
  }): Promise<Template[]> => {
    const response = await apiClient.get<{ templates: Template[] }>('/templates', { params })
    return response.data.templates
  },

  /**
   * Get a specific template
   */
  getTemplate: async (templateId: string): Promise<Template> => {
    const response = await apiClient.get<Template>(`/templates/${templateId}`)
    return response.data
  },

  /**
   * Create a new template (admin only)
   */
  createTemplate: async (request: CreateTemplateRequest): Promise<Template> => {
    const response = await apiClient.post<Template>('/templates', request)
    return response.data
  },

  /**
   * Update an existing template (admin only)
   */
  updateTemplate: async (
    templateId: string,
    request: UpdateTemplateRequest
  ): Promise<Template> => {
    const response = await apiClient.put<Template>(`/templates/${templateId}`, request)
    return response.data
  },

  /**
   * Deactivate a template (admin only)
   */
  deleteTemplate: async (templateId: string): Promise<void> => {
    await apiClient.delete(`/templates/${templateId}`)
  },
}
