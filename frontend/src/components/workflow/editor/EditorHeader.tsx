interface EditorHeaderProps {
  workflowName: string
  onBack: () => void
  onSave: () => void
  saving: boolean
  dirty: boolean
}

export default function EditorHeader({
  workflowName,
  onBack,
  onSave,
  saving,
  dirty,
}: EditorHeaderProps) {
  return (
    <div className="sticky top-0 z-10 bg-gray-900 border-b border-gray-700">
      <div className="flex items-center justify-between px-6 py-4">
        <div className="flex items-center space-x-4">
          <button
            onClick={onBack}
            className="flex items-center space-x-2 text-gray-400 hover:text-white transition-colors"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 19l-7-7m0 0l7-7m-7 7h18" />
            </svg>
            <span>Back to Workflow</span>
          </button>

          <div className="h-6 w-px bg-gray-700" />

          <h1 className="text-xl font-semibold text-white truncate max-w-md">
            {workflowName || 'Untitled Workflow'}
          </h1>

          {dirty && (
            <span className="px-2 py-0.5 text-xs rounded bg-yellow-900/50 text-yellow-400 border border-yellow-700/50">
              Unsaved
            </span>
          )}
        </div>

        <div className="flex items-center space-x-3">
          <span className="text-xs text-gray-500">
            {navigator.platform.includes('Mac') ? '⌘' : 'Ctrl'}+S to save
          </span>

          <button
            onClick={onSave}
            disabled={saving || !dirty}
            className={`flex items-center space-x-2 px-4 py-2 rounded-lg font-medium transition-colors ${
              dirty
                ? 'bg-primary-600 text-white hover:bg-primary-500'
                : 'bg-gray-700 text-gray-400 cursor-not-allowed'
            } disabled:opacity-50`}
          >
            {saving ? (
              <>
                <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                </svg>
                <span>Saving...</span>
              </>
            ) : (
              <>
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                </svg>
                <span>Save Changes</span>
              </>
            )}
          </button>
        </div>
      </div>
    </div>
  )
}
