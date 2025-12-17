import React from 'react'
import clsx from 'clsx'
import { FiCheckCircle, FiAlertCircle, FiAlertTriangle, FiInfo, FiX } from 'react-icons/fi'

interface AlertProps {
  type: 'success' | 'error' | 'warning' | 'info'
  title?: string
  message: string
  onClose?: () => void
  className?: string
}

export const Alert: React.FC<AlertProps> = ({
  type,
  title,
  message,
  onClose,
  className
}) => {
  const config = {
    success: {
      icon: FiCheckCircle,
      className: 'bg-success-50 border-success text-success-900',
    },
    error: {
      icon: FiAlertCircle,
      className: 'bg-error-50 border-error text-error-900',
    },
    warning: {
      icon: FiAlertTriangle,
      className: 'bg-warning-50 border-warning text-warning-900',
    },
    info: {
      icon: FiInfo,
      className: 'bg-info-50 border-info text-info-900',
    },
  }

  const { icon: Icon, className: typeClassName } = config[type]

  return (
    <div
      className={clsx(
        'rounded-lg border-l-4 p-4',
        typeClassName,
        className
      )}
      role="alert"
    >
      <div className="flex">
        <div className="flex-shrink-0">
          <Icon className="w-5 h-5" aria-hidden="true" />
        </div>
        <div className="ml-3 flex-1">
          {title && <h3 className="text-sm font-medium mb-1">{title}</h3>}
          <div className="text-sm">{message}</div>
        </div>
        {onClose && (
          <div className="ml-auto pl-3">
            <button
              onClick={onClose}
              className="inline-flex rounded-md p-1.5 hover:bg-black hover:bg-opacity-10 focus:outline-none focus:ring-2 focus:ring-offset-2"
              aria-label="Dismiss"
            >
              <FiX className="w-4 h-4" />
            </button>
          </div>
        )}
      </div>
    </div>
  )
}
