import { useEffect } from 'react'
import { Routes, Route, Navigate } from 'react-router-dom'
import { useAppSelector } from './store/hooks'

// Layout
import { Layout } from './components/layout/Layout'

// Pages
import { Login } from './pages/Login'
import { Register } from './pages/Register'
import { Dashboard } from './pages/Dashboard'
import { NoteGeneration } from './pages/NoteGeneration'
import { Calculators } from './pages/Calculators'
import { KnowledgeBase } from './pages/KnowledgeBase'
import { Settings } from './pages/Settings'

// Private Route Component
const PrivateRoute = ({ children }: { children: React.ReactNode }) => {
  const { isAuthenticated } = useAppSelector((state) => state.auth)
  return isAuthenticated ? <>{children}</> : <Navigate to="/login" replace />
}

function App() {
  const { theme } = useAppSelector((state) => state.ui)

  useEffect(() => {
    // Apply theme class to document
    if (theme === 'dark') {
      document.documentElement.classList.add('dark')
    } else {
      document.documentElement.classList.remove('dark')
    }
  }, [theme])

  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/register" element={<Register />} />
      <Route
        path="/*"
        element={
          <PrivateRoute>
            <Layout>
              <Routes>
                <Route path="/" element={<Dashboard />} />
                <Route path="/notes" element={<NoteGeneration />} />
                <Route path="/calculators" element={<Calculators />} />
                <Route path="/knowledge-base" element={<KnowledgeBase />} />
                <Route path="/settings" element={<Settings />} />
                <Route path="*" element={<Navigate to="/" replace />} />
              </Routes>
            </Layout>
          </PrivateRoute>
        }
      />
    </Routes>
  )
}

export default App
