import { useState } from 'react'

interface ArtifactPreviewProps {
  artifacts: {
    design_doc?: string
    guardrails?: string
  }
}

export default function ArtifactPreview({ artifacts }: ArtifactPreviewProps) {
  const [activeTab, setActiveTab] = useState<'design_doc' | 'guardrails'>('design_doc')

  const tabs = [
    { id: 'design_doc', label: 'Design Document', content: artifacts.design_doc },
    { id: 'guardrails', label: 'Guardrails', content: artifacts.guardrails },
  ].filter(tab => tab.content) as { id: 'design_doc' | 'guardrails'; label: string; content: string }[]

  if (tabs.length === 0) {
    return null
  }

  const activeContent = tabs.find(t => t.id === activeTab)?.content || tabs[0]?.content

  return (
    <div className="mt-4 rounded-lg border border-gray-700 overflow-hidden">
      {/* Tabs */}
      <div className="flex border-b border-gray-700 bg-gray-800">
        {tabs.map(tab => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`px-4 py-2 text-sm font-medium transition-colors ${
              activeTab === tab.id
                ? 'text-white bg-gray-700 border-b-2 border-primary-500'
                : 'text-gray-400 hover:text-white hover:bg-gray-700/50'
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Content */}
      <div className="p-4 bg-gray-900 max-h-96 overflow-y-auto">
        <pre className="text-sm text-gray-300 whitespace-pre-wrap font-mono">
          {activeContent}
        </pre>
      </div>
    </div>
  )
}
