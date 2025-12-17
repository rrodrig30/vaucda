import React from 'react'
import { NavLink } from 'react-router-dom'
import { FiHome, FiFileText, FiTool, FiBook, FiSettings } from 'react-icons/fi'
import { useAppSelector } from '@/store/hooks'
import clsx from 'clsx'

const navigation = [
  { name: 'Dashboard', href: '/', icon: FiHome },
  { name: 'Note Generation', href: '/notes', icon: FiFileText },
  { name: 'Calculators', href: '/calculators', icon: FiTool },
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
