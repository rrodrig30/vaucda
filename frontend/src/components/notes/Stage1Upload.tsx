import React, { useState, useRef, useCallback } from 'react'
import { Button } from '@/components/common/Button'
import { FiUpload, FiX, FiFile, FiCheck } from 'react-icons/fi'

interface Stage1UploadProps {
  onUpload: (content: string) => void
  onCancel: () => void
}

export const Stage1Upload: React.FC<Stage1UploadProps> = ({
  onUpload,
  onCancel
}) => {
  const [dragActive, setDragActive] = useState(false)
  const [uploadedContent, setUploadedContent] = useState<string | null>(null)
  const [fileName, setFileName] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  const handleFile = useCallback((file: File) => {
    setError(null)

    // Validate file type
    if (!file.name.endsWith('.txt')) {
      setError('Please upload a .txt file only')
      return
    }

    // Validate file size (max 1MB)
    if (file.size > 1024 * 1024) {
      setError('File size must be less than 1MB')
      return
    }

    const reader = new FileReader()
    reader.onload = (e) => {
      const content = e.target?.result as string
      setUploadedContent(content)
      setFileName(file.name)
    }
    reader.onerror = () => {
      setError('Failed to read file')
    }
    reader.readAsText(file)
  }, [])

  const handleDrag = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    e.stopPropagation()
    if (e.type === 'dragenter' || e.type === 'dragover') {
      setDragActive(true)
    } else if (e.type === 'dragleave') {
      setDragActive(false)
    }
  }, [])

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    e.stopPropagation()
    setDragActive(false)

    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      handleFile(e.dataTransfer.files[0])
    }
  }, [handleFile])

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      handleFile(e.target.files[0])
    }
  }

  const handleUseUploadedNote = () => {
    if (uploadedContent) {
      onUpload(uploadedContent)
    }
  }

  const handleClear = () => {
    setUploadedContent(null)
    setFileName(null)
    setError(null)
    if (inputRef.current) {
      inputRef.current.value = ''
    }
  }

  return (
    <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4">
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow-2xl max-w-2xl w-full max-h-[80vh] flex flex-col">
        {/* Header */}
        <div className="p-6 border-b border-gray-200 dark:border-gray-700">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-xl font-bold text-gray-900 dark:text-white">
                Upload Edited Stage 1 Note
              </h2>
              <p className="text-sm text-gray-600 dark:text-gray-400 mt-1">
                Upload your edited Stage 1 note to use for Stage 2 generation
              </p>
            </div>
            <button
              onClick={onCancel}
              className="p-2 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg transition-colors"
            >
              <FiX className="h-5 w-5 text-gray-600 dark:text-gray-400" />
            </button>
          </div>
        </div>

        {/* Upload Area */}
        <div className="flex-1 overflow-auto p-6">
          {!uploadedContent ? (
            <div
              className={`border-2 border-dashed rounded-lg p-8 text-center transition-colors ${
                dragActive
                  ? 'border-primary bg-primary/5'
                  : 'border-gray-300 dark:border-gray-600 hover:border-primary'
              }`}
              onDragEnter={handleDrag}
              onDragLeave={handleDrag}
              onDragOver={handleDrag}
              onDrop={handleDrop}
            >
              <FiUpload className="mx-auto h-12 w-12 text-gray-400 mb-4" />
              <p className="text-lg font-medium text-gray-900 dark:text-white mb-2">
                Drop your .txt file here
              </p>
              <p className="text-sm text-gray-600 dark:text-gray-400 mb-4">
                or click to browse
              </p>
              <input
                ref={inputRef}
                type="file"
                accept=".txt"
                onChange={handleInputChange}
                className="hidden"
                id="stage1-upload"
              />
              <label htmlFor="stage1-upload">
                <Button
                  variant="outline"
                  size="md"
                  onClick={() => inputRef.current?.click()}
                >
                  Select File
                </Button>
              </label>
            </div>
          ) : (
            <div className="space-y-4">
              {/* File info */}
              <div className="flex items-center justify-between p-4 bg-green-50 dark:bg-green-900/20 rounded-lg border border-green-200 dark:border-green-800">
                <div className="flex items-center gap-3">
                  <div className="p-2 bg-green-100 dark:bg-green-800 rounded-lg">
                    <FiFile className="h-5 w-5 text-green-600 dark:text-green-400" />
                  </div>
                  <div>
                    <p className="font-medium text-gray-900 dark:text-white">{fileName}</p>
                    <p className="text-sm text-gray-600 dark:text-gray-400">
                      {uploadedContent.length.toLocaleString()} characters
                    </p>
                  </div>
                </div>
                <button
                  onClick={handleClear}
                  className="p-2 hover:bg-green-100 dark:hover:bg-green-800 rounded-lg transition-colors"
                >
                  <FiX className="h-5 w-5 text-gray-600 dark:text-gray-400" />
                </button>
              </div>

              {/* Preview */}
              <div>
                <p className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                  Preview:
                </p>
                <div className="max-h-64 overflow-auto p-4 bg-gray-50 dark:bg-gray-900 rounded-lg border border-gray-200 dark:border-gray-700">
                  <pre className="text-sm text-gray-800 dark:text-gray-200 font-mono whitespace-pre-wrap">
                    {uploadedContent.slice(0, 2000)}
                    {uploadedContent.length > 2000 && (
                      <span className="text-gray-500">
                        {'\n\n'}... ({(uploadedContent.length - 2000).toLocaleString()} more characters)
                      </span>
                    )}
                  </pre>
                </div>
              </div>
            </div>
          )}

          {error && (
            <div className="mt-4 p-4 bg-red-50 dark:bg-red-900/20 rounded-lg border border-red-200 dark:border-red-800">
              <p className="text-sm text-red-600 dark:text-red-400">{error}</p>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="p-6 border-t border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-900">
          <div className="flex justify-end gap-3">
            <Button
              variant="outline"
              size="md"
              onClick={onCancel}
            >
              Cancel
            </Button>
            <Button
              variant="primary"
              size="md"
              onClick={handleUseUploadedNote}
              disabled={!uploadedContent}
              icon={<FiCheck />}
            >
              Use Uploaded Note
            </Button>
          </div>
        </div>
      </div>
    </div>
  )
}
