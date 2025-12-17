import React, { HTMLAttributes } from 'react'
import clsx from 'clsx'

interface CardProps extends HTMLAttributes<HTMLDivElement> {
  title?: string
  description?: string
  footer?: React.ReactNode
  noPadding?: boolean
}

export const Card: React.FC<CardProps> = ({
  title,
  description,
  footer,
  noPadding = false,
  children,
  className,
  ...props
}) => {
  return (
    <div className={clsx('card', className)} {...props}>
      {(title || description) && (
        <div className={clsx('border-b border-gray-200 dark:border-gray-700', !noPadding && 'px-6 py-4')}>
          {title && (
            <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-50">
              {title}
            </h3>
          )}
          {description && (
            <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">{description}</p>
          )}
        </div>
      )}
      <div className={clsx(!noPadding && 'p-6')}>{children}</div>
      {footer && (
        <div className="px-6 py-4 bg-gray-50 dark:bg-gray-700 border-t border-gray-200 dark:border-gray-600 rounded-b-lg">
          {footer}
        </div>
      )}
    </div>
  )
}
