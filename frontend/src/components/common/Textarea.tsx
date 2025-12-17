import { TextareaHTMLAttributes, forwardRef } from 'react'
import clsx from 'clsx'

interface TextareaProps extends TextareaHTMLAttributes<HTMLTextAreaElement> {
  label?: string
  error?: string
  helpText?: string
  showCharCount?: boolean
  maxCharCount?: number
}

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaProps>(
  ({ label, error, helpText, showCharCount, maxCharCount, className, value, ...props }, ref) => {
    const currentLength = typeof value === 'string' ? value.length : 0

    return (
      <div className="w-full">
        {label && (
          <div className="flex items-center justify-between mb-2">
            <label className="label mb-0">
              {label}
              {props.required && <span className="text-error ml-1">*</span>}
            </label>
            {showCharCount && maxCharCount && (
              <span className={clsx(
                "text-sm",
                currentLength > maxCharCount ? "text-error" : "text-gray-500 dark:text-gray-400"
              )}>
                {currentLength.toLocaleString()} / {maxCharCount.toLocaleString()}
              </span>
            )}
          </div>
        )}
        <textarea
          ref={ref}
          className={clsx(
            'input resize-y min-h-[100px]',
            error && 'input-error',
            className
          )}
          value={value}
          {...props}
        />
        {error && <p className="mt-1 text-sm text-error">{error}</p>}
        {helpText && !error && (
          <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">{helpText}</p>
        )}
      </div>
    )
  }
)

Textarea.displayName = 'Textarea'
