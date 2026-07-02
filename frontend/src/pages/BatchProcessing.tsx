import React, { useState, useRef, useEffect, useCallback } from 'react'
import { Card } from '@/components/common/Card'
import { Button } from '@/components/common/Button'
import { notesApi } from '@/api'
import {
  FiFolder, FiPlay, FiCheckCircle, FiXCircle, FiClock,
  FiLoader, FiDownload, FiFileText, FiStopCircle, FiSave,
} from 'react-icons/fi'

interface SelectedFile {
  file: File
  name: string
  size: number
  noteType: string
  outputName: string
  included: boolean
}

// Batch note-type options — 'auto' keeps the per-file filename detection.
const BATCH_NOTE_TYPES = [
  { value: 'auto', label: 'Auto-detect (from filename)' },
  { value: 'urology_clinic', label: 'Urology Clinic' },
  { value: 'urology_consult', label: 'Urology Consult' },
  { value: 'cystoscopy', label: 'Cystoscopy Note' },
]

interface CompletedFile {
  filename: string
  outputFilename: string
  noteType: string
  status: 'completed' | 'failed'
  attempts: number
  generationTime?: number
  errorMessage?: string
  noteContent?: string
  // Set true once written to the input folder's output/ subdir via the
  // File System Access API. Used to mark which files still need writing
  // when the "Save all" button is clicked.
  savedToFolder?: boolean
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

// File System Access API: returns true on browsers (Chrome/Edge/Opera)
// where we can request a writable directory handle and stream `.vaucda`
// files into an `output/` subfolder of the user's chosen input folder.
const hasFSAccess = typeof window !== 'undefined'
  && typeof (window as any).showDirectoryPicker === 'function'

// Write one file into <dirHandle>/output/<filename>. Creates the
// output/ subfolder if it doesn't exist.
async function writeFileToOutputSubfolder(
  dirHandle: any,
  filename: string,
  content: string,
): Promise<void> {
  const outputDir = await dirHandle.getDirectoryHandle('output', { create: true })
  const fileHandle = await outputDir.getFileHandle(filename, { create: true })
  const writable = await fileHandle.createWritable()
  await writable.write(content)
  await writable.close()
}

export const BatchProcessing: React.FC = () => {
  const [selectedFiles, setSelectedFiles] = useState<SelectedFile[]>([])
  const [selectionError, setSelectionError] = useState<string | null>(null)
  const folderInputRef = useRef<HTMLInputElement>(null)
  // Separate <input> for picking one or more individual files (not a folder).
  const fileInputRef = useRef<HTMLInputElement>(null)
  // Note-type override applied to every file in the batch ('auto' = per-file).
  const [batchNoteType, setBatchNoteType] = useState<string>('auto')

  // When the user picks a folder via the modern File System Access API
  // (Chrome/Edge), we hold a writable handle so completed `.vaucda`
  // files can be written directly into <input folder>/output/.
  // Falls back to null in browsers without API support (Firefox/Safari).
  const [dirHandle, setDirHandle] = useState<any>(null)
  const [folderName, setFolderName] = useState<string | null>(null)
  const [folderSaveError, setFolderSaveError] = useState<string | null>(null)

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

  const sortFiles = (files: SelectedFile[]): SelectedFile[] => {
    return files.sort((a, b) => {
      const aMatch = a.name.match(/^(\d+)/)
      const bMatch = b.name.match(/^(\d+)/)
      if (aMatch && bMatch) return parseInt(aMatch[1]) - parseInt(bMatch[1])
      if (aMatch) return -1
      if (bMatch) return 1
      return a.name.localeCompare(b.name)
    })
  }

  const resetSelectionState = () => {
    setSelectionError(null)
    setBatchSummary(null)
    setProcessError(null)
    setCompletedFiles([])
    setTotalContent(null)
    setFolderSaveError(null)
  }

  // Modern path: showDirectoryPicker gives a writable handle so we can
  // save `.vaucda` files directly into <input>/output/. Falls through
  // to the legacy <input webkitdirectory> picker when unavailable or
  // the user cancels.
  const handlePickFolder = async () => {
    if (!hasFSAccess) {
      folderInputRef.current?.click()
      return
    }
    try {
      const handle = await (window as any).showDirectoryPicker({
        mode: 'readwrite',
      })
      const txtFiles: SelectedFile[] = []
      for await (const [name, entry] of handle.entries()) {
        if (entry.kind === 'file' && name.toLowerCase().endsWith('.txt')) {
          const file = await entry.getFile()
          txtFiles.push({
            file, name: file.name, size: file.size,
            noteType: detectNoteType(file.name),
            outputName: file.name.replace(/\.[^/.]+$/, '') + '.vaucda',
            included: true,
          })
        }
      }
      resetSelectionState()
      if (txtFiles.length === 0) {
        setSelectionError('No .txt files found in the selected folder')
        setSelectedFiles([])
        setDirHandle(null)
        setFolderName(null)
        return
      }
      setSelectedFiles(sortFiles(txtFiles))
      setDirHandle(handle)
      setFolderName(handle.name)
    } catch (err: any) {
      // User cancelled the picker — leave existing state untouched.
      if (err?.name === 'AbortError') return
      setSelectionError(`Folder picker failed: ${err?.message || String(err)}`)
    }
  }

  // Legacy path used by Firefox/Safari and as a fallback when the user
  // explicitly chooses the legacy picker via the hidden input.
  // Cannot write back to the input folder — completed files go to the
  // browser's download folder instead.
  // Include/exclude individual files from the batch.
  const toggleFileIncluded = (name: string) => {
    setSelectedFiles(prev => prev.map(sf =>
      sf.name === name ? { ...sf, included: !sf.included } : sf))
  }
  const setAllIncluded = (val: boolean) => {
    setSelectedFiles(prev => prev.map(sf => ({ ...sf, included: val })))
  }

  const handleFolderSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const fileList = e.target.files
    if (!fileList || fileList.length === 0) return

    resetSelectionState()
    setDirHandle(null)
    setFolderName(null)

    const txtFiles: SelectedFile[] = []
    for (let i = 0; i < fileList.length; i++) {
      const file = fileList[i]
      if (file.name.toLowerCase().endsWith('.txt')) {
        txtFiles.push({
          file, name: file.name, size: file.size,
          noteType: detectNoteType(file.name),
          outputName: file.name.replace(/\.[^/.]+$/, '') + '.vaucda',
          included: true,
        })
      }
    }

    if (txtFiles.length === 0) {
      setSelectionError('No .txt files found in the selected folder')
      setSelectedFiles([])
      return
    }

    setSelectedFiles(sortFiles(txtFiles))
  }

  const handleStartBatch = useCallback(() => {
    setShowConfirm(false)
    const filesToProcess = selectedFiles.filter(sf => sf.included)
    if (filesToProcess.length === 0) return

    setIsProcessing(true)
    setProcessError(null)
    setBatchSummary(null)
    setCompletedFiles([])
    setTotalContent(null)
    setCurrentFile(null)
    setCurrentIndex(0)
    setTotalFiles(filesToProcess.length)

    const handle = notesApi.batchUploadProcessStream(
      filesToProcess.map(sf => sf.file),
      {
        visitDate: visitDate || undefined,
        noteType: batchNoteType !== 'auto' ? batchNoteType : undefined,
      },
      {
        onFileStart: (data) => {
          setCurrentFile(data.filename)
          setCurrentIndex(data.current_index)
          setTotalFiles(data.total_files)
        },
        onFileComplete: (data) => {
          // Save into <input>/output/ when a writable dirHandle exists
          // (Chrome/Edge File System Access path). Otherwise the user
          // re-downloads via the per-row button in the results table.
          let saved = false
          if (dirHandle && data.note_content) {
            writeFileToOutputSubfolder(dirHandle, data.output_filename, data.note_content)
              .then(() => {
                setCompletedFiles(prev => prev.map(cf =>
                  cf.outputFilename === data.output_filename
                    ? { ...cf, savedToFolder: true } : cf))
              })
              .catch(err => {
                setFolderSaveError(
                  `Auto-save of ${data.output_filename} to <folder>/output/ failed: `
                  + `${err?.message || String(err)}`,
                )
              })
            saved = false // optimistic; flipped to true above on resolve
          }
          setCompletedFiles(prev => [...prev, {
            filename: data.filename,
            outputFilename: data.output_filename,
            noteType: data.note_type,
            status: 'completed',
            attempts: data.attempts,
            generationTime: data.generation_time_seconds,
            noteContent: data.note_content,
            savedToFolder: saved,
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
          // Auto-save total.vaucda alongside the per-patient files when
          // a writable folder handle is available.
          if (dirHandle && data.note_content) {
            writeFileToOutputSubfolder(dirHandle, 'total.vaucda', data.note_content)
              .catch(err => setFolderSaveError(
                `Auto-save of total.vaucda failed: ${err?.message || String(err)}`,
              ))
          }
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
  }, [selectedFiles, visitDate, dirHandle])

  // Re-saves every completed `.vaucda` (and total.vaucda) to
  // <input>/output/ in one click. Useful when the user wants to grab
  // everything after the fact, or when an earlier auto-save failed.
  const handleSaveAllToFolder = useCallback(async () => {
    if (!dirHandle) return
    setFolderSaveError(null)
    let written = 0
    const errors: string[] = []
    for (const cf of completedFiles) {
      if (cf.status !== 'completed' || !cf.noteContent) continue
      try {
        await writeFileToOutputSubfolder(dirHandle, cf.outputFilename, cf.noteContent)
        written++
      } catch (err: any) {
        errors.push(`${cf.outputFilename}: ${err?.message || String(err)}`)
      }
    }
    if (totalContent) {
      try {
        await writeFileToOutputSubfolder(dirHandle, 'total.vaucda', totalContent)
        written++
      } catch (err: any) {
        errors.push(`total.vaucda: ${err?.message || String(err)}`)
      }
    }
    setCompletedFiles(prev => prev.map(cf =>
      cf.status === 'completed' ? { ...cf, savedToFolder: true } : cf))
    if (errors.length > 0) {
      setFolderSaveError(`Wrote ${written}; failed: ${errors.join('; ')}`)
    }
  }, [dirHandle, completedFiles, totalContent])

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
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">Select Files or Folder</h2>

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
          {/* Individual-file picker: choose one or several .txt files (not a whole folder). */}
          <input
            ref={fileInputRef}
            type="file"
            multiple
            className="hidden"
            onChange={handleFolderSelect}
            accept=".txt"
            aria-label="Select one or more clinical document files"
          />

          <div className="flex items-center gap-4 flex-wrap">
            <Button onClick={handlePickFolder} disabled={isProcessing} className="flex items-center gap-2" aria-label="Browse for folder">
              <FiFolder className="w-4 h-4" aria-hidden="true" />
              Browse for Folder...
            </Button>
            <Button variant="secondary" onClick={() => fileInputRef.current?.click()} disabled={isProcessing} className="flex items-center gap-2" aria-label="Select individual files">
              <FiFileText className="w-4 h-4" aria-hidden="true" />
              Select File(s)...
            </Button>
            <div>
              <label htmlFor="batch-note-type" className="block text-xs font-medium text-gray-600 dark:text-gray-400 mb-1">Note Type</label>
              <select
                id="batch-note-type"
                value={batchNoteType}
                onChange={(e) => setBatchNoteType(e.target.value)}
                disabled={isProcessing}
                className="px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md text-sm bg-white dark:bg-gray-800 text-gray-900 dark:text-white"
                aria-label="Note type applied to all files in the batch"
              >
                {BATCH_NOTE_TYPES.map(nt => (
                  <option key={nt.value} value={nt.value}>{nt.label}</option>
                ))}
              </select>
            </div>
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
                {folderName && (
                  <span className="ml-2 text-green-700 dark:text-green-400">
                    · auto-save to <span className="font-mono">{folderName}/output/</span>
                  </span>
                )}
              </span>
            )}
          </div>

          {selectionError && (
            <div role="alert" className="mt-3 p-3 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg">
              <p className="text-sm text-red-700 dark:text-red-400">{selectionError}</p>
            </div>
          )}

          <div className="mt-3 text-xs text-gray-500 dark:text-gray-400 space-y-1">
            <p>Pick a whole folder or individual <span className="font-mono">.txt</span> file(s), then use the checkboxes to include/exclude any. <span className="font-semibold">Note Type</span> = <span className="font-semibold">Auto-detect</span> uses the filename (<span className="font-mono">CON</span> as a standalone word → Consult, else Clinic); choose a specific type to force it for the whole batch.</p>
            {hasFSAccess ? (
              <p>Output files write directly into an <span className="font-mono">output/</span> subfolder of the folder you select. A combined <span className="font-mono">total.vaucda</span> is written alongside them.</p>
            ) : (
              <p>Your browser does not support direct folder writes. Each completed note downloads to your browser's download folder; combined <span className="font-mono">total.vaucda</span> downloads at the end.</p>
            )}
          </div>
        </div>
      </Card>

      {/* File Preview + Start */}
      {selectedFiles.length > 0 && !isProcessing && !batchSummary && (
        <Card>
          <div className="p-6">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
                Files to Process ({selectedFiles.filter(sf => sf.included).length} of {selectedFiles.length})
              </h2>
              <div className="flex items-center gap-2">
                <button type="button" onClick={() => setAllIncluded(true)} className="text-xs text-primary hover:underline" aria-label="Select all files">All</button>
                <span className="text-gray-300">·</span>
                <button type="button" onClick={() => setAllIncluded(false)} className="text-xs text-primary hover:underline" aria-label="Deselect all files">None</button>
                <Button onClick={() => setShowConfirm(true)} disabled={selectedFiles.every(sf => !sf.included)} className="flex items-center gap-2 bg-green-600 hover:bg-green-700 ml-2" aria-label="Start batch processing">
                  <FiPlay className="w-4 h-4" aria-hidden="true" /> Start Batch Processing
                </Button>
              </div>
            </div>

            {showConfirm && (
              <div role="alertdialog" aria-labelledby="confirm-title" aria-describedby="confirm-desc" className="mb-4 p-4 bg-yellow-50 dark:bg-yellow-900/20 border border-yellow-300 dark:border-yellow-700 rounded-lg">
                <p id="confirm-title" className="font-semibold text-yellow-800 dark:text-yellow-300">Confirm Batch Processing</p>
                <p id="confirm-desc" className="text-sm text-yellow-700 dark:text-yellow-400 mt-1">
                  This will upload and process {selectedFiles.filter(sf => sf.included).length} file{selectedFiles.filter(sf => sf.included).length !== 1 ? 's' : ''}
                  {batchNoteType !== 'auto' && ` as ${BATCH_NOTE_TYPES.find(n => n.value === batchNoteType)?.label}`}.
                  Each note will download automatically as it completes.
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
                    <th scope="col" className="text-left py-2 px-3 text-gray-600 dark:text-gray-400 font-medium">
                      <input
                        type="checkbox"
                        aria-label="Include all files"
                        checked={selectedFiles.length > 0 && selectedFiles.every(sf => sf.included)}
                        ref={el => { if (el) el.indeterminate = selectedFiles.some(sf => sf.included) && selectedFiles.some(sf => !sf.included) }}
                        onChange={(e) => setAllIncluded(e.target.checked)}
                      />
                    </th>
                    <th scope="col" className="text-left py-2 px-3 text-gray-600 dark:text-gray-400 font-medium">#</th>
                    <th scope="col" className="text-left py-2 px-3 text-gray-600 dark:text-gray-400 font-medium">Filename</th>
                    <th scope="col" className="text-left py-2 px-3 text-gray-600 dark:text-gray-400 font-medium">Size</th>
                    <th scope="col" className="text-left py-2 px-3 text-gray-600 dark:text-gray-400 font-medium">Type</th>
                    <th scope="col" className="text-left py-2 px-3 text-gray-600 dark:text-gray-400 font-medium">Output</th>
                  </tr>
                </thead>
                <tbody>
                  {selectedFiles.map((sf, idx) => {
                    // Effective note type = batch override when set, else per-file detection.
                    const effType = batchNoteType !== 'auto' ? batchNoteType : sf.noteType
                    const typeLabel = effType === 'cystoscopy' ? 'Cystoscopy'
                      : effType === 'urology_consult' ? 'Consult' : 'Clinic'
                    const typeClass = effType === 'cystoscopy'
                      ? 'bg-teal-100 text-teal-800 dark:bg-teal-900/30 dark:text-teal-300'
                      : effType === 'urology_consult'
                      ? 'bg-purple-100 text-purple-800 dark:bg-purple-900/30 dark:text-purple-300'
                      : 'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-300'
                    return (
                    <tr key={sf.name} className={`border-b border-gray-100 dark:border-gray-800 ${sf.included ? '' : 'opacity-40'}`}>
                      <td className="py-2 px-3">
                        <input
                          type="checkbox"
                          aria-label={`Include ${sf.name}`}
                          checked={sf.included}
                          onChange={() => toggleFileIncluded(sf.name)}
                        />
                      </td>
                      <td className="py-2 px-3 text-gray-500">{idx + 1}</td>
                      <td className="py-2 px-3 font-mono text-gray-900 dark:text-white">
                        <span className="flex items-center gap-2"><FiFileText className="w-4 h-4 text-gray-400" aria-hidden="true" />{sf.name}</span>
                      </td>
                      <td className="py-2 px-3 text-gray-600 dark:text-gray-400">{formatBytes(sf.size)}</td>
                      <td className="py-2 px-3">
                        <span className={`inline-flex px-2 py-0.5 rounded text-xs font-medium ${typeClass}`}>
                          {typeLabel}
                        </span>
                      </td>
                      <td className="py-2 px-3 font-mono text-gray-500 dark:text-gray-400 text-xs">{sf.outputName}</td>
                    </tr>
                    )
                  })}
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

            {/* Download / save buttons */}
            {batchSummary && (
              <div className="flex flex-col gap-3 mb-4">
                <div className="flex flex-wrap gap-2">
                  {dirHandle && (
                    <Button
                      onClick={handleSaveAllToFolder}
                      className="flex items-center gap-2 bg-blue-600 hover:bg-blue-700 w-fit"
                      aria-label={`Save all .vaucda files to ${folderName}/output/`}
                    >
                      <FiSave className="w-4 h-4" aria-hidden="true" />
                      Save all to {folderName}/output/
                    </Button>
                  )}
                  {totalContent && (
                    <Button onClick={() => triggerDownload('total.vaucda', totalContent)} className="flex items-center gap-2 bg-green-600 hover:bg-green-700 w-fit" aria-label="Download total.vaucda (all notes combined)">
                      <FiDownload className="w-4 h-4" aria-hidden="true" /> Download total.vaucda (all notes combined)
                    </Button>
                  )}
                </div>
                {folderSaveError && (
                  <div role="alert" className="p-3 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg">
                    <p className="text-sm text-red-700 dark:text-red-400">{folderSaveError}</p>
                  </div>
                )}
                <p className="text-xs text-gray-500 dark:text-gray-400">
                  {dirHandle
                    ? `Files were written to ${folderName}/output/ as each completed. Re-save anytime with the button above.`
                    : 'Use the download buttons in the table below for individual files.'}
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
