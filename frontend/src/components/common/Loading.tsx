import React from 'react'
import clsx from 'clsx'

interface LoadingProps {
  size?: 'sm' | 'md' | 'lg'
  text?: string
  fullScreen?: boolean
}

export const Loading: React.FC<LoadingProps> = ({
  size = 'md',
  text,
  fullScreen = false
}) => {
  const sizeClasses = {
    sm: 'w-4 h-4',
    md: 'w-8 h-8',
    lg: 'w-12 h-12',
  }

  const spinner = (
    <div className={clsx('spinner border-t-primary', sizeClasses[size])} />
  )

  if (fullScreen) {
    return (
      <div className="fixed inset-0 z-50 flex items-center justify-center bg-white dark:bg-gray-900 bg-opacity-75 dark:bg-opacity-75">
        <div className="text-center">
          {spinner}
          {text && <p className="mt-4 text-gray-700 dark:text-gray-300">{text}</p>}
        </div>
      </div>
    )
  }

  return (
    <div className="flex items-center justify-center p-4">
      {spinner}
      {text && <span className="ml-3 text-gray-700 dark:text-gray-300">{text}</span>}
    </div>
  )
}
