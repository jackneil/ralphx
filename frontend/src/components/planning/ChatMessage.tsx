import type { PlanningMessage } from '../../api'
import { formatLocalTime } from '../../utils/time'

interface ChatMessageProps {
  message: PlanningMessage
  isStreaming?: boolean
}

export default function ChatMessage({ message, isStreaming = false }: ChatMessageProps) {
  const isUser = message.role === 'user'

  // Simple markdown-like rendering for common patterns
  const renderContent = (content: string) => {
    // Split by double newlines to create paragraphs
    const paragraphs = content.split(/\n\n+/)

    return paragraphs.map((paragraph, pIndex) => {
      // Check if this is a numbered list
      if (/^\d+\.\s/.test(paragraph)) {
        const items = paragraph.split(/\n(?=\d+\.\s)/)
        return (
          <ol key={pIndex} className="list-decimal list-inside space-y-1 mb-4">
            {items.map((item, iIndex) => {
              const text = item.replace(/^\d+\.\s/, '')
              return <li key={iIndex}>{renderInline(text)}</li>
            })}
          </ol>
        )
      }

      // Check if this is a bullet list
      if (/^[-*]\s/.test(paragraph)) {
        const items = paragraph.split(/\n(?=[-*]\s)/)
        return (
          <ul key={pIndex} className="list-disc list-inside space-y-1 mb-4">
            {items.map((item, iIndex) => {
              const text = item.replace(/^[-*]\s/, '')
              return <li key={iIndex}>{renderInline(text)}</li>
            })}
          </ul>
        )
      }

      // Check for headers
      const headerMatch = paragraph.match(/^(#{1,3})\s+(.+)$/)
      if (headerMatch) {
        const level = headerMatch[1].length
        const text = headerMatch[2]
        const className = level === 1
          ? 'text-lg font-bold mb-2'
          : level === 2
            ? 'text-base font-semibold mb-2'
            : 'text-sm font-medium mb-1'
        return (
          <div key={pIndex} className={className}>
            {renderInline(text)}
          </div>
        )
      }

      // Regular paragraph
      return (
        <p key={pIndex} className="mb-4 last:mb-0">
          {renderInline(paragraph)}
        </p>
      )
    })
  }

  // Escape HTML entities to prevent XSS
  const escapeHtml = (text: string) => {
    return text
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;')
  }

  // Render inline markdown (bold, italic, code)
  const renderInline = (text: string) => {
    // First escape HTML to prevent XSS
    let processed = escapeHtml(text)
    // Replace **bold** with <strong>
    processed = processed.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    // Replace *italic* with <em>
    processed = processed.replace(/\*(.+?)\*/g, '<em>$1</em>')
    // Replace `code` with <code>
    processed = processed.replace(/`(.+?)`/g, '<code class="px-1 py-0.5 bg-gray-700 rounded text-sm">$1</code>')

    return <span dangerouslySetInnerHTML={{ __html: processed }} />
  }

  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}>
      <div
        className={`max-w-[80%] rounded-lg px-4 py-3 ${
          isUser
            ? 'bg-primary-600 text-white'
            : 'bg-gray-800 border border-gray-700 text-gray-200'
        }`}
      >
        {/* Role indicator */}
        <div className={`text-xs mb-2 ${isUser ? 'text-primary-200' : 'text-gray-500'}`}>
          {isUser ? 'You' : 'Claude'}
          {isStreaming && <span className="ml-2 animate-pulse">typing...</span>}
        </div>

        {/* Content */}
        <div className="text-sm leading-relaxed">
          {renderContent(message.content)}
        </div>

        {/* Timestamp */}
        {message.timestamp && (
          <div className={`text-xs mt-2 ${isUser ? 'text-primary-200' : 'text-gray-500'}`}>
            {formatLocalTime(message.timestamp)}
          </div>
        )}
      </div>
    </div>
  )
}
