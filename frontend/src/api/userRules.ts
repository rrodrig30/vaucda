import apiClient from './client'

export interface UserRule {
  id: number
  rule_text: string
  is_active: boolean
  sort_order: number
  created_at: string
  updated_at: string | null
}

export interface UserRuleCreate {
  rule_text: string
  is_active?: boolean
  sort_order?: number
}

export interface UserRuleUpdate {
  rule_text?: string
  is_active?: boolean
  sort_order?: number
}

export const userRulesApi = {
  list: async (): Promise<UserRule[]> => {
    const response = await apiClient.get<UserRule[]>('/settings/user-rules')
    return response.data
  },

  create: async (payload: UserRuleCreate): Promise<UserRule> => {
    const response = await apiClient.post<UserRule>('/settings/user-rules', payload)
    return response.data
  },

  update: async (ruleId: number, payload: UserRuleUpdate): Promise<UserRule> => {
    const response = await apiClient.put<UserRule>(`/settings/user-rules/${ruleId}`, payload)
    return response.data
  },

  remove: async (ruleId: number): Promise<void> => {
    await apiClient.delete(`/settings/user-rules/${ruleId}`)
  },
}
