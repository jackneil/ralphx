import { useState, useEffect, useCallback } from 'react'
import {
  getDesignDocFile,
  listDesignDocBackups,
  listDesignDocFiles,
  diffDesignDocVersions,
  restoreDesignDocBackup,
} from '../../api'
import type { DesignDocFile, DesignDocBackup, DiffResult } from '../../api'

interface DesignDocCardProps {
  projectSlug: string
  designDocPath?: string
  stepStatus: string
  onLinkFile?: (path: string) => void
}

export default function DesignDocCard({
  projectSlug,
  designDocPath,
  stepStatus,
  onLinkFile,
}: DesignDocCardProps) {
  // State
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [fileInfo, setFileInfo] = useState<(DesignDocFile & { content: string }) | null>(null)
  const [fileExists, setFileExists] = useState(true)
  const [backups, setBackups] = useState<DesignDocBackup[]>([])
  const [availableFiles, setAvailableFiles] = useState<DesignDocFile[]>([])

  // Modal states
  const [showContent, setShowContent] = useState(false)
  const [showCompare, setShowCompare] = useState(false)
  const [showLinkDropdown, setShowLinkDropdown] = useState(false)

  // Diff state
  const [diffResult, setDiffResult] = useState<DiffResult | null>(null)
  const [diffLeft, setDiffLeft] = useState<string>('')
  const [diffRight, setDiffRight] = useState<string>('current')
  const [loadingDiff, setLoadingDiff] = useState(false)

  const loadFileInfo = useCallback(async () => {
    if (!designDocPath) {
      setLoading(false)
      return
    }

    try {
      setLoading(true)
      setError(null)

      const [file, backupList] = await Promise.all([
        getDesignDocFile(projectSlug, designDocPath).catch(() => null),
        listDesignDocBackups(projectSlug, designDocPath).catch(() => []),
      ])

      if (file) {
        setFileInfo(file)
        setFileExists(true)
      } else {
        setFileExists(false)
      }
      setBackups(backupList)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load file info')
    } finally {
      setLoading(false)
    }
  }, [projectSlug, designDocPath])

  const loadAvailableFiles = useCallback(async () => {
    try {
      const files = await listDesignDocFiles(projectSlug)
      setAvailableFiles(files)
    } catch (err) {
      console.error('Failed to load available files:', err)
    }
  }, [projectSlug])

  useEffect(() => {
    loadFileInfo()
  }, [loadFileInfo])

  useEffect(() => {
    if (!designDocPath) {
      loadAvailableFiles()
    }
  }, [designDocPath, loadAvailableFiles])

  const handleCompare = async () => {
    if (!designDocPath || !diffLeft) return

    setLoadingDiff(true)
    try {
      const result = await diffDesignDocVersions(
        projectSlug,
        designDocPath,
        diffLeft,
        diffRight
      )
      setDiffResult(result)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to generate diff')
    } finally {
      setLoadingDiff(false)
    }
  }

  const handleRestore = async (backupName: string) => {
    if (!designDocPath) return

    try {
      await restoreDesignDocBackup(projectSlug, designDocPath, backupName)
      loadFileInfo()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to restore backup')
    }
  }

  const formatSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`
    return `${(bytes / 1024).toFixed(1)} KB`
  }

  const formatDate = (dateStr: string) => {
    if (!dateStr) return 'Unknown'
    const date = new Date(dateStr)
    if (isNaN(date.getTime())) return 'Unknown'
    return date.toLocaleString()
  }

  // Loading state
  if (loading) {
    return (
      <div className="card mb-4">
        <div className="flex items-center space-x-2 text-gray-400">
          <div className="animate-spin w-4 h-4 border-2 border-gray-400 border-t-transparent rounded-full" />
          <span>Loading design document info...</span>
        </div>
      </div>
    )
  }

  // Error state
  if (error && !fileInfo && designDocPath) {
    return (
      <div className="card mb-4 border-red-800 bg-red-900/20">
        <div className="flex items-center justify-between">
          <div className="flex items-center space-x-2 text-red-400">
            <span>Error: {error}</span>
          </div>
          <button onClick={loadFileInfo} className="text-sm text-red-400 hover:text-red-300 underline">
            Retry
          </button>
        </div>
      </div>
    )
  }

  // No file linked state
  if (!designDocPath) {
    return (
      <div className="card mb-4">
        <h3 className="text-lg font-semibold text-white mb-3 flex items-center gap-2">
          <svg className="w-5 h-5 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
          </svg>
          Design Document
        </h3>
        <div className="p-4 rounded-lg bg-yellow-900/20 border border-yellow-800">
          <div className="flex items-start gap-3">
            <span className="text-yellow-400 text-xl">
              <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
              </svg>
            </span>
            <div className="flex-1">
              <p className="text-yellow-300 font-medium">No file linked</p>
              <p className="text-yellow-400/70 text-sm mt-1">
                A new design document will be created when you complete this planning step.
              </p>
            </div>
          </div>

          {stepStatus === 'pending' && availableFiles.length > 0 && (
            <div className="mt-4 relative">
              <button
                onClick={() => setShowLinkDropdown(!showLinkDropdown)}
                className="px-3 py-2 bg-yellow-600/30 text-yellow-300 rounded hover:bg-yellow-600/40 transition-colors text-sm flex items-center gap-1"
              >
                Link Existing File
                <svg className={`w-4 h-4 transition-transform ${showLinkDropdown ? 'rotate-180' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                </svg>
              </button>

              {showLinkDropdown && (
                <div className="absolute top-full left-0 mt-1 w-64 bg-gray-800 border border-gray-700 rounded-lg shadow-xl z-10 max-h-48 overflow-y-auto">
                  {availableFiles.map((file) => (
                    <button
                      key={file.path}
                      onClick={() => {
                        onLinkFile?.(file.name)
                        setShowLinkDropdown(false)
                      }}
                      className="w-full px-3 py-2 text-left text-sm hover:bg-gray-700 flex items-center gap-2"
                    >
                      <svg className="w-4 h-4 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                      </svg>
                      <span className="flex-1 truncate text-gray-200">{file.name}</span>
                      <span className="text-gray-500">{formatSize(file.size)}</span>
                    </button>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    )
  }

  // File was deleted state
  if (!fileExists) {
    return (
      <div className="card mb-4">
        <h3 className="text-lg font-semibold text-white mb-3 flex items-center gap-2">
          <svg className="w-5 h-5 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
          </svg>
          Design Document
        </h3>
        <div className="p-4 rounded-lg bg-red-900/20 border border-red-800">
          <div className="flex items-start gap-3">
            <span className="text-red-400 text-xl">
              <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </span>
            <div className="flex-1">
              <p className="text-red-300 font-medium">File not found: {designDocPath}</p>
              <p className="text-red-400/70 text-sm mt-1">
                The linked file no longer exists. It may have been deleted or moved.
              </p>
            </div>
          </div>

          {backups.length > 0 && (
            <div className="mt-4 flex gap-2 flex-wrap">
              <select
                className="px-3 py-2 bg-gray-800 border border-gray-700 rounded text-sm text-gray-200"
                onChange={(e) => {
                  if (e.target.value) handleRestore(e.target.value)
                }}
                defaultValue=""
              >
                <option value="" disabled>Restore from backup...</option>
                {backups.map((backup) => (
                  <option key={backup.name} value={backup.name}>
                    {backup.name} ({formatSize(backup.size)})
                  </option>
                ))}
              </select>

              <button
                onClick={() => {
                  onLinkFile?.('')
                  loadAvailableFiles()
                  setShowLinkDropdown(true)
                }}
                className="px-3 py-2 bg-gray-700 text-gray-300 rounded hover:bg-gray-600 text-sm"
              >
                Link Different File
              </button>
            </div>
          )}
        </div>
      </div>
    )
  }

  // Normal state - file exists
  return (
    <div className="card mb-4">
      <h3 className="text-lg font-semibold text-white mb-3 flex items-center gap-2">
        <svg className="w-5 h-5 text-primary-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
        </svg>
        Design Document
      </h3>

      {/* File Info */}
      <div className="p-4 rounded-lg bg-gray-800/50 border border-gray-700">
        <div className="flex items-start justify-between">
          <div>
            <p className="text-white font-medium">{designDocPath}</p>
            <p className="text-gray-400 text-sm mt-1">
              {formatSize(fileInfo?.size || 0)} {' '} Last modified: {formatDate(fileInfo?.modified || '')}
            </p>
          </div>
          <div className="flex gap-2">
            <button
              onClick={() => setShowContent(true)}
              className="px-3 py-1.5 bg-primary-600 text-white rounded text-sm hover:bg-primary-500 transition-colors"
            >
              View Document
            </button>
          </div>
        </div>

        {/* Version History */}
        {backups.length > 0 && (
          <div className="mt-4">
            <p className="text-gray-400 text-sm mb-2 flex items-center gap-2">
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              Version History ({backups.length} backup{backups.length !== 1 ? 's' : ''})
            </p>
            <div className="space-y-1 max-h-32 overflow-y-auto">
              <div className="flex items-center justify-between px-2 py-1 bg-green-900/20 rounded text-sm">
                <span className="text-green-400">Current</span>
                <span className="text-gray-400">{formatSize(fileInfo?.size || 0)}</span>
                <span className="text-gray-500">{formatDate(fileInfo?.modified || '')}</span>
                <span className="w-6"></span>
              </div>
              {backups.map((backup, index) => (
                <div key={backup.name} className="flex items-center justify-between px-2 py-1 hover:bg-gray-700/50 rounded text-sm">
                  <span className="text-gray-300">Backup #{backups.length - index}</span>
                  <span className="text-gray-400">{formatSize(backup.size)}</span>
                  <span className="text-gray-500">{formatDate(backup.created)}</span>
                  <button
                    onClick={() => {
                      setDiffLeft(backup.name)
                      setDiffRight('current')
                      setShowCompare(true)
                    }}
                    className="text-cyan-400 hover:text-cyan-300"
                    title="Compare with current"
                  >
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 7h12m0 0l-4-4m4 4l-4 4m0 6H4m0 0l4 4m-4-4l4-4" />
                    </svg>
                  </button>
                </div>
              ))}
            </div>

            <button
              onClick={() => setShowCompare(true)}
              className="mt-2 px-3 py-1.5 bg-gray-700 text-gray-300 rounded text-sm hover:bg-gray-600 transition-colors"
            >
              Compare Versions
            </button>
          </div>
        )}
      </div>

      {/* View Document Modal */}
      {showContent && fileInfo?.content && (
        <ViewDocumentModal
          content={fileInfo.content}
          fileName={designDocPath}
          onClose={() => setShowContent(false)}
        />
      )}

      {/* Compare Versions Modal */}
      {showCompare && (
        <CompareVersionsModal
          backups={backups}
          currentSize={fileInfo?.size || 0}
          diffResult={diffResult}
          diffLeft={diffLeft}
          diffRight={diffRight}
          loadingDiff={loadingDiff}
          onLeftChange={setDiffLeft}
          onRightChange={setDiffRight}
          onCompare={handleCompare}
          onClose={() => {
            setShowCompare(false)
            setDiffResult(null)
          }}
        />
      )}
    </div>
  )
}

// Sub-components
interface ViewDocumentModalProps {
  content: string
  fileName: string
  onClose: () => void
}

function ViewDocumentModal({ content, fileName, onClose }: ViewDocumentModalProps) {
  // Close on Escape key
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [onClose])

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4" onClick={onClose}>
      <div className="bg-gray-800 rounded-lg w-full max-w-4xl max-h-[90vh] flex flex-col" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between p-4 border-b border-gray-700">
          <h3 className="text-lg font-semibold text-white">{fileName}</h3>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-white"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
        <div className="flex-1 overflow-auto p-4">
          <pre className="text-sm text-gray-300 whitespace-pre-wrap font-mono">{content}</pre>
        </div>
        <div className="p-4 border-t border-gray-700 flex justify-end">
          <button
            onClick={onClose}
            className="px-4 py-2 bg-gray-700 text-white rounded hover:bg-gray-600 transition-colors"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  )
}

interface CompareVersionsModalProps {
  backups: DesignDocBackup[]
  currentSize: number
  diffResult: DiffResult | null
  diffLeft: string
  diffRight: string
  loadingDiff: boolean
  onLeftChange: (value: string) => void
  onRightChange: (value: string) => void
  onCompare: () => void
  onClose: () => void
}

function CompareVersionsModal({
  backups,
  currentSize,
  diffResult,
  diffLeft,
  diffRight,
  loadingDiff,
  onLeftChange,
  onRightChange,
  onCompare,
  onClose,
}: CompareVersionsModalProps) {
  // Close on Escape key
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [onClose])

  const formatSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`
    return `${(bytes / 1024).toFixed(1)} KB`
  }

  const formatDate = (dateStr: string) => {
    if (!dateStr) return 'Unknown'
    const date = new Date(dateStr)
    if (isNaN(date.getTime())) return 'Unknown'
    return date.toLocaleString()
  }

  const getDiffLineClass = (type: string) => {
    switch (type) {
      case 'add':
        return 'bg-green-900/30 text-green-300'
      case 'remove':
        return 'bg-red-900/30 text-red-300'
      case 'hunk':
        return 'bg-blue-900/30 text-blue-300'
      default:
        return 'text-gray-400'
    }
  }

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4" onClick={onClose}>
      <div className="bg-gray-800 rounded-lg w-full max-w-4xl max-h-[90vh] flex flex-col" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between p-4 border-b border-gray-700">
          <h3 className="text-lg font-semibold text-white">Compare Versions</h3>
          <button onClick={onClose} className="text-gray-400 hover:text-white">
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        <div className="p-4 border-b border-gray-700">
          <div className="flex items-center gap-4 flex-wrap">
            <div className="flex-1 min-w-[200px]">
              <label className="block text-sm text-gray-400 mb-1">Left (older)</label>
              <select
                value={diffLeft}
                onChange={(e) => onLeftChange(e.target.value)}
                className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded text-white"
              >
                <option value="">Select version...</option>
                {backups.map((backup, index) => (
                  <option key={backup.name} value={backup.name}>
                    Backup #{backups.length - index} - {formatDate(backup.created)} ({formatSize(backup.size)})
                  </option>
                ))}
              </select>
            </div>

            <div className="text-gray-500">
              <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 7h12m0 0l-4-4m4 4l-4 4m0 6H4m0 0l4 4m-4-4l4-4" />
              </svg>
            </div>

            <div className="flex-1 min-w-[200px]">
              <label className="block text-sm text-gray-400 mb-1">Right (newer)</label>
              <select
                value={diffRight}
                onChange={(e) => onRightChange(e.target.value)}
                className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded text-white"
              >
                <option value="current">Current ({formatSize(currentSize)})</option>
                {backups.map((backup, index) => (
                  <option key={backup.name} value={backup.name}>
                    Backup #{backups.length - index} - {formatDate(backup.created)} ({formatSize(backup.size)})
                  </option>
                ))}
              </select>
            </div>

            <button
              onClick={onCompare}
              disabled={!diffLeft || loadingDiff}
              className="px-4 py-2 bg-primary-600 text-white rounded hover:bg-primary-500 transition-colors disabled:opacity-50"
            >
              {loadingDiff ? 'Comparing...' : 'Compare'}
            </button>
          </div>
        </div>

        <div className="flex-1 overflow-auto p-4">
          {!diffResult && !loadingDiff && (
            <div className="text-center py-12 text-gray-500">
              Select two versions and click Compare to see differences
            </div>
          )}

          {loadingDiff && (
            <div className="flex items-center justify-center py-12">
              <div className="animate-spin w-6 h-6 border-2 border-primary-400 border-t-transparent rounded-full" />
              <span className="ml-2 text-gray-400">Generating diff...</span>
            </div>
          )}

          {diffResult && (
            <div>
              <div className="mb-4 flex items-center gap-4 text-sm">
                <span className="text-green-400">+{diffResult.chars_added.toLocaleString()} chars added</span>
                <span className="text-red-400">-{diffResult.chars_removed.toLocaleString()} chars removed</span>
              </div>
              <div className="bg-gray-900 rounded-lg overflow-hidden">
                <div className="overflow-x-auto">
                  <pre className="text-sm font-mono">
                    {diffResult.diff_lines.map((line, index) => (
                      <div
                        key={index}
                        className={`px-3 py-0.5 ${getDiffLineClass(line.type)}`}
                      >
                        {line.line}
                      </div>
                    ))}
                  </pre>
                </div>
              </div>
            </div>
          )}
        </div>

        <div className="p-4 border-t border-gray-700 flex justify-end">
          <button
            onClick={onClose}
            className="px-4 py-2 bg-gray-700 text-white rounded hover:bg-gray-600 transition-colors"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  )
}
