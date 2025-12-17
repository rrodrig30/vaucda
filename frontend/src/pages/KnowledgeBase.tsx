import React, { useState, useRef } from 'react'
import { Card } from '@/components/common/Card'
import { Button } from '@/components/common/Button'
import { Select } from '@/components/common/Select'
import { Textarea } from '@/components/common/Textarea'
import { ragApi } from '@/api'
import { FiSearch, FiBook, FiExternalLink, FiCopy, FiChevronDown, FiChevronUp, FiUpload, FiFile, FiCheck, FiX } from 'react-icons/fi'
import type { EvidenceSearchResponse, EvidenceSearchResult } from '@/types/api.types'

const CATEGORIES = [
  { value: 'all', label: 'All Categories' },
  { value: 'peer_reviewed_papers', label: 'Peer Reviewed Papers' },
  { value: 'aua_guidelines', label: 'AUA Guidelines' },
  { value: 'nccn_guidelines', label: 'NCCN Guidelines' },
  { value: 'aua_updates', label: 'AUA Updates' },
  { value: 'best_practices', label: 'Best Practices' },
  { value: 'aua_core_curriculum', label: 'AUA Core Curriculum' },
  { value: 'other', label: 'Other' },
]

const TOP_K_OPTIONS = [
  { value: '3', label: '3 results' },
  { value: '5', label: '5 results' },
  { value: '10', label: '10 results' },
  { value: '15', label: '15 results' },
]

export const KnowledgeBase: React.FC = () => {
  const [query, setQuery] = useState('')
  const [selectedCategory, setSelectedCategory] = useState('all')
  const [topK, setTopK] = useState(5)
  const [isSearching, setIsSearching] = useState(false)
  const [searchResults, setSearchResults] = useState<EvidenceSearchResult[]>([])
  const [searchMetadata, setSearchMetadata] = useState<{
    query: string
    total_results: number
    search_time_ms: number
  } | null>(null)
  const [expandedResults, setExpandedResults] = useState<Set<string>>(new Set())
  const [hasSearched, setHasSearched] = useState(false)

  // Document upload state
  const [uploadCategory, setUploadCategory] = useState('peer_reviewed_papers')
  const [selectedFiles, setSelectedFiles] = useState<File[]>([])
  const [isUploading, setIsUploading] = useState(false)
  const [uploadResults, setUploadResults] = useState<any>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const folderInputRef = useRef<HTMLInputElement>(null)

  const handleSearch = async () => {
    if (!query.trim()) {
      alert('Please enter a search query')
      return
    }

    try {
      setIsSearching(true)
      setHasSearched(true)

      const response: EvidenceSearchResponse = await ragApi.search({
        query: query.trim(),
        category: selectedCategory === 'all' ? undefined : selectedCategory,
        k: topK,
        include_references: true
      })

      setSearchResults(response.results)
      setSearchMetadata({
        query: response.query,
        total_results: response.total_results,
        search_time_ms: response.search_time_ms
      })
      setExpandedResults(new Set())
    } catch (error: any) {
      console.error('Search error:', error)
      alert(`Search failed: ${error.response?.data?.detail || error.message || 'Unknown error'}`)
    } finally {
      setIsSearching(false)
    }
  }

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSearch()
    }
  }

  const toggleExpanded = (documentId: string) => {
    setExpandedResults(prev => {
      const next = new Set(prev)
      if (next.has(documentId)) {
        next.delete(documentId)
      } else {
        next.add(documentId)
      }
      return next
    })
  }

  const handleCopyResult = (result: EvidenceSearchResult) => {
    const text = `${result.title}\nSource: ${result.source}\n\n${result.content}`
    navigator.clipboard.writeText(text)
    alert('Content copied to clipboard')
  }

  const handleOpenNSQIP = () => {
    window.open('https://riskcalculator.facs.org', '_blank')
  }

  const handleOpenOpenEvidence = () => {
    // Open OpenEvidence with the current query if available
    const searchQuery = query.trim() || 'urology guidelines'
    window.open(`https://openevidence.com?q=${encodeURIComponent(searchQuery)}`, '_blank')
  }

  const getRelevanceColor = (score: number): string => {
    if (score >= 0.8) return 'text-success'
    if (score >= 0.6) return 'text-warning'
    return 'text-gray-500'
  }

  const getRelevanceBadge = (score: number): string => {
    if (score >= 0.8) return 'High'
    if (score >= 0.6) return 'Medium'
    return 'Low'
  }

  // Document upload handlers
  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files) {
      setSelectedFiles(Array.from(e.target.files))
    }
  }

  const handleFolderSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files) {
      // Filter for PDF, DOCX, and TXT files only
      const supportedFiles = Array.from(e.target.files).filter(file => {
        const ext = file.name.toLowerCase()
        return ext.endsWith('.pdf') || ext.endsWith('.docx') || ext.endsWith('.txt')
      })
      setSelectedFiles(supportedFiles)
    }
  }

  const handleUploadDocuments = async () => {
    if (selectedFiles.length === 0) {
      alert('Please select files to upload')
      return
    }

    try {
      setIsUploading(true)
      setUploadResults(null)

      const formData = new FormData()
      selectedFiles.forEach(file => {
        formData.append('files', file)
      })
      formData.append('category', uploadCategory)

      const response = await ragApi.uploadDocuments(formData)

      setUploadResults(response)
      setSelectedFiles([])
      if (fileInputRef.current) {
        fileInputRef.current.value = ''
      }
      if (folderInputRef.current) {
        folderInputRef.current.value = ''
      }

      alert(`Successfully uploaded ${response.processed.length} of ${response.processed.length + response.failed.length} files`)
    } catch (error: any) {
      console.error('Upload error:', error)
      alert(`Upload failed: ${error.response?.data?.detail || error.message || 'Unknown error'}`)
    } finally {
      setIsUploading(false)
    }
  }

  const removeFile = (index: number) => {
    setSelectedFiles(prev => prev.filter((_, i) => i !== index))
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold">Clinical Knowledge Base</h1>
        <p className="text-gray-600 dark:text-gray-400 mt-2">
          Search evidence-based clinical guidelines and literature using RAG
        </p>
      </div>

      <Card title="Upload Clinical Documents" description="Build your knowledge base with clinical papers and guidelines">
        <div className="space-y-4">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <Select
              label="Document Category"
              value={uploadCategory}
              onChange={(e) => setUploadCategory(e.target.value)}
              options={[
                { value: 'peer_reviewed_papers', label: 'Peer Reviewed Papers' },
                { value: 'aua_guidelines', label: 'AUA Guidelines' },
                { value: 'nccn_guidelines', label: 'NCCN Guidelines' },
                { value: 'aua_updates', label: 'AUA Updates' },
                { value: 'best_practices', label: 'Best Practices' },
                { value: 'aua_core_curriculum', label: 'AUA Core Curriculum' },
                { value: 'other', label: 'Other' },
              ]}
            />
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                Select Files or Folder (PDF, DOCX, TXT)
              </label>
              <div className="flex gap-2">
                <input
                  ref={fileInputRef}
                  type="file"
                  multiple
                  accept=".pdf,.docx,.txt"
                  onChange={handleFileSelect}
                  className="hidden"
                />
                <input
                  ref={folderInputRef}
                  type="file"
                  /* @ts-ignore */
                  webkitdirectory=""
                  directory=""
                  onChange={handleFolderSelect}
                  className="hidden"
                />
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => fileInputRef.current?.click()}
                >
                  📄 Select Files
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => folderInputRef.current?.click()}
                >
                  📁 Select Folder
                </Button>
              </div>
            </div>
          </div>

          {selectedFiles.length > 0 && (
            <div className="space-y-2">
              <p className="text-sm font-medium">Selected Files ({selectedFiles.length}):</p>
              {selectedFiles.map((file, index) => (
                <div key={index} className="flex items-center justify-between p-2 bg-gray-50 dark:bg-gray-800 rounded">
                  <div className="flex items-center gap-2">
                    <FiFile className="text-gray-500" />
                    <span className="text-sm">{file.name}</span>
                    <span className="text-xs text-gray-500">({(file.size / 1024).toFixed(1)} KB)</span>
                  </div>
                  <button
                    onClick={() => removeFile(index)}
                    className="text-red-500 hover:text-red-700"
                  >
                    <FiX />
                  </button>
                </div>
              ))}
            </div>
          )}

          <Button
            variant="medical"
            onClick={handleUploadDocuments}
            isLoading={isUploading}
            disabled={selectedFiles.length === 0 || isUploading}
            icon={<FiUpload />}
            fullWidth
          >
            {isUploading ? 'Uploading and Processing...' : 'Upload Documents'}
          </Button>

          {uploadResults && (
            <div className="mt-4 p-4 bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-700 rounded-lg">
              <div className="flex items-start gap-2">
                <FiCheck className="text-green-600 mt-1" />
                <div className="flex-1">
                  <p className="font-semibold text-green-800 dark:text-green-300">
                    {uploadResults.message}
                  </p>
                  {uploadResults.processed.length > 0 && (
                    <ul className="mt-2 text-sm text-green-700 dark:text-green-400 space-y-1">
                      {uploadResults.processed.map((file: any, idx: number) => (
                        <li key={idx}>✓ {file.filename} - {file.chunks_created} chunks created</li>
                      ))}
                    </ul>
                  )}
                  {uploadResults.failed.length > 0 && (
                    <ul className="mt-2 text-sm text-red-700 dark:text-red-400 space-y-1">
                      {uploadResults.failed.map((file: any, idx: number) => (
                        <li key={idx}>✗ {file.filename} - {file.reason}</li>
                      ))}
                    </ul>
                  )}
                </div>
              </div>
            </div>
          )}
        </div>
      </Card>

      <Card title="Search Clinical Evidence" description="Enter your clinical question or topic">
        <div className="space-y-4">
          <Textarea
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyPress={handleKeyPress}
            placeholder="Example: What are the AUA guidelines for active surveillance in low-risk prostate cancer?"
            className="min-h-[100px]"
          />

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <Select
              label="Category Filter"
              value={selectedCategory}
              onChange={(e) => setSelectedCategory(e.target.value)}
              options={CATEGORIES}
            />

            <Select
              label="Number of Results"
              value={String(topK)}
              onChange={(e) => setTopK(parseInt(e.target.value, 10))}
              options={TOP_K_OPTIONS}
            />
          </div>

          <div className="flex gap-2">
            <Button
              variant="medical"
              onClick={handleSearch}
              isLoading={isSearching}
              disabled={!query.trim() || isSearching}
              icon={<FiSearch />}
              fullWidth
            >
              {isSearching ? 'Searching...' : 'Search Knowledge Base'}
            </Button>
          </div>
        </div>
      </Card>

      {searchMetadata && (
        <Card>
          <div className="flex items-center justify-between text-sm text-gray-600 dark:text-gray-400">
            <div>
              Found <span className="font-semibold text-gray-900 dark:text-gray-100">{searchMetadata.total_results}</span> results
              {selectedCategory !== 'all' && (
                <span> in <span className="font-semibold">{CATEGORIES.find(c => c.value === selectedCategory)?.label}</span></span>
              )}
            </div>
            <div>
              Search time: <span className="font-semibold">{searchMetadata.search_time_ms}ms</span>
            </div>
          </div>
        </Card>
      )}

      {hasSearched && searchResults.length === 0 && !isSearching && (
        <Card>
          <div className="text-center py-12">
            <FiBook className="w-12 h-12 mx-auto text-gray-400 mb-4" />
            <p className="text-gray-600 dark:text-gray-400">
              No results found for your query. Try different keywords or broaden your search.
            </p>
          </div>
        </Card>
      )}

      {searchResults.length > 0 && (
        <div className="space-y-4">
          <h2 className="text-xl font-semibold">Search Results</h2>

          {searchResults.map((result) => (
            <Card key={result.document_id} noPadding>
              <div className="p-6">
                <div className="flex items-start justify-between mb-3">
                  <div className="flex-1">
                    <div className="flex items-center gap-2 mb-1">
                      <FiBook className="w-5 h-5 text-primary flex-shrink-0" />
                      <h3 className="font-semibold text-lg">{result.title}</h3>
                    </div>
                    <div className="flex items-center gap-3 text-sm text-gray-600 dark:text-gray-400">
                      <span>Source: {result.source}</span>
                      <span>•</span>
                      <span className="capitalize">{result.metadata.document_type}</span>
                      {result.metadata.category && (
                        <>
                          <span>•</span>
                          <span className="capitalize">{result.metadata.category.replace('_', ' ')}</span>
                        </>
                      )}
                    </div>
                  </div>
                  <div className="flex items-center gap-2 ml-4">
                    <span className={`text-sm font-semibold ${getRelevanceColor(result.relevance_score)}`}>
                      {getRelevanceBadge(result.relevance_score)}
                    </span>
                    <span className="text-xs text-gray-500">
                      ({(result.relevance_score * 100).toFixed(0)}%)
                    </span>
                  </div>
                </div>

                <div className="text-sm text-gray-700 dark:text-gray-300">
                  {expandedResults.has(result.document_id) ? (
                    <div className="whitespace-pre-wrap">{result.content}</div>
                  ) : (
                    <div className="line-clamp-3">{result.content}</div>
                  )}
                </div>

                <div className="flex items-center gap-2 mt-4 pt-4 border-t border-gray-200 dark:border-gray-700">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => toggleExpanded(result.document_id)}
                    icon={expandedResults.has(result.document_id) ? <FiChevronUp /> : <FiChevronDown />}
                  >
                    {expandedResults.has(result.document_id) ? 'Show Less' : 'Show More'}
                  </Button>

                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => handleCopyResult(result)}
                    icon={<FiCopy />}
                  >
                    Copy
                  </Button>

                  {result.metadata.publication_date && (
                    <span className="ml-auto text-xs text-gray-500">
                      Published: {new Date(result.metadata.publication_date).toLocaleDateString()}
                    </span>
                  )}
                </div>
              </div>
            </Card>
          ))}
        </div>
      )}

      <Card title="External Resources" description="Additional clinical decision support tools">
        <div className="space-y-4">
          <div className="flex items-start gap-4 p-4 border border-gray-200 dark:border-gray-700 rounded-lg hover:border-primary transition-colors">
            <div className="flex-1">
              <h3 className="font-semibold mb-1">OpenEvidence</h3>
              <p className="text-sm text-gray-600 dark:text-gray-400">
                Search evidence-based medical literature with AI-powered synthesis. Uses your search query above.
                Note: Requires OpenEvidence account (two-step login process).
              </p>
            </div>
            <Button
              variant="outline"
              size="sm"
              onClick={handleOpenOpenEvidence}
              icon={<FiExternalLink />}
            >
              Open OpenEvidence
            </Button>
          </div>

          <div className="flex items-start gap-4 p-4 border border-gray-200 dark:border-gray-700 rounded-lg hover:border-primary transition-colors">
            <div className="flex-1">
              <h3 className="font-semibold mb-1">NSQIP Surgical Risk Calculator</h3>
              <p className="text-sm text-gray-600 dark:text-gray-400">
                Access the ACS NSQIP Surgical Risk Calculator for preoperative risk assessment
              </p>
            </div>
            <Button
              variant="outline"
              size="sm"
              onClick={handleOpenNSQIP}
              icon={<FiExternalLink />}
            >
              Open NSQIP
            </Button>
          </div>

          <div className="p-4 bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-700 rounded-lg">
            <h4 className="font-semibold text-sm mb-2">Search Tips:</h4>
            <ul className="text-sm space-y-1 text-gray-700 dark:text-gray-300">
              <li>• Use specific clinical terms and questions</li>
              <li>• Include patient characteristics when relevant (age, risk factors)</li>
              <li>• Filter by category for more targeted results</li>
              <li>• Higher relevance scores indicate better matches to your query</li>
              <li>• Results are based on AUA guidelines, clinical trials, and peer-reviewed literature</li>
            </ul>
          </div>
        </div>
      </Card>
    </div>
  )
}
