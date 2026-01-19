import { useEffect, useRef, useState } from 'react'

export interface ConfirmDialogProps {
  isOpen: boolean
  title: string
  message: string
  details?: string
  confirmLabel?: string
  cancelLabel?: string
  variant?: 'default' | 'danger'
  /** If set, user must type this exact text to enable confirm button */
  typeToConfirm?: string
  onConfirm: () => void
  onCancel: () => void
}

export default function ConfirmDialog({
  isOpen,
  title,
  message,
  details,
  confirmLabel = 'Confirm',
  cancelLabel = 'Cancel',
  variant = 'default',
  typeToConfirm,
  onConfirm,
  onCancel,
}: ConfirmDialogProps) {
  const confirmButtonRef = useRef<HTMLButtonElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)
  const [typedValue, setTypedValue] = useState('')

  // Reset typed value when dialog opens/closes
  useEffect(() => {
    if (isOpen) {
      setTypedValue('')
    }
  }, [isOpen])

  // Focus input or confirm button when dialog opens
  useEffect(() => {
    if (isOpen) {
      if (typeToConfirm && inputRef.current) {
        inputRef.current.focus()
      } else if (confirmButtonRef.current) {
        confirmButtonRef.current.focus()
      }
    }
  }, [isOpen, typeToConfirm])

  const canConfirm = !typeToConfirm || typedValue === typeToConfirm

  // Handle escape key
  useEffect(() => {
    if (!isOpen) return
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onCancel()
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [isOpen, onCancel])

  if (!isOpen) return null

  const isDanger = variant === 'danger'

  return (
    <div
      className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 animate-in fade-in duration-150"
      onClick={(e) => {
        if (e.target === e.currentTarget) onCancel()
      }}
    >
      <div className="bg-gray-800 rounded-xl border border-gray-600 shadow-2xl w-full max-w-md mx-4 animate-in zoom-in-95 duration-150">
        {/* Header */}
        <div className="flex items-start gap-4 p-6 pb-4">
          {isDanger ? (
            <div className="flex-shrink-0 w-10 h-10 rounded-full bg-red-500/20 flex items-center justify-center">
              <svg className="w-5 h-5 text-red-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
              </svg>
            </div>
          ) : (
            <div className="flex-shrink-0 w-10 h-10 rounded-full bg-primary-500/20 flex items-center justify-center">
              <svg className="w-5 h-5 text-primary-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8.228 9c.549-1.165 2.03-2 3.772-2 2.21 0 4 1.343 4 3 0 1.4-1.278 2.575-3.006 2.907-.542.104-.994.54-.994 1.093m0 3h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
            </div>
          )}
          <div className="flex-1">
            <h3 className="text-lg font-semibold text-white">{title}</h3>
            <p className="mt-1 text-sm text-gray-400">{message}</p>
          </div>
        </div>

        {/* Details box (for showing what will be lost, etc.) */}
        {details && (
          <div className="px-6 pb-4">
            <div className={`p-3 rounded-lg text-sm ${
              isDanger
                ? 'bg-red-900/20 border border-red-800/50 text-red-300'
                : 'bg-gray-700 text-gray-300'
            }`}>
              {details}
            </div>
          </div>
        )}

        {/* Type to confirm input */}
        {typeToConfirm && (
          <div className="px-6 pb-4">
            <label className="block text-sm text-gray-400 mb-2">
              Type <span className="font-mono font-semibold text-white bg-gray-700 px-1.5 py-0.5 rounded">{typeToConfirm}</span> to confirm
            </label>
            <input
              ref={inputRef}
              type="text"
              value={typedValue}
              onChange={(e) => setTypedValue(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && canConfirm) {
                  onConfirm()
                }
              }}
              placeholder={typeToConfirm}
              className="w-full px-3 py-2 bg-gray-900 border border-gray-600 rounded-lg text-white placeholder-gray-600 focus:outline-none focus:border-red-500 font-mono"
              autoComplete="off"
              spellCheck={false}
            />
          </div>
        )}

        {/* Actions */}
        <div className="flex justify-end gap-3 px-6 py-4 bg-gray-900/50 rounded-b-xl border-t border-gray-700">
          <button
            onClick={onCancel}
            className="px-4 py-2 text-sm font-medium text-gray-300 hover:text-white bg-gray-700 hover:bg-gray-600 rounded-lg transition-colors"
          >
            {cancelLabel}
          </button>
          <button
            ref={confirmButtonRef}
            onClick={onConfirm}
            disabled={!canConfirm}
            className={`px-4 py-2 text-sm font-medium rounded-lg transition-colors disabled:opacity-40 disabled:cursor-not-allowed ${
              isDanger
                ? 'bg-red-600 hover:bg-red-500 text-white disabled:hover:bg-red-600'
                : 'bg-primary-600 hover:bg-primary-500 text-white disabled:hover:bg-primary-600'
            }`}
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  )
}
