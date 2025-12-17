import React, { useState, useEffect } from 'react'
import { Button } from '@/components/common/Button'
import { FiSave, FiX, FiCopy, FiDownload } from 'react-icons/fi'

interface NoteEditorProps {
  note: string
  noteType: 'Stage 1' | 'Stage 2'
  onSave: (editedNote: string) => void
  onClose: () => void
}

export const NoteEditor: React.FC<NoteEditorProps> = ({
  note,
  noteType,
  onSave,
  onClose
}) => {
  const [editedNote, setEditedNote] = useState(note)
  const [hasChanges, setHasChanges] = useState(false)

  useEffect(() => {
    setEditedNote(note)
    setHasChanges(false)
  }, [note])

  const handleChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setEditedNote(e.target.value)
    setHasChanges(true)
  }

  const handleSave = () => {
    onSave(editedNote)
    setHasChanges(false)
  }

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(editedNote)
      alert('Note copied to clipboard!')
    } catch (err) {
      console.error('Failed to copy:', err)
    }
  }

  const handleDownload = () => {
    const element = document.createElement('a')
    const file = new Blob([editedNote], { type: 'text/plain' })
    element.href = URL.createObjectURL(file)
    const timestamp = new Date().toISOString().split('T')[0]
    element.download = `${noteType.toLowerCase().replace(' ', '-')}-note-${timestamp}.txt`
    document.body.appendChild(element)
    element.click()
    document.body.removeChild(element)
  }

  return (
    <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4">
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow-2xl max-w-6xl w-full max-h-[90vh] flex flex-col">
        {/* Header */}
        <div className="p-6 border-b border-gray-200 dark:border-gray-700">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-2xl font-bold text-gray-900 dark:text-white">
                Edit {noteType} Note
              </h2>
              {hasChanges && (
                <p className="text-sm text-warning mt-1">
                  You have unsaved changes
                </p>
              )}
            </div>
            <button
              onClick={onClose}
              className="p-2 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg transition-colors"
            >
              <FiX className="h-6 w-6 text-gray-600 dark:text-gray-400" />
            </button>
          </div>
        </div>

        {/* Editor */}
        <div className="flex-1 overflow-hidden p-6">
          <textarea
            value={editedNote}
            onChange={handleChange}
            className="w-full h-full p-4 border border-gray-300 dark:border-gray-600 rounded-lg
                     bg-white dark:bg-gray-900 text-gray-900 dark:text-white
                     font-mono text-sm leading-relaxed
                     focus:ring-2 focus:ring-primary focus:border-transparent
                     resize-none"
            placeholder="Edit your clinical note here..."
          />
        </div>

        {/* Footer Actions */}
        <div className="p-6 border-t border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-900">
          <div className="flex items-center justify-between">
            <div className="flex gap-2">
              <Button
                variant="secondary"
                size="md"
                onClick={handleCopy}
                leftIcon={<FiCopy />}
              >
                Copy
              </Button>
              <Button
                variant="secondary"
                size="md"
                onClick={handleDownload}
                leftIcon={<FiDownload />}
              >
                Download
              </Button>
            </div>
            <div className="flex gap-2">
              <Button
                variant="secondary"
                size="md"
                onClick={onClose}
              >
                Cancel
              </Button>
              <Button
                variant="primary"
                size="md"
                onClick={handleSave}
                leftIcon={<FiSave />}
                disabled={!hasChanges}
              >
                Save Changes
              </Button>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
