import { useState, useRef, useEffect, useCallback } from 'react'
import { createSimpleLoop, browseProjectFiles, readProjectFile, type SimpleLoopRequest } from '../api'

interface SimpleLoopWizardProps {
  projectSlug: string
  availableLoops: string[]
  onClose: () => void
  onCreated: (loopName: string) => void
  onAdvanced: () => void
}

type WizardStep = 'choose-type' | 'planning-setup' | 'implementation-setup' | 'creating'

interface FileSelection {
  content: string
  filename: string
}

export default function SimpleLoopWizard({
  projectSlug,
  availableLoops,
  onClose,
  onCreated,
  onAdvanced,
}: SimpleLoopWizardProps) {
  const [step, setStep] = useState<WizardStep>('choose-type')
  const [loopType, setLoopType] = useState<'planning' | 'implementation' | null>(null)
  const [displayName, setDisplayName] = useState('')
  const [description, setDescription] = useState('')
  const [error, setError] = useState<string | null>(null)

  // Planning state
  const [designDoc, setDesignDoc] = useState<FileSelection | null>(null)
  const [useDefaultInstructions, setUseDefaultInstructions] = useState(true)
  const [useDefaultGuardrails, setUseDefaultGuardrails] = useState(true)

  // Implementation state
  const [storiesSourceType, setStoriesSourceType] = useState<'loop' | 'upload'>('loop')
  const [sourceLoopName, setSourceLoopName] = useState('')
  const [storiesFile, setStoriesFile] = useState<FileSelection | null>(null)
  const [designContext, setDesignContext] = useState<FileSelection | null>(null)
  const [useCodeGuardrails, setUseCodeGuardrails] = useState(true)

  // File browser state
  const [showFileBrowser, setShowFileBrowser] = useState(false)
  const [fileBrowserTarget, setFileBrowserTarget] = useState<'design' | 'context' | 'stories' | null>(null)
  const [browserPath, setBrowserPath] = useState('')
  const [browserFiles, setBrowserFiles] = useState<{ name: string; size: number; extension: string }[]>([])
  const [browserDirs, setBrowserDirs] = useState<string[]>([])
  const [browserCanGoUp, setBrowserCanGoUp] = useState(false)
  const [browserParent, setBrowserParent] = useState<string | null>(null)
  const [loadingBrowser, setLoadingBrowser] = useState(false)
  const [browserError, setBrowserError] = useState<string | null>(null)

  // Paste modal state
  const [showPasteModal, setShowPasteModal] = useState(false)
  const [pasteTarget, setPasteTarget] = useState<'design' | 'context' | 'stories' | null>(null)
  const [pasteContent, setPasteContent] = useState('')
  const [pasteFilename, setPasteFilename] = useState('')

  const fileInputRef = useRef<HTMLInputElement>(null)

  // Handle Escape key to close modal (when not creating)
  const handleEscapeKey = useCallback((e: KeyboardEvent) => {
    if (e.key === 'Escape' && step !== 'creating') {
      // Close sub-modals first if open
      if (showFileBrowser) {
        setShowFileBrowser(false)
      } else if (showPasteModal) {
        setShowPasteModal(false)
      } else {
        onClose()
      }
    }
  }, [step, showFileBrowser, showPasteModal, onClose])

  useEffect(() => {
    document.addEventListener('keydown', handleEscapeKey)
    return () => document.removeEventListener('keydown', handleEscapeKey)
  }, [handleEscapeKey])

  const handleSelectType = (type: 'planning' | 'implementation') => {
    setLoopType(type)
    setDisplayName(type === 'planning' ? 'Planning' : 'Implementation')
    setStep(type === 'planning' ? 'planning-setup' : 'implementation-setup')
  }

  const handleBack = () => {
    setStep('choose-type')
    setLoopType(null)
    setError(null)
  }

  const openFileBrowser = async (target: 'design' | 'context' | 'stories') => {
    setFileBrowserTarget(target)
    setShowFileBrowser(true)
    setLoadingBrowser(true)
    setBrowserError(null)
    try {
      const result = await browseProjectFiles(projectSlug)
      setBrowserPath(result.relative_path || '')
      setBrowserFiles(result.files)
      setBrowserDirs(result.directories)
      setBrowserCanGoUp(result.canGoUp)
      setBrowserParent(result.parent)
    } catch (err) {
      setBrowserError(err instanceof Error ? err.message : 'Failed to browse files')
    } finally {
      setLoadingBrowser(false)
    }
  }

  const navigateToDir = async (dir: string) => {
    setLoadingBrowser(true)
    setBrowserError(null)
    try {
      const newPath = browserPath ? `${browserPath}/${dir}` : dir
      const result = await browseProjectFiles(projectSlug, newPath)
      setBrowserPath(result.relative_path || newPath)
      setBrowserFiles(result.files)
      setBrowserDirs(result.directories)
      setBrowserCanGoUp(result.canGoUp)
      setBrowserParent(result.parent)
    } catch (err) {
      setBrowserError(err instanceof Error ? err.message : 'Failed to navigate')
    } finally {
      setLoadingBrowser(false)
    }
  }

  const navigateUp = async () => {
    if (browserParent !== null) {
      setLoadingBrowser(true)
      setBrowserError(null)
      try {
        const result = await browseProjectFiles(projectSlug, browserParent || undefined)
        setBrowserPath(result.relative_path || '')
        setBrowserFiles(result.files)
        setBrowserDirs(result.directories)
        setBrowserCanGoUp(result.canGoUp)
        setBrowserParent(result.parent)
      } catch (err) {
        setBrowserError(err instanceof Error ? err.message : 'Failed to navigate')
      } finally {
        setLoadingBrowser(false)
      }
    }
  }

  const selectFile = async (filename: string) => {
    setLoadingBrowser(true)
    setBrowserError(null)
    try {
      const filePath = browserPath ? `${browserPath}/${filename}` : filename
      const result = await readProjectFile(projectSlug, filePath)
      const selection: FileSelection = {
        content: result.content,
        filename: result.filename,
      }
      if (fileBrowserTarget === 'design') {
        setDesignDoc(selection)
      } else if (fileBrowserTarget === 'context') {
        setDesignContext(selection)
      } else if (fileBrowserTarget === 'stories') {
        setStoriesFile(selection)
      }
      setShowFileBrowser(false)
    } catch (err) {
      setBrowserError(err instanceof Error ? err.message : 'Failed to read file')
    } finally {
      setLoadingBrowser(false)
    }
  }

  const openPasteModal = (target: 'design' | 'context' | 'stories') => {
    setPasteTarget(target)
    setPasteContent('')
    setPasteFilename(target === 'stories' ? 'stories.jsonl' : 'design.md')
    setShowPasteModal(true)
  }

  const handlePaste = () => {
    if (!pasteContent || !pasteFilename) return
    const selection: FileSelection = {
      content: pasteContent,
      filename: pasteFilename,
    }
    if (pasteTarget === 'design') {
      setDesignDoc(selection)
    } else if (pasteTarget === 'context') {
      setDesignContext(selection)
    } else if (pasteTarget === 'stories') {
      setStoriesFile(selection)
    }
    setShowPasteModal(false)
  }

  const handleFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    const reader = new FileReader()
    reader.onload = () => {
      setStoriesFile({
        content: reader.result as string,
        filename: file.name,
      })
    }
    reader.readAsText(file)
    e.target.value = ''
  }

  const handleCreate = async () => {
    setStep('creating')
    setError(null)

    try {
      const request: SimpleLoopRequest = {
        type: loopType!,
        display_name: displayName || undefined,
        description: description || undefined,
      }

      if (loopType === 'planning') {
        if (designDoc) {
          request.design_doc = designDoc
        }
        request.use_default_instructions = useDefaultInstructions
        request.use_default_guardrails = useDefaultGuardrails
      } else {
        if (storiesSourceType === 'loop' && sourceLoopName) {
          request.stories_source = {
            type: 'loop',
            loop_name: sourceLoopName,
          }
        } else if (storiesSourceType === 'upload' && storiesFile) {
          request.stories_source = {
            type: 'content',
            content: storiesFile.content,
            filename: storiesFile.filename,
          }
        }
        if (designContext) {
          request.design_context = designContext
        }
        request.use_code_guardrails = useCodeGuardrails
      }

      const result = await createSimpleLoop(projectSlug, request)
      onCreated(result.loop_id)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create loop')
      setStep(loopType === 'planning' ? 'planning-setup' : 'implementation-setup')
    }
  }

  const canCreate = () => {
    // ID is auto-generated, so we just check implementation source requirements
    if (loopType === 'implementation') {
      if (storiesSourceType === 'loop' && !sourceLoopName) return false
      if (storiesSourceType === 'upload' && !storiesFile) return false
    }
    return true
  }

  // Filter to show available loops for implementation source
  const generatorLoops = availableLoops

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
      <div className="bg-gray-800 rounded-lg w-full max-w-lg mx-4">
        {/* Header */}
        <div className="p-4 border-b border-gray-700 flex justify-between items-center">
          <div>
            <h3 className="text-lg font-semibold text-white">
              {step === 'choose-type' && 'Create Loop'}
              {step === 'planning-setup' && 'Planning Loop Setup'}
              {step === 'implementation-setup' && 'Implementation Loop Setup'}
              {step === 'creating' && 'Creating Loop...'}
            </h3>
          </div>
          <button
            onClick={onClose}
            disabled={step === 'creating'}
            className="p-1 text-gray-400 hover:text-white disabled:opacity-50 disabled:cursor-not-allowed"
            aria-label="Close"
          >
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Content */}
        <div className="p-4">
          {error && (
            <div className="mb-4 p-3 bg-red-900/30 border border-red-800 rounded text-sm text-red-400 flex justify-between items-start">
              <span>{error}</span>
              <button
                onClick={() => setError(null)}
                className="ml-2 text-red-400 hover:text-red-300 flex-shrink-0"
                aria-label="Dismiss error"
              >
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
          )}

          {/* Step: Choose Type */}
          {step === 'choose-type' && (
            <div className="space-y-4">
              <p className="text-gray-400 text-sm">What do you want to do?</p>
              <div className="grid grid-cols-2 gap-4">
                <button
                  onClick={() => handleSelectType('planning')}
                  className="p-4 bg-gray-700 rounded-lg hover:bg-gray-600 text-left transition-colors border border-transparent hover:border-primary-500"
                >
                  <div className="text-2xl mb-2">📝</div>
                  <div className="font-medium text-white">Planning</div>
                  <div className="text-sm text-gray-400 mt-1">
                    Generate user stories from design docs
                  </div>
                </button>
                <button
                  onClick={() => handleSelectType('implementation')}
                  className="p-4 bg-gray-700 rounded-lg hover:bg-gray-600 text-left transition-colors border border-transparent hover:border-primary-500"
                >
                  <div className="text-2xl mb-2">🔨</div>
                  <div className="font-medium text-white">Implementation</div>
                  <div className="text-sm text-gray-400 mt-1">
                    Implement stories as working code
                  </div>
                </button>
              </div>
              <div className="pt-4 border-t border-gray-700">
                <button
                  onClick={onAdvanced}
                  className="text-sm text-gray-400 hover:text-primary-400"
                >
                  Need more control? Advanced Options →
                </button>
              </div>
            </div>
          )}

          {/* Step: Planning Setup */}
          {step === 'planning-setup' && (
            <div className="space-y-4">
              <div>
                <label htmlFor="planning-display-name" className="block text-sm font-medium text-gray-300 mb-1">
                  Name
                </label>
                <input
                  id="planning-display-name"
                  type="text"
                  value={displayName}
                  onChange={(e) => setDisplayName(e.target.value)}
                  className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded text-white"
                  placeholder="Planning"
                />
              </div>

              <div>
                <label htmlFor="planning-description" className="block text-sm font-medium text-gray-300 mb-1">
                  Description <span className="text-gray-500">(optional)</span>
                </label>
                <input
                  id="planning-description"
                  type="text"
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded text-white"
                  placeholder="Generate stories for the RCM module"
                />
              </div>

              <div className="border-t border-gray-700 pt-4">
                <label className="block text-sm font-medium text-gray-300 mb-2">
                  📄 Design Document
                </label>
                {designDoc ? (
                  <div className="flex items-center justify-between p-3 bg-gray-700 rounded">
                    <span className="text-white">{designDoc.filename}</span>
                    <button
                      onClick={() => setDesignDoc(null)}
                      className="text-gray-400 hover:text-red-400"
                    >
                      Remove
                    </button>
                  </div>
                ) : (
                  <div className="flex space-x-2">
                    <button
                      onClick={() => openFileBrowser('design')}
                      className="flex-1 px-3 py-2 bg-gray-700 border border-gray-600 rounded text-gray-300 hover:bg-gray-600"
                    >
                      Browse from Project
                    </button>
                    <button
                      onClick={() => openPasteModal('design')}
                      className="flex-1 px-3 py-2 bg-gray-700 border border-gray-600 rounded text-gray-300 hover:bg-gray-600"
                    >
                      Paste Content
                    </button>
                  </div>
                )}
              </div>

              <div className="border-t border-gray-700 pt-4 space-y-2">
                <label className="block text-sm font-medium text-gray-300 mb-2">
                  Optional
                </label>
                <label className="flex items-center space-x-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={useDefaultInstructions}
                    onChange={(e) => setUseDefaultInstructions(e.target.checked)}
                    className="rounded bg-gray-700 border-gray-600"
                  />
                  <span className="text-gray-300 text-sm">Use default story instructions</span>
                </label>
                <label className="flex items-center space-x-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={useDefaultGuardrails}
                    onChange={(e) => setUseDefaultGuardrails(e.target.checked)}
                    className="rounded bg-gray-700 border-gray-600"
                  />
                  <span className="text-gray-300 text-sm">Use default guardrails</span>
                </label>
              </div>
            </div>
          )}

          {/* Step: Implementation Setup */}
          {step === 'implementation-setup' && (
            <div className="space-y-4">
              <div>
                <label htmlFor="impl-display-name" className="block text-sm font-medium text-gray-300 mb-1">
                  Name
                </label>
                <input
                  id="impl-display-name"
                  type="text"
                  value={displayName}
                  onChange={(e) => setDisplayName(e.target.value)}
                  className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded text-white"
                  placeholder="Implementation"
                />
              </div>

              <div>
                <label htmlFor="impl-description" className="block text-sm font-medium text-gray-300 mb-1">
                  Description <span className="text-gray-500">(optional)</span>
                </label>
                <input
                  id="impl-description"
                  type="text"
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded text-white"
                  placeholder="Implement RCM stories"
                />
              </div>

              <div className="border-t border-gray-700 pt-4">
                <label className="block text-sm font-medium text-gray-300 mb-2">
                  📋 Stories to Implement
                </label>
                <div className="space-y-2">
                  <label className="flex items-center space-x-2 cursor-pointer">
                    <input
                      type="radio"
                      name="storiesSource"
                      checked={storiesSourceType === 'loop'}
                      onChange={() => setStoriesSourceType('loop')}
                      className="bg-gray-700 border-gray-600"
                    />
                    <span className="text-gray-300 text-sm">From planning loop:</span>
                    <select
                      value={sourceLoopName}
                      onChange={(e) => setSourceLoopName(e.target.value)}
                      disabled={storiesSourceType !== 'loop'}
                      className="flex-1 px-2 py-1 bg-gray-700 border border-gray-600 rounded text-white text-sm disabled:opacity-50"
                    >
                      <option value="">Select a loop...</option>
                      {generatorLoops.map((loop) => (
                        <option key={loop} value={loop}>
                          {loop}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label className="flex items-center space-x-2 cursor-pointer">
                    <input
                      type="radio"
                      name="storiesSource"
                      checked={storiesSourceType === 'upload'}
                      onChange={() => setStoriesSourceType('upload')}
                      className="bg-gray-700 border-gray-600"
                    />
                    <span className="text-gray-300 text-sm">Upload JSONL file</span>
                  </label>
                  {storiesSourceType === 'upload' && (
                    <div className="ml-6">
                      {storiesFile ? (
                        <div className="flex items-center justify-between p-2 bg-gray-700 rounded">
                          <span className="text-white text-sm">{storiesFile.filename}</span>
                          <button
                            onClick={() => setStoriesFile(null)}
                            className="text-gray-400 hover:text-red-400 text-sm"
                          >
                            Remove
                          </button>
                        </div>
                      ) : (
                        <div className="flex flex-wrap gap-2">
                          <button
                            onClick={() => openFileBrowser('stories')}
                            className="px-3 py-1.5 bg-gray-700 border border-gray-600 rounded text-gray-300 hover:bg-gray-600 text-sm"
                          >
                            Browse Project
                          </button>
                          <button
                            onClick={() => fileInputRef.current?.click()}
                            className="px-3 py-1.5 bg-gray-700 border border-gray-600 rounded text-gray-300 hover:bg-gray-600 text-sm"
                          >
                            Upload File
                          </button>
                          <button
                            onClick={() => openPasteModal('stories')}
                            className="px-3 py-1.5 bg-gray-700 border border-gray-600 rounded text-gray-300 hover:bg-gray-600 text-sm"
                          >
                            Paste JSONL
                          </button>
                          <input
                            ref={fileInputRef}
                            type="file"
                            accept=".jsonl"
                            onChange={handleFileUpload}
                            className="hidden"
                          />
                        </div>
                      )}
                    </div>
                  )}
                </div>
              </div>

              <div className="border-t border-gray-700 pt-4">
                <label className="block text-sm font-medium text-gray-300 mb-2">
                  📄 Design Context (optional)
                </label>
                {designContext ? (
                  <div className="flex items-center justify-between p-3 bg-gray-700 rounded">
                    <span className="text-white">{designContext.filename}</span>
                    <button
                      onClick={() => setDesignContext(null)}
                      className="text-gray-400 hover:text-red-400"
                    >
                      Remove
                    </button>
                  </div>
                ) : (
                  <div className="flex space-x-2">
                    <button
                      onClick={() => openFileBrowser('context')}
                      className="flex-1 px-3 py-2 bg-gray-700 border border-gray-600 rounded text-gray-300 hover:bg-gray-600 text-sm"
                    >
                      Browse from Project
                    </button>
                    <button
                      onClick={() => openPasteModal('context')}
                      className="flex-1 px-3 py-2 bg-gray-700 border border-gray-600 rounded text-gray-300 hover:bg-gray-600 text-sm"
                    >
                      Paste Content
                    </button>
                  </div>
                )}
              </div>

              <div className="border-t border-gray-700 pt-4">
                <label className="flex items-center space-x-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={useCodeGuardrails}
                    onChange={(e) => setUseCodeGuardrails(e.target.checked)}
                    className="rounded bg-gray-700 border-gray-600"
                  />
                  <span className="text-gray-300 text-sm">Use default code guardrails</span>
                </label>
              </div>
            </div>
          )}

          {/* Step: Creating */}
          {step === 'creating' && (
            <div className="flex flex-col items-center justify-center py-8">
              <svg className="w-8 h-8 animate-spin text-primary-500" fill="none" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
              </svg>
              <p className="text-gray-400 mt-4">Creating "{displayName || loopType}"...</p>
            </div>
          )}
        </div>

        {/* Footer */}
        {step !== 'creating' && step !== 'choose-type' && (
          <div className="p-4 border-t border-gray-700 flex justify-between">
            <button
              onClick={handleBack}
              className="px-4 py-2 text-gray-400 hover:text-white"
            >
              Back
            </button>
            <button
              onClick={handleCreate}
              disabled={!canCreate()}
              className="px-4 py-2 bg-primary-600 text-white rounded hover:bg-primary-500 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              Create Loop
            </button>
          </div>
        )}
      </div>

      {/* File Browser Modal */}
      {showFileBrowser && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-[60]">
          <div className="bg-gray-800 rounded-lg w-full max-w-md mx-4">
            <div className="p-4 border-b border-gray-700 flex justify-between items-center">
              <h4 className="font-medium text-white">Select File</h4>
              <button
                onClick={() => setShowFileBrowser(false)}
                className="text-gray-400 hover:text-white"
                aria-label="Close file browser"
              >
                <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
            <div className="p-4">
              {browserError && (
                <div className="mb-3 p-2 bg-red-900/30 border border-red-800 rounded text-sm text-red-400">
                  {browserError}
                </div>
              )}
              <div className="text-sm text-gray-400 mb-2">
                {browserPath || '/ (project root)'}
              </div>
              {loadingBrowser ? (
                <div className="text-gray-400">Loading...</div>
              ) : (
                <div className="max-h-64 overflow-y-auto space-y-1">
                  {browserCanGoUp && (
                    <button
                      onClick={navigateUp}
                      className="w-full text-left px-3 py-2 bg-gray-700 rounded hover:bg-gray-600 text-gray-300"
                    >
                      📁 ..
                    </button>
                  )}
                  {browserDirs.map((dir) => (
                    <button
                      key={dir}
                      onClick={() => navigateToDir(dir)}
                      className="w-full text-left px-3 py-2 bg-gray-700 rounded hover:bg-gray-600 text-white"
                    >
                      📁 {dir}
                    </button>
                  ))}
                  {browserFiles.map((file) => (
                    <button
                      key={file.name}
                      onClick={() => selectFile(file.name)}
                      className="w-full text-left px-3 py-2 bg-gray-700 rounded hover:bg-gray-600 text-white"
                    >
                      📄 {file.name}
                    </button>
                  ))}
                  {browserDirs.length === 0 && browserFiles.length === 0 && (
                    <div className="text-gray-400 text-sm">No files found</div>
                  )}
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Paste Modal */}
      {showPasteModal && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-[60]">
          <div className="bg-gray-800 rounded-lg w-full max-w-md mx-4">
            <div className="p-4 border-b border-gray-700">
              <h4 className="font-medium text-white">Paste Content</h4>
            </div>
            <div className="p-4 space-y-4">
              <div>
                <label htmlFor="paste-filename" className="block text-sm text-gray-400 mb-1">Filename</label>
                <input
                  id="paste-filename"
                  type="text"
                  value={pasteFilename}
                  onChange={(e) => setPasteFilename(e.target.value)}
                  className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded text-white"
                />
              </div>
              <div>
                <label htmlFor="paste-content" className="block text-sm text-gray-400 mb-1">Content</label>
                <textarea
                  id="paste-content"
                  value={pasteContent}
                  onChange={(e) => setPasteContent(e.target.value)}
                  rows={8}
                  className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded text-white font-mono text-sm"
                  placeholder="Paste your content here..."
                />
              </div>
            </div>
            <div className="p-4 border-t border-gray-700 flex justify-end space-x-3">
              <button
                onClick={() => setShowPasteModal(false)}
                className="px-4 py-2 text-gray-400 hover:text-white"
              >
                Cancel
              </button>
              <button
                onClick={handlePaste}
                disabled={!pasteContent || !pasteFilename}
                className="px-4 py-2 bg-primary-600 text-white rounded hover:bg-primary-500 disabled:opacity-50"
              >
                Add
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
