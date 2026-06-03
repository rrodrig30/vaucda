import React from 'react'
import { Link } from 'react-router-dom'
import { Card } from '@/components/common/Card'
import { useAppSelector } from '@/store/hooks'
import { FiFileText, FiTool, FiBook, FiArrowRight } from 'react-icons/fi'

export const Dashboard: React.FC = () => {
  // HIPAA COMPLIANCE: No note history retrieval - notes are ephemeral only
  const { user } = useAppSelector((state) => state.auth)

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
      icon: FiTool,
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

      {/* HIPAA COMPLIANCE: Recent Notes section removed - notes are ephemeral only
          No note history or persistence to prevent cross-patient contamination */}
    </div>
  )
}
