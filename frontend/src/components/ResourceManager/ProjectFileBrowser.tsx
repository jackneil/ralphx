import { useEffect, useState, useCallback } from 'react'
import {
  browseProjectFiles,
  readProjectFile,
  BrowseFilesResponse,
  ProjectFile,
} from '../../api'

interface ProjectFileBrowserProps {
  projectSlug: string
  onSelect: (file: { path: string; content: string; filename: string }) => void
  onClose: () => void
}

export default function ProjectFileBrowser({
  projectSlug,
  onSelect,
  onClose,
}: ProjectFileBrowserProps) {
  // Browser state
  const [currentPath, setCurrentPath] = useState('')
  const [browseData, setBrowseData] = useState<BrowseFilesResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Selected file state
  const [selectedFile, setSelectedFile] = useState<ProjectFile | null>(null)
  const [fileContent, setFileContent] = useState<string | null>(null)
  const [loadingFile, setLoadingFile] = useState(false)
  const [fileError, setFileError] = useState<string | null>(null)

  // Load directory contents
  const loadDirectory = useCallback(async (path: string) => {
    setLoading(true)
    setError(null)
    try {
      const result = await browseProjectFiles(projectSlug, path || undefined)
      setBrowseData(result)
      setCurrentPath(result.relative_path)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to browse directory')
    } finally {
      setLoading(false)
    }
  }, [projectSlug])

  // Initial load
  useEffect(() => {
    loadDirectory('')
  }, [loadDirectory])

  // Navigate to directory
  const handleNavigate = (dirName: string) => {
    const newPath = currentPath ? `${currentPath}/${dirName}` : dirName
    setSelectedFile(null)
    setFileContent(null)
    loadDirectory(newPath)
  }

  // Go up to parent
  const handleGoUp = () => {
    if (browseData?.parent !== null && browseData?.parent !== undefined) {
      setSelectedFile(null)
      setFileContent(null)
      loadDirectory(browseData.parent)
    }
  }

  // Select file and load preview
  const handleSelectFile = async (file: ProjectFile) => {
    setSelectedFile(file)
    setFileContent(null)
    setFileError(null)
    setLoadingFile(true)

    try {
      const filePath = currentPath ? `${currentPath}/${file.name}` : file.name
      const result = await readProjectFile(projectSlug, filePath)
      setFileContent(result.content)
    } catch (err) {
      setFileError(err instanceof Error ? err.message : 'Failed to load file')
    } finally {
      setLoadingFile(false)
    }
  }

  // Confirm selection
  const handleConfirm = () => {
    if (selectedFile && fileContent !== null) {
      const filePath = currentPath ? `${currentPath}/${selectedFile.name}` : selectedFile.name
      onSelect({
        path: filePath,
        content: fileContent,
        filename: selectedFile.name,
      })
    }
  }

  // Format file size
  const formatSize = (bytes: number): string => {
    if (bytes < 1024) return `${bytes} B`
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
  }

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
      <div className="bg-gray-800 rounded-lg w-full max-w-5xl h-[80vh] flex flex-col">
        {/* Header */}
        <div className="p-4 border-b border-gray-700 flex items-center justify-between">
          <div>
            <h3 className="text-lg font-semibold text-white">Import File from Project</h3>
            <div className="mt-1 text-sm text-gray-400 font-mono">
              {currentPath ? `/${currentPath}` : '/ (project root)'}
            </div>
          </div>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-white"
            aria-label="Close"
          >
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Content - Split Pane */}
        <div className="flex-1 flex overflow-hidden">
          {/* Left Pane - File Browser */}
          <div className="w-1/2 border-r border-gray-700 flex flex-col">
            <div className="p-2 border-b border-gray-700 text-xs text-gray-500 uppercase tracking-wider">
              Files & Folders
            </div>
            <div className="flex-1 overflow-auto p-2">
              {loading ? (
                <div className="flex items-center justify-center p-8">
                  <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-primary-500" />
                </div>
              ) : error ? (
                <div className="p-4 text-center text-red-400">{error}</div>
              ) : (
                <div className="space-y-0.5">
                  {/* Go Up */}
                  {browseData?.canGoUp && (
                    <button
                      onClick={handleGoUp}
                      className="w-full flex items-center space-x-2 px-3 py-2 rounded hover:bg-gray-700 text-left"
                    >
                      <svg
                        className="w-4 h-4 text-gray-400"
                        fill="none"
                        stroke="currentColor"
                        viewBox="0 0 24 24"
                      >
                        <path
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          strokeWidth={2}
                          d="M11 17l-5-5m0 0l5-5m-5 5h12"
                        />
                      </svg>
                      <span className="text-gray-400">..</span>
                    </button>
                  )}

                  {/* Directories */}
                  {browseData?.directories.map((dir) => (
                    <button
                      key={`dir-${dir}`}
                      onClick={() => handleNavigate(dir)}
                      className="w-full flex items-center space-x-2 px-3 py-2 rounded hover:bg-gray-700 text-left"
                    >
                      <svg
                        className="w-4 h-4 text-yellow-500"
                        fill="currentColor"
                        viewBox="0 0 20 20"
                      >
                        <path d="M2 6a2 2 0 012-2h5l2 2h5a2 2 0 012 2v6a2 2 0 01-2 2H4a2 2 0 01-2-2V6z" />
                      </svg>
                      <span className="text-gray-200">{dir}</span>
                    </button>
                  ))}

                  {/* Files */}
                  {browseData?.files.map((file) => (
                    <button
                      key={`file-${file.name}`}
                      onClick={() => handleSelectFile(file)}
                      className={`w-full flex items-center justify-between px-3 py-2 rounded text-left transition-colors ${
                        selectedFile?.name === file.name
                          ? 'bg-primary-600/30 border border-primary-500'
                          : 'hover:bg-gray-700 border border-transparent'
                      }`}
                    >
                      <div className="flex items-center space-x-2 min-w-0">
                        <svg
                          className="w-4 h-4 text-gray-400 flex-shrink-0"
                          fill="none"
                          stroke="currentColor"
                          viewBox="0 0 24 24"
                        >
                          <path
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            strokeWidth={2}
                            d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
                          />
                        </svg>
                        <span className="text-gray-200 truncate">{file.name}</span>
                      </div>
                      <span className="text-xs text-gray-500 flex-shrink-0 ml-2">
                        {formatSize(file.size)}
                      </span>
                    </button>
                  ))}

                  {/* Empty State */}
                  {browseData?.directories.length === 0 &&
                   browseData?.files.length === 0 && (
                    <div className="p-8 text-center text-gray-500">
                      <p>No visible files or directories</p>
                      {(browseData?.hidden_count > 0 || browseData?.other_files_count > 0) && (
                        <div className="text-xs mt-2 space-y-1">
                          {browseData.hidden_count > 0 && (
                            <p>{browseData.hidden_count} hidden item(s) filtered out</p>
                          )}
                          {browseData.other_files_count > 0 && (
                            <p>{browseData.other_files_count} file(s) with unsupported extensions</p>
                          )}
                        </div>
                      )}
                    </div>
                  )}

                  {/* Filtering Info (when some files are shown) */}
                  {browseData &&
                   (browseData.files.length > 0 || browseData.directories.length > 0) &&
                   (browseData.hidden_count > 0 || browseData.other_files_count > 0) && (
                    <div className="mt-2 p-2 text-xs text-gray-500 border-t border-gray-700">
                      {browseData.hidden_count > 0 && (
                        <span>{browseData.hidden_count} hidden </span>
                      )}
                      {browseData.hidden_count > 0 && browseData.other_files_count > 0 && (
                        <span>+ </span>
                      )}
                      {browseData.other_files_count > 0 && (
                        <span>{browseData.other_files_count} unsupported </span>
                      )}
                      <span>item(s) filtered</span>
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>

          {/* Right Pane - Preview */}
          <div className="w-1/2 flex flex-col bg-gray-900/50">
            <div className="p-2 border-b border-gray-700 text-xs text-gray-500 uppercase tracking-wider">
              Preview
            </div>
            <div className="flex-1 overflow-auto">
              {!selectedFile ? (
                <div className="flex items-center justify-center h-full text-gray-500">
                  <div className="text-center">
                    <svg
                      className="w-12 h-12 mx-auto mb-3 text-gray-600"
                      fill="none"
                      stroke="currentColor"
                      viewBox="0 0 24 24"
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={1.5}
                        d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"
                      />
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={1.5}
                        d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z"
                      />
                    </svg>
                    <p>Select a file to preview</p>
                  </div>
                </div>
              ) : loadingFile ? (
                <div className="flex items-center justify-center h-full">
                  <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary-500" />
                </div>
              ) : fileError ? (
                <div className="p-4 text-red-400">
                  <p className="font-medium">Failed to load file</p>
                  <p className="text-sm mt-1">{fileError}</p>
                </div>
              ) : (
                <div className="h-full flex flex-col">
                  {/* File Info */}
                  <div className="p-3 bg-gray-800/50 border-b border-gray-700">
                    <div className="font-medium text-white">{selectedFile.name}</div>
                    <div className="text-xs text-gray-500 mt-1">
                      {formatSize(selectedFile.size)} | {selectedFile.extension.toUpperCase()}
                    </div>
                  </div>
                  {/* Content */}
                  <pre className="flex-1 p-4 text-sm text-gray-300 overflow-auto whitespace-pre-wrap font-mono">
                    {fileContent}
                  </pre>
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="p-4 border-t border-gray-700 flex items-center justify-between">
          <div className="text-sm text-gray-500">
            {selectedFile ? (
              <span>
                Selected: <span className="text-gray-300">{selectedFile.name}</span>
              </span>
            ) : (
              <span>Click a file to preview it</span>
            )}
          </div>
          <div className="flex space-x-3">
            <button
              onClick={onClose}
              className="px-4 py-2 text-sm rounded bg-gray-700 text-gray-300 hover:bg-gray-600"
            >
              Cancel
            </button>
            <button
              onClick={handleConfirm}
              disabled={!selectedFile || fileContent === null || loadingFile}
              className="px-4 py-2 text-sm rounded bg-primary-600 text-white hover:bg-primary-500 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              Add as Resource
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
