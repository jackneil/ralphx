import ReactMarkdown from 'react-markdown'
import type { PlanningMessage } from '../../api'
import { formatLocalTime } from '../../utils/time'

interface ChatMessageProps {
  message: PlanningMessage
  isStreaming?: boolean
}

export default function ChatMessage({ message, isStreaming = false }: ChatMessageProps) {
  const isUser = message.role === 'user'

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
        <div className="text-sm leading-relaxed prose prose-invert prose-sm max-w-none">
          <ReactMarkdown>{message.content}</ReactMarkdown>
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
