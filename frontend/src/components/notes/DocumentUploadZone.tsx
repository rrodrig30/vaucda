import React, { useState, useRef, useCallback } from 'react'
import { Button } from '@/components/common/Button'
import { notesApi } from '@/api'
import { FiUpload, FiX, FiFile, FiFileText, FiLoader, FiAlertCircle, FiCheckCircle } from 'react-icons/fi'
import type { DocumentUploadResponse } from '@/types/api.types'

interface DocumentUploadZoneProps {
  onUploadComplete: (text: string, response: DocumentUploadResponse) => void
  disabled?: boolean
}

interface UploadState {
  status: 'idle' | 'uploading' | 'processing' | 'success' | 'error'
  progress?: string
  error?: string
  response?: DocumentUploadResponse
}

const MAX_FILE_SIZE = 100 * 1024 * 1024 // 100MB
const ALLOWED_EXTENSIONS = ['.pdf', '.txt']

export const DocumentUploadZone: React.FC<DocumentUploadZoneProps> = ({
  onUploadComplete,
  disabled = false
}) => {
  const [dragActive, setDragActive] = useState(false)
  const [uploadState, setUploadState] = useState<UploadState>({ status: 'idle' })
  const inputRef = useRef<HTMLInputElement>(null)

  const validateFile = (file: File): string | null => {
    const ext = '.' + file.name.split('.').pop()?.toLowerCase()

    if (!ALLOWED_EXTENSIONS.includes(ext)) {
      return `Invalid file type: ${ext}. Only PDF and TXT files are supported.`
    }

    if (file.size > MAX_FILE_SIZE) {
      return `File too large (${(file.size / 1024 / 1024).toFixed(1)}MB). Maximum size is 100MB.`
    }

    return null
  }

  const handleFile = useCallback(async (file: File) => {
    const validationError = validateFile(file)
    if (validationError) {
      setUploadState({ status: 'error', error: validationError })
      return
    }

    const isPdf = file.name.toLowerCase().endsWith('.pdf')

    setUploadState({
      status: 'uploading',
      progress: isPdf ? 'Uploading PDF...' : 'Uploading text file...'
    })

    try {
      // Update to processing state
      setUploadState({
        status: 'processing',
        progress: isPdf
          ? 'Processing PDF (OCR may take a few minutes for scanned documents)...'
          : 'Extracting text...'
      })

      const response = await notesApi.uploadDocument(file)

      setUploadState({
        status: 'success',
        response
      })

      // Pass extracted text to parent
      onUploadComplete(response.extracted_text, response)
    } catch (error: any) {
      console.error('Document upload error:', error)
      setUploadState({
        status: 'error',
        error: error.response?.data?.detail || error.message || 'Failed to upload document'
      })
    }
  }, [onUploadComplete])

  const handleDrag = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    e.stopPropagation()
    if (disabled) return

    if (e.type === 'dragenter' || e.type === 'dragover') {
      setDragActive(true)
    } else if (e.type === 'dragleave') {
      setDragActive(false)
    }
  }, [disabled])

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    e.stopPropagation()
    setDragActive(false)

    if (disabled) return

    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      handleFile(e.dataTransfer.files[0])
    }
  }, [handleFile, disabled])

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      handleFile(e.target.files[0])
    }
  }

  const handleClear = () => {
    setUploadState({ status: 'idle' })
    if (inputRef.current) {
      inputRef.current.value = ''
    }
  }

  const formatFileSize = (bytes: number): string => {
    if (bytes < 1024) return `${bytes} B`
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
    return `${(bytes / 1024 / 1024).toFixed(1)} MB`
  }

  // Idle state - show dropzone
  if (uploadState.status === 'idle') {
    return (
      <div className="mt-4 pt-4 border-t border-gray-200 dark:border-gray-700">
        <div className="flex items-center gap-2 mb-2">
          <FiUpload className="h-4 w-4 text-gray-500" />
          <span className="text-sm font-medium text-gray-700 dark:text-gray-300">
            Upload Document (Optional)
          </span>
        </div>
        <div
          className={`border-2 border-dashed rounded-lg p-6 text-center transition-colors cursor-pointer ${
            dragActive
              ? 'border-primary bg-primary/5'
              : disabled
                ? 'border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800 cursor-not-allowed'
                : 'border-gray-300 dark:border-gray-600 hover:border-primary hover:bg-gray-50 dark:hover:bg-gray-800'
          }`}
          onDragEnter={handleDrag}
          onDragLeave={handleDrag}
          onDragOver={handleDrag}
          onDrop={handleDrop}
          onClick={() => !disabled && inputRef.current?.click()}
        >
          <FiFile className="mx-auto h-8 w-8 text-gray-400 mb-2" />
          <p className="text-sm text-gray-600 dark:text-gray-400">
            Drop PDF or TXT file here, or <span className="text-primary font-medium">browse</span>
          </p>
          <p className="text-xs text-gray-500 dark:text-gray-500 mt-1">
            Scanned PDFs will be processed with OCR (may take longer)
          </p>
          <input
            ref={inputRef}
            type="file"
            accept=".pdf,.txt"
            onChange={handleInputChange}
            className="hidden"
            disabled={disabled}
          />
        </div>
      </div>
    )
  }

  // Uploading/Processing state
  if (uploadState.status === 'uploading' || uploadState.status === 'processing') {
    return (
      <div className="mt-4 pt-4 border-t border-gray-200 dark:border-gray-700">
        <div className="flex items-center gap-2 mb-2">
          <FiUpload className="h-4 w-4 text-gray-500" />
          <span className="text-sm font-medium text-gray-700 dark:text-gray-300">
            Upload Document
          </span>
        </div>
        <div className="border-2 border-primary/30 bg-primary/5 rounded-lg p-6 text-center">
          <FiLoader className="mx-auto h-8 w-8 text-primary animate-spin mb-2" />
          <p className="text-sm font-medium text-primary">
            {uploadState.progress}
          </p>
          <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
            Please wait, this may take a few minutes for large documents
          </p>
        </div>
      </div>
    )
  }

  // Error state
  if (uploadState.status === 'error') {
    return (
      <div className="mt-4 pt-4 border-t border-gray-200 dark:border-gray-700">
        <div className="flex items-center gap-2 mb-2">
          <FiUpload className="h-4 w-4 text-gray-500" />
          <span className="text-sm font-medium text-gray-700 dark:text-gray-300">
            Upload Document
          </span>
        </div>
        <div className="border-2 border-red-200 dark:border-red-800 bg-red-50 dark:bg-red-900/20 rounded-lg p-4">
          <div className="flex items-start gap-3">
            <FiAlertCircle className="h-5 w-5 text-red-500 flex-shrink-0 mt-0.5" />
            <div className="flex-1">
              <p className="text-sm font-medium text-red-700 dark:text-red-400">
                Upload Failed
              </p>
              <p className="text-sm text-red-600 dark:text-red-300 mt-1">
                {uploadState.error}
              </p>
            </div>
            <button
              onClick={handleClear}
              className="p-1 hover:bg-red-100 dark:hover:bg-red-800 rounded transition-colors"
            >
              <FiX className="h-4 w-4 text-red-500" />
            </button>
          </div>
          <Button
            variant="outline"
            size="sm"
            className="mt-3"
            onClick={handleClear}
          >
            Try Again
          </Button>
        </div>
      </div>
    )
  }

  // Success state
  if (uploadState.status === 'success' && uploadState.response) {
    const { response } = uploadState
    return (
      <div className="mt-4 pt-4 border-t border-gray-200 dark:border-gray-700">
        <div className="flex items-center gap-2 mb-2">
          <FiCheckCircle className="h-4 w-4 text-green-500" />
          <span className="text-sm font-medium text-green-700 dark:text-green-400">
            Document Uploaded
          </span>
        </div>
        <div className="border-2 border-green-200 dark:border-green-800 bg-green-50 dark:bg-green-900/20 rounded-lg p-4">
          <div className="flex items-start justify-between">
            <div className="flex items-start gap-3">
              <div className="p-2 bg-green-100 dark:bg-green-800 rounded-lg">
                <FiFileText className="h-5 w-5 text-green-600 dark:text-green-400" />
              </div>
              <div>
                <p className="font-medium text-gray-900 dark:text-white">
                  {response.file_name}
                </p>
                <div className="flex items-center gap-3 mt-1 text-sm text-gray-600 dark:text-gray-400">
                  <span>{formatFileSize(response.file_size_bytes)}</span>
                  <span className="text-gray-400">|</span>
                  <span>{response.page_count} page{response.page_count > 1 ? 's' : ''}</span>
                  <span className="text-gray-400">|</span>
                  <span>{response.extracted_text.length.toLocaleString()} chars</span>
                </div>
                <div className="mt-2">
                  <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${
                    response.extraction_method === 'ocr'
                      ? 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400'
                      : 'bg-gray-100 text-gray-700 dark:bg-gray-700 dark:text-gray-300'
                  }`}>
                    {response.extraction_method === 'ocr' ? 'OCR Processed' : 'Direct Text'}
                  </span>
                </div>
              </div>
            </div>
            <button
              onClick={handleClear}
              className="p-2 hover:bg-green-100 dark:hover:bg-green-800 rounded-lg transition-colors"
              title="Remove uploaded document"
            >
              <FiX className="h-4 w-4 text-gray-500 dark:text-gray-400" />
            </button>
          </div>
        </div>
      </div>
    )
  }

  return null
}
