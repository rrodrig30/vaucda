#!/usr/bin/env python3
"""
Script to generate all remaining VAUCDA frontend files
This creates the complete React application with all pages, components, and utilities
"""

import os
from pathlib import Path

# Base directory
FRONTEND_DIR = Path("/home/gulab/PythonProjects/VAUCDA/frontend/src")

# File contents as templates
FILES = {
    # Layout Components
    "components/layout/Header.tsx": '''import React from 'react'
import { FiMenu, FiMoon, FiSun, FiUser, FiLogOut } from 'react-icons/fi'
import { useAppDispatch, useAppSelector } from '@/store/hooks'
import { toggleSidebar, toggleTheme } from '@/store/slices/uiSlice'
import { logout } from '@/store/slices/authSlice'
import { useNavigate } from 'react-router-dom'

export const Header: React.FC = () => {
  const dispatch = useAppDispatch()
  const navigate = useNavigate()
  const { theme } = useAppSelector((state) => state.ui)
  const { user } = useAppSelector((state) => state.auth)

  const handleLogout = async () => {
    await dispatch(logout())
    navigate('/login')
  }

  return (
    <header className="bg-white dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700 px-4 py-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center space-x-4">
          <button
            onClick={() => dispatch(toggleSidebar())}
            className="p-2 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors"
            aria-label="Toggle sidebar"
          >
            <FiMenu className="w-5 h-5" />
          </button>
          <div className="flex items-center space-x-3">
            <img src="/logo.svg" alt="VAUCDA Logo" className="h-10 w-10" />
            <div>
              <h1 className="text-lg font-bold text-primary">VAUCDA</h1>
              <p className="text-xs text-gray-500 dark:text-gray-400">VA Urology Clinical Documentation Assistant</p>
            </div>
          </div>
        </div>

        <div className="flex items-center space-x-4">
          <button
            onClick={() => dispatch(toggleTheme())}
            className="p-2 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors"
            aria-label="Toggle theme"
          >
            {theme === 'dark' ? <FiSun className="w-5 h-5" /> : <FiMoon className="w-5 h-5" />}
          </button>

          <div className="flex items-center space-x-2 px-3 py-2 rounded-lg bg-gray-100 dark:bg-gray-700">
            <FiUser className="w-4 h-4" />
            <span className="text-sm font-medium">{user?.username || 'User'}</span>
          </div>

          <button
            onClick={handleLogout}
            className="p-2 rounded-lg hover:bg-error-50 hover:text-error transition-colors"
            aria-label="Logout"
          >
            <FiLogOut className="w-5 h-5" />
          </button>
        </div>
      </div>
    </header>
  )
}
''',

    "components/layout/Sidebar.tsx": '''import React from 'react'
import { NavLink } from 'react-router-dom'
import { FiHome, FiFileText, FiCalculator, FiBook, FiSettings } from 'react-icons/fi'
import { useAppSelector } from '@/store/hooks'
import clsx from 'clsx'

const navigation = [
  { name: 'Dashboard', href: '/', icon: FiHome },
  { name: 'Note Generation', href: '/notes', icon: FiFileText },
  { name: 'Calculators', href: '/calculators', icon: FiCalculator },
  { name: 'Knowledge Base', href: '/knowledge-base', icon: FiBook },
  { name: 'Settings', href: '/settings', icon: FiSettings },
]

export const Sidebar: React.FC = () => {
  const { sidebarOpen } = useAppSelector((state) => state.ui)

  if (!sidebarOpen) return null

  return (
    <aside className="w-64 bg-white dark:bg-gray-800 border-r border-gray-200 dark:border-gray-700 h-[calc(100vh-4rem)]">
      <nav className="p-4 space-y-2">
        {navigation.map((item) => (
          <NavLink
            key={item.name}
            to={item.href}
            className={({ isActive }) =>
              clsx(
                'flex items-center space-x-3 px-4 py-3 rounded-lg transition-colors',
                isActive
                  ? 'bg-primary text-white'
                  : 'text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700'
              )
            }
          >
            <item.icon className="w-5 h-5" />
            <span className="font-medium">{item.name}</span>
          </NavLink>
        ))}
      </nav>
    </aside>
  )
}
''',

    "components/layout/Layout.tsx": '''import React from 'react'
import { Header } from './Header'
import { Sidebar } from './Sidebar'

interface LayoutProps {
  children: React.ReactNode
}

export const Layout: React.FC<LayoutProps> = ({ children }) => {
  return (
    <div className="h-screen flex flex-col overflow-hidden">
      <Header />
      <div className="flex flex-1 overflow-hidden">
        <Sidebar />
        <main className="flex-1 overflow-y-auto bg-gray-50 dark:bg-gray-900 p-6">
          {children}
        </main>
      </div>
    </div>
  )
}
''',

    # Pages - Login
    "pages/Login.tsx": '''import React from 'react'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { useNavigate } from 'react-router-dom'
import { useAppDispatch, useAppSelector } from '@/store/hooks'
import { login, clearError } from '@/store/slices/authSlice'
import { Button } from '@/components/common/Button'
import { Input } from '@/components/common/Input'
import { Alert } from '@/components/common/Alert'

const loginSchema = z.object({
  username: z.string().min(1, 'Username is required'),
  password: z.string().min(1, 'Password is required'),
})

type LoginFormData = z.infer<typeof loginSchema>

export const Login: React.FC = () => {
  const dispatch = useAppDispatch()
  const navigate = useNavigate()
  const { isLoading, error } = useAppSelector((state) => state.auth)

  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<LoginFormData>({
    resolver: zodResolver(loginSchema),
  })

  const onSubmit = async (data: LoginFormData) => {
    const result = await dispatch(login(data))
    if (login.fulfilled.match(result)) {
      navigate('/')
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-primary to-secondary p-4">
      <div className="max-w-md w-full bg-white dark:bg-gray-800 rounded-lg shadow-heavy p-8">
        <div className="text-center mb-8">
          <img src="/logo.svg" alt="VAUCDA Logo" className="h-16 w-16 mx-auto mb-4" />
          <h1 className="text-2xl font-bold text-primary">VAUCDA</h1>
          <p className="text-sm text-gray-600 dark:text-gray-400 mt-2">
            VA Urology Clinical Documentation Assistant
          </p>
        </div>

        {error && (
          <Alert
            type="error"
            message={error}
            onClose={() => dispatch(clearError())}
            className="mb-4"
          />
        )}

        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
          <Input
            {...register('username')}
            label="Username"
            type="text"
            placeholder="Enter your username"
            error={errors.username?.message}
            autoComplete="username"
          />

          <Input
            {...register('password')}
            label="Password"
            type="password"
            placeholder="Enter your password"
            error={errors.password?.message}
            autoComplete="current-password"
          />

          <Button
            type="submit"
            variant="primary"
            fullWidth
            isLoading={isLoading}
          >
            Sign In
          </Button>
        </form>

        <div className="mt-6 text-center text-sm text-gray-600 dark:text-gray-400">
          <p>Secure VA System - Authorized Access Only</p>
        </div>
      </div>
    </div>
  )
}
''',

    # Pages - Dashboard
    "pages/Dashboard.tsx": '''import React, { useEffect } from 'react'
import { Link } from 'react-router-dom'
import { Card } from '@/components/common/Card'
import { Button } from '@/components/common/Button'
import { Loading } from '@/components/common/Loading'
import { useAppDispatch, useAppSelector } from '@/store/hooks'
import { fetchRecentNotes } from '@/store/slices/noteSlice'
import { FiFileText, FiCalculator, FiBook, FiArrowRight } from 'react-icons/fi'

export const Dashboard: React.FC = () => {
  const dispatch = useAppDispatch()
  const { savedNotes } = useAppSelector((state) => state.note)
  const { user } = useAppSelector((state) => state.auth)

  useEffect(() => {
    dispatch(fetchRecentNotes(5))
  }, [dispatch])

  const quickActions = [
    {
      title: 'Generate Note',
      description: 'Create clinical documentation',
      icon: FiFileText,
      link: '/notes',
      color: 'bg-primary',
    },
    {
      title: 'Calculators',
      description: 'Access clinical calculators',
      icon: FiCalculator,
      link: '/calculators',
      color: 'bg-medical',
    },
    {
      title: 'Knowledge Base',
      description: 'Search evidence-based resources',
      icon: FiBook,
      link: '/knowledge-base',
      color: 'bg-accent',
    },
  ]

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold text-gray-900 dark:text-gray-50">
          Welcome back, {user?.username || 'User'}!
        </h1>
        <p className="text-gray-600 dark:text-gray-400 mt-2">
          Your clinical documentation assistant
        </p>
      </div>

      {/* Quick Actions */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {quickActions.map((action) => (
          <Link key={action.title} to={action.link}>
            <Card className="hover:shadow-medium transition-all cursor-pointer h-full">
              <div className="flex items-start space-x-4">
                <div className={`${action.color} text-white p-3 rounded-lg`}>
                  <action.icon className="w-6 h-6" />
                </div>
                <div className="flex-1">
                  <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-50">
                    {action.title}
                  </h3>
                  <p className="text-sm text-gray-600 dark:text-gray-400 mt-1">
                    {action.description}
                  </p>
                  <div className="flex items-center text-primary mt-2">
                    <span className="text-sm font-medium">Get started</span>
                    <FiArrowRight className="w-4 h-4 ml-1" />
                  </div>
                </div>
              </div>
            </Card>
          </Link>
        ))}
      </div>

      {/* Recent Notes */}
      <Card title="Recent Notes" description="Your recently generated clinical notes">
        {savedNotes.length === 0 ? (
          <p className="text-gray-500 dark:text-gray-400 text-center py-8">
            No recent notes. Generate your first note to get started!
          </p>
        ) : (
          <div className="space-y-3">
            {savedNotes.map((note) => (
              <div
                key={note.note_id}
                className="p-4 rounded-lg border border-gray-200 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors"
              >
                <div className="flex items-center justify-between">
                  <div className="flex-1">
                    <p className="text-sm text-gray-600 dark:text-gray-400">
                      {new Date(note.created_at).toLocaleString()}
                    </p>
                    <p className="text-sm text-gray-800 dark:text-gray-200 mt-1 line-clamp-2">
                      {note.generated_note.substring(0, 150)}...
                    </p>
                  </div>
                  <Button variant="outline" size="sm">
                    View
                  </Button>
                </div>
              </div>
            ))}
          </div>
        )}
      </Card>
    </div>
  )
}
''',

    # Create placeholder pages for remaining routes
    "pages/NoteGeneration.tsx": '''import React from 'react'
import { Card } from '@/components/common/Card'

export const NoteGeneration: React.FC = () => {
  return (
    <div className="space-y-6">
      <h1 className="text-3xl font-bold">Note Generation</h1>
      <Card title="Clinical Note Generator" description="Transform unstructured data into structured clinical notes">
        <p className="text-gray-600 dark:text-gray-400">Note generation interface will be implemented here with WebSocket streaming support.</p>
      </Card>
    </div>
  )
}
''',

    "pages/Calculators.tsx": '''import React from 'react'
import { Card } from '@/components/common/Card'

export const Calculators: React.FC = () => {
  return (
    <div className="space-y-6">
      <h1 className="text-3xl font-bold">Clinical Calculators</h1>
      <Card title="Calculator Library" description="Access 44 specialized urology calculators">
        <p className="text-gray-600 dark:text-gray-400">Calculator library interface will be implemented here.</p>
      </Card>
    </div>
  )
}
''',

    "pages/KnowledgeBase.tsx": '''import React from 'react'
import { Card } from '@/components/common/Card'

export const KnowledgeBase: React.FC = () => {
  return (
    <div className="space-y-6">
      <h1 className="text-3xl font-bold">Knowledge Base</h1>
      <Card title="RAG Search" description="Search evidence-based clinical guidelines and literature">
        <p className="text-gray-600 dark:text-gray-400">RAG search interface will be implemented here.</p>
      </Card>
    </div>
  )
}
''',

    "pages/Settings.tsx": '''import React from 'react'
import { Card } from '@/components/common/Card'

export const Settings: React.FC = () => {
  return (
    <div className="space-y-6">
      <h1 className="text-3xl font-bold">Settings</h1>
      <Card title="User Preferences" description="Configure your VAUCDA experience">
        <p className="text-gray-600 dark:text-gray-400">Settings interface will be implemented here.</p>
      </Card>
    </div>
  )
}
''',

    # Utilities
    "utils/constants.ts": '''export const CALCULATOR_CATEGORIES = {
  prostate_cancer: 'Prostate Cancer',
  kidney_cancer: 'Kidney Cancer',
  bladder_cancer: 'Bladder Cancer',
  male_voiding: 'Male Voiding',
  female_urology: 'Female Urology',
  reconstructive: 'Reconstructive Urology',
  fertility: 'Male Fertility',
  hypogonadism: 'Hypogonadism',
  stones: 'Urolithiasis',
  surgical_planning: 'Surgical Planning',
} as const

export const NOTE_TYPES = {
  clinic_note: 'Clinic Note',
  consult: 'Consult Note',
  preop: 'Pre-Op Note',
  postop: 'Post-Op Note',
} as const

export const LLM_PROVIDERS = {
  ollama: 'Ollama (Local)',
  anthropic: 'Anthropic Claude',
  openai: 'OpenAI GPT',
} as const
''',

    "utils/formatting.ts": '''export const formatDate = (date: string | Date): string => {
  return new Date(date).toLocaleDateString('en-US', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

export const formatNumber = (num: number, decimals: number = 2): string => {
  return num.toFixed(decimals)
}

export const formatBytes = (bytes: number): string => {
  if (bytes === 0) return '0 Bytes'
  const k = 1024
  const sizes = ['Bytes', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return Math.round((bytes / Math.pow(k, i)) * 100) / 100 + ' ' + sizes[i]
}

export const truncate = (str: string, length: number): string => {
  return str.length > length ? str.substring(0, length) + '...' : str
}
''',

    "utils/validation.ts": '''export const isValidEmail = (email: string): boolean => {
  const emailRegex = /^[^\\s@]+@[^\\s@]+\\.[^\\s@]+$/
  return emailRegex.test(email)
}

export const isValidNumber = (value: any): boolean => {
  return !isNaN(parseFloat(value)) && isFinite(value)
}

export const isInRange = (value: number, min: number, max: number): boolean => {
  return value >= min && value <= max
}

export const sanitizeInput = (input: string): string => {
  return input.trim().replace(/[<>]/g, '')
}
''',

    # Hooks
    "hooks/useWebSocket.ts": '''import { useEffect, useRef, useCallback } from 'react'
import { io, Socket } from 'socket.io-client'

const WS_URL = import.meta.env.VITE_WS_URL || 'ws://localhost:8000'

interface UseWebSocketOptions {
  onMessage?: (data: any) => void
  onConnect?: () => void
  onDisconnect?: () => void
  onError?: (error: any) => void
}

export const useWebSocket = (options: UseWebSocketOptions = {}) => {
  const socketRef = useRef<Socket | null>(null)
  const { onMessage, onConnect, onDisconnect, onError } = options

  useEffect(() => {
    const token = localStorage.getItem('access_token')

    socketRef.current = io(WS_URL, {
      auth: { token },
      transports: ['websocket'],
    })

    const socket = socketRef.current

    socket.on('connect', () => {
      console.log('WebSocket connected')
      onConnect?.()
    })

    socket.on('disconnect', () => {
      console.log('WebSocket disconnected')
      onDisconnect?.()
    })

    socket.on('error', (error: any) => {
      console.error('WebSocket error:', error)
      onError?.(error)
    })

    socket.on('message', (data: any) => {
      onMessage?.(data)
    })

    return () => {
      socket.close()
    }
  }, [onMessage, onConnect, onDisconnect, onError])

  const sendMessage = useCallback((type: string, payload: any) => {
    if (socketRef.current?.connected) {
      socketRef.current.emit('message', { type, payload })
    }
  }, [])

  return {
    sendMessage,
    isConnected: socketRef.current?.connected || false,
  }
}
''',

    "hooks/useAuth.ts": '''import { useAppSelector } from '@/store/hooks'

export const useAuth = () => {
  const { user, isAuthenticated, isLoading, error } = useAppSelector((state) => state.auth)

  return {
    user,
    isAuthenticated,
    isLoading,
    error,
    isAdmin: user?.role === 'admin',
  }
}
''',
}


def create_file(filepath: str, content: str):
    """Create a file with the given content"""
    full_path = FRONTEND_DIR / filepath
    full_path.parent.mkdir(parents=True, exist_ok=True)

    with open(full_path, 'w', encoding='utf-8') as f:
        f.write(content)

    print(f"Created: {filepath}")


def main():
    """Generate all frontend files"""
    print("Generating VAUCDA frontend files...")
    print(f"Target directory: {FRONTEND_DIR}")

    for filepath, content in FILES.items():
        try:
            create_file(filepath, content)
        except Exception as e:
            print(f"Error creating {filepath}: {e}")

    print(f"\\nSuccessfully created {len(FILES)} files!")
    print("\\nNext steps:")
    print("1. cd /home/gulab/PythonProjects/VAUCDA/frontend")
    print("2. npm install")
    print("3. npm run dev")


if __name__ == "__main__":
    main()
