import { createSlice, createAsyncThunk, PayloadAction } from '@reduxjs/toolkit'
import { calculatorsApi } from '@/api'
import type {
  Calculator,
  CalculatorCategory,
  CalculatorExecutionRequest,
  CalculatorExecutionResponse,
} from '@/types/api.types'

interface CalculatorState {
  categories: CalculatorCategory | null
  selectedCalculator: Calculator | null
  currentResult: CalculatorExecutionResponse | null
  recentResults: CalculatorExecutionResponse[]
  isLoading: boolean
  isExecuting: boolean
  error: string | null
}

const initialState: CalculatorState = {
  categories: null,
  selectedCalculator: null,
  currentResult: null,
  recentResults: [],
  isLoading: false,
  isExecuting: false,
  error: null,
}

// Async thunks
export const fetchAllCalculators = createAsyncThunk(
  'calculator/fetchAll',
  async (_, { rejectWithValue }) => {
    try {
      const response = await calculatorsApi.getAllCalculators()
      return response
    } catch (error: any) {
      return rejectWithValue(error.detail || 'Failed to fetch calculators')
    }
  }
)

export const fetchCalculator = createAsyncThunk(
  'calculator/fetch',
  async (calculatorId: string, { rejectWithValue }) => {
    try {
      const response = await calculatorsApi.getCalculator(calculatorId)
      return response
    } catch (error: any) {
      return rejectWithValue(error.detail || 'Failed to fetch calculator')
    }
  }
)

export const executeCalculator = createAsyncThunk(
  'calculator/execute',
  async (
    { calculatorId, request }: { calculatorId: string; request: CalculatorExecutionRequest },
    { rejectWithValue }
  ) => {
    try {
      const response = await calculatorsApi.executeCalculator(calculatorId, request)
      return response
    } catch (error: any) {
      return rejectWithValue(error.detail || 'Failed to execute calculator')
    }
  }
)

const calculatorSlice = createSlice({
  name: 'calculator',
  initialState,
  reducers: {
    clearSelectedCalculator: (state) => {
      state.selectedCalculator = null
    },
    clearCurrentResult: (state) => {
      state.currentResult = null
    },
    addToRecentResults: (state, action: PayloadAction<CalculatorExecutionResponse>) => {
      state.recentResults.unshift(action.payload)
      if (state.recentResults.length > 10) {
        state.recentResults = state.recentResults.slice(0, 10)
      }
    },
    clearError: (state) => {
      state.error = null
    },
  },
  extraReducers: (builder) => {
    builder
      // Fetch all calculators
      .addCase(fetchAllCalculators.pending, (state) => {
        state.isLoading = true
        state.error = null
      })
      .addCase(fetchAllCalculators.fulfilled, (state, action) => {
        state.isLoading = false
        state.categories = action.payload
      })
      .addCase(fetchAllCalculators.rejected, (state, action) => {
        state.isLoading = false
        state.error = action.payload as string
      })
      // Fetch calculator
      .addCase(fetchCalculator.pending, (state) => {
        state.isLoading = true
        state.error = null
      })
      .addCase(fetchCalculator.fulfilled, (state, action) => {
        state.isLoading = false
        state.selectedCalculator = action.payload
      })
      .addCase(fetchCalculator.rejected, (state, action) => {
        state.isLoading = false
        state.error = action.payload as string
      })
      // Execute calculator
      .addCase(executeCalculator.pending, (state) => {
        state.isExecuting = true
        state.error = null
      })
      .addCase(executeCalculator.fulfilled, (state, action) => {
        state.isExecuting = false
        state.currentResult = action.payload
        // Add to recent results
        state.recentResults.unshift(action.payload)
        if (state.recentResults.length > 10) {
          state.recentResults = state.recentResults.slice(0, 10)
        }
      })
      .addCase(executeCalculator.rejected, (state, action) => {
        state.isExecuting = false
        state.error = action.payload as string
      })
  },
})

export const {
  clearSelectedCalculator,
  clearCurrentResult,
  addToRecentResults,
  clearError,
} = calculatorSlice.actions

export default calculatorSlice.reducer
