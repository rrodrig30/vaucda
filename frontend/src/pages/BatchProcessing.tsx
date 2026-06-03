import React, { useState, useRef, useEffect, useCallback } from 'react'
import { Card } from '@/components/common/Card'
import { Button } from '@/components/common/Button'
import { notesApi } from '@/api'
import {
  FiFolder, FiPlay, FiCheckCircle, FiXCircle, FiClock,
  FiLoader, FiDownload, FiFileText, FiStopCircle,
} from 'react-icons/fi'

interface SelectedFile {
  file: File
  name: string
  size: number
  noteType: string
  outputName: string
}

interface CompletedFile {
  filename: string
  outputFilename: string
  noteType: string
  status: 'completed' | 'failed'
  attempts: number
  generationTime?: number
  errorMessage?: string
  noteContent?: string
}

function detectNoteType(filename: string): string {
  const stem = filename.replace(/\.[^/.]+$/, '').toUpperCase()
  if (/(?<![A-Z])CON(?![A-Z])/.test(stem)) return 'urology_consult'
  return 'urology_clinic'
}

function triggerDownload(filename: string, content: string) {
  const blob = new Blob([content], { type: 'text/plain' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}

export const BatchProcessing: React.FC = () => {
  const [selectedFiles, setSelectedFiles] = useState<SelectedFile[]>([])
  const [selectionError, setSelectionError] = useState<string | null>(null)
  const folderInputRef = useRef<HTMLInputElement>(null)

  const [visitDate, setVisitDate] = useState('')

  const [isProcessing, setIsProcessing] = useState(false)
  const [processError, setProcessError] = useState<string | null>(null)
  const [showConfirm, setShowConfirm] = useState(false)

  // Streaming progress state
  const [currentFile, setCurrentFile] = useState<string | null>(null)
  const [currentIndex, setCurrentIndex] = useState(0)
  const [totalFiles, setTotalFiles] = useState(0)
  const [completedFiles, setCompletedFiles] = useState<CompletedFile[]>([])
  const [totalContent, setTotalContent] = useState<string | null>(null)
  const [batchSummary, setBatchSummary] = useState<{ processed: number; failed: number; totalTime: number } | null>(null)
  const abortRef = useRef<{ abort: () => void } | null>(null)

  useEffect(() => {
    if (!showConfirm) return
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setShowConfirm(false)
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [showConfirm])

  const handleFolderSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const fileList = e.target.files
    if (!fileList || fileList.length === 0) return

    setSelectionError(null)
    setBatchSummary(null)
    setProcessError(null)
    setCompletedFiles([])
    setTotalContent(null)

    const txtFiles: SelectedFile[] = []
    for (let i = 0; i < fileList.length; i++) {
      const file = fileList[i]
      if (file.name.toLowerCase().endsWith('.txt')) {
        txtFiles.push({
          file, name: file.name, size: file.size,
          noteType: detectNoteType(file.name),
          outputName: file.name.replace(/\.[^/.]+$/, '') + '.vaucda',
        })
      }
    }

    if (txtFiles.length === 0) {
      setSelectionError('No .txt files found in the selected folder')
      setSelectedFiles([])
      return
    }

    txtFiles.sort((a, b) => {
      const aMatch = a.name.match(/^(\d+)/)
      const bMatch = b.name.match(/^(\d+)/)
      if (aMatch && bMatch) return parseInt(aMatch[1]) - parseInt(bMatch[1])
      if (aMatch) return -1
      if (bMatch) return 1
      return a.name.localeCompare(b.name)
    })

    setSelectedFiles(txtFiles)
  }

  const handleStartBatch = useCallback(() => {
    setShowConfirm(false)
    if (selectedFiles.length === 0) return

    setIsProcessing(true)
    setProcessError(null)
    setBatchSummary(null)
    setCompletedFiles([])
    setTotalContent(null)
    setCurrentFile(null)
    setCurrentIndex(0)
    setTotalFiles(selectedFiles.length)

    const handle = notesApi.batchUploadProcessStream(
      selectedFiles.map(sf => sf.file),
      { visitDate: visitDate || undefined },
      {
        onFileStart: (data) => {
          setCurrentFile(data.filename)
          setCurrentIndex(data.current_index)
          setTotalFiles(data.total_files)
        },
        onFileComplete: (data) => {
          // Store the note content — user downloads via buttons (auto-download blocked by browsers)
          setCompletedFiles(prev => [...prev, {
            filename: data.filename,
            outputFilename: data.output_filename,
            noteType: data.note_type,
            status: 'completed',
            attempts: data.attempts,
            generationTime: data.generation_time_seconds,
            noteContent: data.note_content,
          }])
        },
        onFileFailed: (data) => {
          setCompletedFiles(prev => [...prev, {
            filename: data.filename,
            outputFilename: data.output_filename,
            noteType: data.note_type,
            status: 'failed',
            attempts: data.attempts,
            errorMessage: data.error_message,
          }])
        },
        onTotal: (data) => {
          setTotalContent(data.note_content)
        },
        onComplete: (data) => {
          setBatchSummary({ processed: data.processed, failed: data.failed, totalTime: data.total_time_seconds })
          setIsProcessing(false)
          setCurrentFile(null)
          abortRef.current = null
        },
        onError: (detail) => {
          setProcessError(detail)
          setIsProcessing(false)
          setCurrentFile(null)
          abortRef.current = null
        },
      }
    )

    abortRef.current = handle
  }, [selectedFiles])

  const handleCancelBatch = useCallback(() => {
    if (abortRef.current) {
      abortRef.current.abort()
      abortRef.current = null
    }
    setIsProcessing(false)
    setCurrentFile(null)
    setProcessError('Batch processing cancelled by user')
  }, [])

  const formatBytes = (bytes: number): string => {
    if (bytes < 1024) return `${bytes} B`
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
  }

  const formatTime = (seconds: number): string => {
    if (seconds < 60) return `${seconds.toFixed(1)}s`
    const mins = Math.floor(seconds / 60)
    const secs = seconds % 60
    return `${mins}m ${secs.toFixed(0)}s`
  }

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'completed': return <FiCheckCircle className="w-5 h-5 text-green-500" aria-label="Completed" />
      case 'failed': return <FiXCircle className="w-5 h-5 text-red-500" aria-label="Failed" />
      case 'processing': return <FiLoader className="w-5 h-5 text-blue-500 animate-spin" aria-label="Processing" />
      default: return <FiClock className="w-5 h-5 text-gray-400" aria-label="Pending" />
    }
  }

  const hasResults = completedFiles.length > 0 || batchSummary !== null

  return (
    <div className="max-w-6xl mx-auto space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Batch Processing</h1>
        <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
          Select a folder of clinical documents. Each completed note downloads automatically as it finishes.
        </p>
      </div>

      {/* Folder Selection */}
      <Card>
        <div className="p-6">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">Select Folder</h2>

          <input
            ref={folderInputRef}
            type="file"
            // @ts-expect-error webkitdirectory is non-standard but widely supported
            webkitdirectory="" directory="" multiple
            className="hidden"
            onChange={handleFolderSelect}
            accept=".txt"
            aria-label="Select folder containing clinical documents"
          />

          <div className="flex items-center gap-4">
            <Button onClick={() => folderInputRef.current?.click()} disabled={isProcessing} className="flex items-center gap-2" aria-label="Browse for folder">
              <FiFolder className="w-4 h-4" aria-hidden="true" />
              Browse for Folder...
            </Button>
            <div>
              <label htmlFor="batch-visit-date" className="block text-xs font-medium text-gray-600 dark:text-gray-400 mb-1">Visit Date</label>
              <input
                id="batch-visit-date"
                type="date"
                value={visitDate}
                onChange={(e) => setVisitDate(e.target.value)}
                disabled={isProcessing}
                className="px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md text-sm bg-white dark:bg-gray-800 text-gray-900 dark:text-white"
                aria-label="Visit date for all files (used for IPSS date and age calculation)"
              />
            </div>
            {selectedFiles.length > 0 && (
              <span className="text-sm text-gray-600 dark:text-gray-400">
                {selectedFiles.length} .txt file{selectedFiles.length !== 1 ? 's' : ''} selected
              </span>
            )}
          </div>

          {selectionError && (
            <div role="alert" className="mt-3 p-3 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg">
              <p className="text-sm text-red-700 dark:text-red-400">{selectionError}</p>
            </div>
          )}

          <div className="mt-3 text-xs text-gray-500 dark:text-gray-400 space-y-1">
            <p>Files with <span className="font-mono font-semibold">CON</span> as a standalone word → <span className="font-semibold">Urology Consult</span>. All others → <span className="font-semibold">Urology Clinic Note</span>.</p>
            <p>Each completed note auto-downloads to your browser's download folder. A combined <span className="font-mono">total.vaucda</span> downloads at the end.</p>
          </div>
        </div>
      </Card>

      {/* File Preview + Start */}
      {selectedFiles.length > 0 && !isProcessing && !batchSummary && (
        <Card>
          <div className="p-6">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-semibold text-gray-900 dark:text-white">Files to Process ({selectedFiles.length})</h2>
              <Button onClick={() => setShowConfirm(true)} className="flex items-center gap-2 bg-green-600 hover:bg-green-700" aria-label="Start batch processing">
                <FiPlay className="w-4 h-4" aria-hidden="true" /> Start Batch Processing
              </Button>
            </div>

            {showConfirm && (
              <div role="alertdialog" aria-labelledby="confirm-title" aria-describedby="confirm-desc" className="mb-4 p-4 bg-yellow-50 dark:bg-yellow-900/20 border border-yellow-300 dark:border-yellow-700 rounded-lg">
                <p id="confirm-title" className="font-semibold text-yellow-800 dark:text-yellow-300">Confirm Batch Processing</p>
                <p id="confirm-desc" className="text-sm text-yellow-700 dark:text-yellow-400 mt-1">
                  This will upload and process {selectedFiles.length} file{selectedFiles.length !== 1 ? 's' : ''}. Each note will download automatically as it completes.
                </p>
                <div className="mt-3 flex gap-2">
                  <Button onClick={handleStartBatch} className="bg-green-600 hover:bg-green-700">Confirm</Button>
                  <Button onClick={() => setShowConfirm(false)} className="bg-gray-200 hover:bg-gray-300 text-gray-800">Cancel</Button>
                </div>
              </div>
            )}

            <div className="overflow-x-auto">
              <table className="w-full text-sm" role="table" aria-label="Files to process">
                <thead>
                  <tr className="border-b border-gray-200 dark:border-gray-700">
                    <th scope="col" className="text-left py-2 px-3 text-gray-600 dark:text-gray-400 font-medium">#</th>
                    <th scope="col" className="text-left py-2 px-3 text-gray-600 dark:text-gray-400 font-medium">Filename</th>
                    <th scope="col" className="text-left py-2 px-3 text-gray-600 dark:text-gray-400 font-medium">Size</th>
                    <th scope="col" className="text-left py-2 px-3 text-gray-600 dark:text-gray-400 font-medium">Type</th>
                    <th scope="col" className="text-left py-2 px-3 text-gray-600 dark:text-gray-400 font-medium">Output</th>
                  </tr>
                </thead>
                <tbody>
                  {selectedFiles.map((sf, idx) => (
                    <tr key={sf.name} className="border-b border-gray-100 dark:border-gray-800">
                      <td className="py-2 px-3 text-gray-500">{idx + 1}</td>
                      <td className="py-2 px-3 font-mono text-gray-900 dark:text-white">
                        <span className="flex items-center gap-2"><FiFileText className="w-4 h-4 text-gray-400" aria-hidden="true" />{sf.name}</span>
                      </td>
                      <td className="py-2 px-3 text-gray-600 dark:text-gray-400">{formatBytes(sf.size)}</td>
                      <td className="py-2 px-3">
                        <span className={`inline-flex px-2 py-0.5 rounded text-xs font-medium ${sf.noteType === 'urology_consult' ? 'bg-purple-100 text-purple-800 dark:bg-purple-900/30 dark:text-purple-300' : 'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-300'}`}>
                          {sf.noteType === 'urology_consult' ? 'Consult' : 'Clinic'}
                        </span>
                      </td>
                      <td className="py-2 px-3 font-mono text-gray-500 dark:text-gray-400 text-xs">{sf.outputName}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </Card>
      )}

      {/* Live Processing Progress */}
      {(isProcessing || hasResults) && (
        <Card>
          <div className="p-6">
            {isProcessing && (
              <div className="mb-4" role="status" aria-live="polite" aria-busy="true">
                <div className="flex items-center justify-between mb-3">
                  <div className="flex items-center gap-3">
                    <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-blue-600" aria-hidden="true"></div>
                    <div>
                      <span className="font-semibold text-gray-900 dark:text-white">Processing</span>
                      {currentFile && (
                        <span className="ml-2 text-sm text-gray-500 dark:text-gray-400">
                          {currentIndex}/{totalFiles}: <span className="font-mono">{currentFile}</span>
                        </span>
                      )}
                    </div>
                  </div>
                  <Button onClick={handleCancelBatch} className="flex items-center gap-1 text-xs bg-red-600 hover:bg-red-700" aria-label="Cancel">
                    <FiStopCircle className="w-3 h-3" aria-hidden="true" /> Cancel
                  </Button>
                </div>

                {/* Progress bar */}
                <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-2">
                  <div
                    className="bg-blue-600 h-2 rounded-full transition-all duration-500"
                    style={{ width: `${totalFiles > 0 ? (completedFiles.length / totalFiles) * 100 : 0}%` }}
                    role="progressbar"
                    aria-valuenow={completedFiles.length}
                    aria-valuemin={0}
                    aria-valuemax={totalFiles}
                  ></div>
                </div>
                <div className="flex justify-between text-xs text-gray-500 dark:text-gray-400 mt-1">
                  <span>{completedFiles.length} of {totalFiles} complete</span>
                  <span>{completedFiles.filter(f => f.status === 'completed').length} succeeded, {completedFiles.filter(f => f.status === 'failed').length} failed</span>
                </div>
              </div>
            )}

            {/* Summary (when done) */}
            {batchSummary && (
              <div className="mb-4 grid grid-cols-3 gap-4">
                <div className="bg-green-50 dark:bg-green-900/20 rounded-lg p-3 text-center">
                  <div className="text-xl font-bold text-green-600">{batchSummary.processed}</div>
                  <div className="text-xs text-green-600">Succeeded</div>
                </div>
                <div className="bg-red-50 dark:bg-red-900/20 rounded-lg p-3 text-center">
                  <div className="text-xl font-bold text-red-600">{batchSummary.failed}</div>
                  <div className="text-xs text-red-600">Failed</div>
                </div>
                <div className="bg-blue-50 dark:bg-blue-900/20 rounded-lg p-3 text-center">
                  <div className="text-xl font-bold text-blue-600">{formatTime(batchSummary.totalTime)}</div>
                  <div className="text-xs text-blue-600">Total Time</div>
                </div>
              </div>
            )}

            {/* Download buttons */}
            {batchSummary && (
              <div className="flex flex-col gap-3 mb-4">
                {totalContent && (
                  <Button onClick={() => triggerDownload('total.vaucda', totalContent)} className="flex items-center gap-2 bg-green-600 hover:bg-green-700 w-fit" aria-label="Download total.vaucda (all notes combined)">
                    <FiDownload className="w-4 h-4" aria-hidden="true" /> Download total.vaucda (all notes combined)
                  </Button>
                )}
                <p className="text-xs text-gray-500 dark:text-gray-400">
                  Use the download buttons in the table below for individual files.
                </p>
              </div>
            )}

            {/* Per-file results table */}
            {completedFiles.length > 0 && (
              <div className="overflow-x-auto">
                <table className="w-full text-sm" role="table" aria-label="Processing results">
                  <thead>
                    <tr className="border-b border-gray-200 dark:border-gray-700">
                      <th scope="col" className="text-left py-2 px-3 text-gray-600 dark:text-gray-400 font-medium">Status</th>
                      <th scope="col" className="text-left py-2 px-3 text-gray-600 dark:text-gray-400 font-medium">File</th>
                      <th scope="col" className="text-left py-2 px-3 text-gray-600 dark:text-gray-400 font-medium">Type</th>
                      <th scope="col" className="text-left py-2 px-3 text-gray-600 dark:text-gray-400 font-medium">Time</th>
                      <th scope="col" className="text-left py-2 px-3 text-gray-600 dark:text-gray-400 font-medium">Re-download</th>
                    </tr>
                  </thead>
                  <tbody>
                    {completedFiles.map((cf) => (
                      <tr key={cf.filename} className={`border-b border-gray-100 dark:border-gray-800 ${cf.status === 'failed' ? 'bg-red-50/50 dark:bg-red-900/10' : ''}`}>
                        <td className="py-2 px-3">{getStatusIcon(cf.status)}</td>
                        <td className="py-2 px-3 font-mono text-gray-900 dark:text-white text-xs">{cf.filename}</td>
                        <td className="py-2 px-3">
                          <span className={`inline-flex px-2 py-0.5 rounded text-xs font-medium ${cf.noteType === 'urology_consult' ? 'bg-purple-100 text-purple-800 dark:bg-purple-900/30 dark:text-purple-300' : 'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-300'}`}>
                            {cf.noteType === 'urology_consult' ? 'Consult' : 'Clinic'}
                          </span>
                        </td>
                        <td className="py-2 px-3 text-gray-600 dark:text-gray-400 text-xs">
                          {cf.generationTime ? formatTime(cf.generationTime) : cf.errorMessage || '-'}
                        </td>
                        <td className="py-2 px-3">
                          {cf.status === 'completed' && cf.noteContent && (
                            <button onClick={() => triggerDownload(cf.outputFilename, cf.noteContent!)} className="text-blue-600 hover:text-blue-800 dark:text-blue-400" aria-label={`Re-download ${cf.outputFilename}`}>
                              <FiDownload className="w-4 h-4" />
                            </button>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </Card>
      )}

      {/* Error */}
      {processError && (
        <Card>
          <div className="p-6">
            <div role="alert" className="p-4 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg">
              <h3 className="font-semibold text-red-700 dark:text-red-400">Error</h3>
              <p className="text-sm text-red-600 dark:text-red-300 mt-1">{processError}</p>
            </div>
          </div>
        </Card>
      )}
    </div>
  )
}
