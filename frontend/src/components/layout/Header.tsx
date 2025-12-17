import React from 'react'
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
