import { useEffect, useState } from 'react'
import { browseDirectory } from '../api'

interface DirectoryBrowserProps {
  initialPath?: string
  onSelect: (path: string) => void
  onCancel: () => void
}

export default function DirectoryBrowser({
  initialPath,
  onSelect,
  onCancel,
}: DirectoryBrowserProps) {
  const [currentPath, setCurrentPath] = useState(initialPath || '')
  const [directories, setDirectories] = useState<string[]>([])
  const [canGoUp, setCanGoUp] = useState(false)
  const [parentPath, setParentPath] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    async function load() {
      setLoading(true)
      setError(null)
      try {
        const result = await browseDirectory(currentPath || undefined)
        setCurrentPath(result.path)
        setDirectories(result.directories)
        setCanGoUp(result.canGoUp)
        setParentPath(result.parent)
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to browse directory')
      } finally {
        setLoading(false)
      }
    }
    load()
  }, [currentPath])

  const handleNavigate = (dirName: string) => {
    setCurrentPath(`${currentPath}/${dirName}`)
  }

  const handleGoUp = () => {
    if (parentPath) {
      setCurrentPath(parentPath)
    }
  }

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
      <div className="bg-gray-800 rounded-lg w-full max-w-lg max-h-[80vh] flex flex-col">
        {/* Header */}
        <div className="p-4 border-b border-gray-700">
          <h3 className="text-lg font-semibold text-white">Select Directory</h3>
          <div className="mt-2 text-sm text-gray-400 font-mono truncate">
            {currentPath}
          </div>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-auto p-2">
          {loading ? (
            <div className="p-4 text-center text-gray-400">Loading...</div>
          ) : error ? (
            <div className="p-4 text-center text-red-400">{error}</div>
          ) : (
            <div className="space-y-1">
              {/* Go Up */}
              {canGoUp && (
                <button
                  onClick={handleGoUp}
                  className="w-full flex items-center space-x-2 px-3 py-2 rounded hover:bg-gray-700 text-left"
                >
                  <svg
                    className="w-5 h-5 text-gray-400"
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
                  <span className="text-gray-300">..</span>
                </button>
              )}

              {/* Directories */}
              {directories.length === 0 && !canGoUp ? (
                <div className="p-4 text-center text-gray-500">No subdirectories</div>
              ) : (
                directories.map((dir) => (
                  <button
                    key={dir}
                    onClick={() => handleNavigate(dir)}
                    className="w-full flex items-center space-x-2 px-3 py-2 rounded hover:bg-gray-700 text-left"
                  >
                    <svg
                      className="w-5 h-5 text-primary-400"
                      fill="none"
                      stroke="currentColor"
                      viewBox="0 0 24 24"
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={2}
                        d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z"
                      />
                    </svg>
                    <span className="text-gray-200">{dir}</span>
                  </button>
                ))
              )}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="p-4 border-t border-gray-700 flex justify-end space-x-3">
          <button
            onClick={onCancel}
            className="px-4 py-2 text-sm rounded bg-gray-700 text-gray-300 hover:bg-gray-600"
          >
            Cancel
          </button>
          <button
            onClick={() => onSelect(currentPath)}
            className="px-4 py-2 text-sm rounded bg-primary-600 text-white hover:bg-primary-500"
          >
            Select This Folder
          </button>
        </div>
      </div>
    </div>
  )
}
