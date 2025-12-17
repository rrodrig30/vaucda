import { createSlice, createAsyncThunk } from '@reduxjs/toolkit'
import { settingsApi, templatesApi, llmApi } from '@/api'
import type { UserSettings, UpdateSettingsRequest, Template, LLMProvider } from '@/types/api.types'

interface SettingsState {
  userSettings: UserSettings | null
  templates: Template[]
  llmProviders: LLMProvider[]
  isLoading: boolean
  error: string | null
}

const initialState: SettingsState = {
  userSettings: null,
  templates: [],
  llmProviders: [],
  isLoading: false,
  error: null,
}

// Async thunks
export const fetchSettings = createAsyncThunk(
  'settings/fetch',
  async (_, { rejectWithValue }) => {
    try {
      const response = await settingsApi.getSettings()
      return response
    } catch (error: any) {
      return rejectWithValue(error.detail || 'Failed to fetch settings')
    }
  }
)

export const updateSettings = createAsyncThunk(
  'settings/update',
  async (request: UpdateSettingsRequest, { rejectWithValue }) => {
    try {
      const response = await settingsApi.updateSettings(request)
      return response
    } catch (error: any) {
      return rejectWithValue(error.detail || 'Failed to update settings')
    }
  }
)

export const fetchTemplates = createAsyncThunk(
  'settings/fetchTemplates',
  async (_, { rejectWithValue }) => {
    try {
      const response = await templatesApi.getAllTemplates({ active_only: true })
      return response
    } catch (error: any) {
      return rejectWithValue(error.detail || 'Failed to fetch templates')
    }
  }
)

export const fetchLLMProviders = createAsyncThunk(
  'settings/fetchLLMProviders',
  async (_, { rejectWithValue }) => {
    try {
      const response = await llmApi.getProviders()
      return response
    } catch (error: any) {
      return rejectWithValue(error.detail || 'Failed to fetch LLM providers')
    }
  }
)

const settingsSlice = createSlice({
  name: 'settings',
  initialState,
  reducers: {
    clearError: (state) => {
      state.error = null
    },
  },
  extraReducers: (builder) => {
    builder
      // Fetch settings
      .addCase(fetchSettings.pending, (state) => {
        state.isLoading = true
        state.error = null
      })
      .addCase(fetchSettings.fulfilled, (state, action) => {
        state.isLoading = false
        state.userSettings = action.payload
      })
      .addCase(fetchSettings.rejected, (state, action) => {
        state.isLoading = false
        state.error = action.payload as string
      })
      // Update settings
      .addCase(updateSettings.pending, (state) => {
        state.isLoading = true
        state.error = null
      })
      .addCase(updateSettings.fulfilled, (state, action) => {
        state.isLoading = false
        state.userSettings = action.payload
      })
      .addCase(updateSettings.rejected, (state, action) => {
        state.isLoading = false
        state.error = action.payload as string
      })
      // Fetch templates
      .addCase(fetchTemplates.fulfilled, (state, action) => {
        state.templates = action.payload
      })
      // Fetch LLM providers
      .addCase(fetchLLMProviders.fulfilled, (state, action) => {
        state.llmProviders = action.payload
      })
  },
})

export const { clearError } = settingsSlice.actions
export default settingsSlice.reducer
