import { configureStore } from '@reduxjs/toolkit'
import authReducer from './slices/authSlice'
import noteReducer from './slices/noteSlice'
import calculatorReducer from './slices/calculatorSlice'
import settingsReducer from './slices/settingsSlice'
import uiReducer from './slices/uiSlice'

export const store = configureStore({
  reducer: {
    auth: authReducer,
    note: noteReducer,
    calculator: calculatorReducer,
    settings: settingsReducer,
    ui: uiReducer,
  },
  middleware: (getDefaultMiddleware) =>
    getDefaultMiddleware({
      serializableCheck: {
        // Ignore these action types
        ignoredActions: ['note/appendStreamingContent'],
      },
    }),
  devTools: import.meta.env.VITE_ENABLE_DEVTOOLS === 'true',
})

export type RootState = ReturnType<typeof store.getState>
export type AppDispatch = typeof store.dispatch
