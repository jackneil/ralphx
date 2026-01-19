import { useState, useEffect } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import GettingStartedContent from '../components/Wiki/content/GettingStartedContent'
import UseCasesContent from '../components/Wiki/content/UseCasesContent'
import MonitoringContent from '../components/Wiki/content/MonitoringContent'
import RemoteAccessContent from '../components/Wiki/content/RemoteAccessContent'

type TabId = 'getting-started' | 'use-cases' | 'monitoring' | 'remote-access'

interface Tab {
  id: TabId
  label: string
  icon: JSX.Element
}

const tabs: Tab[] = [
  {
    id: 'getting-started',
    label: 'Getting Started',
    icon: (
      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
      </svg>
    ),
  },
  {
    id: 'use-cases',
    label: 'Use Cases',
    icon: (
      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" />
      </svg>
    ),
  },
  {
    id: 'monitoring',
    label: 'Monitoring',
    icon: (
      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
      </svg>
    ),
  },
  {
    id: 'remote-access',
    label: 'Remote Access',
    icon: (
      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 12a9 9 0 01-9 9m9-9a9 9 0 00-9-9m9 9H3m9 9a9 9 0 01-9-9m9 9c1.657 0 3-4.03 3-9s-1.343-9-3-9m0 18c-1.657 0-3-4.03-3-9s1.343-9 3-9m-9 9a9 9 0 019-9" />
      </svg>
    ),
  },
]

export default function Wiki() {
  const location = useLocation()
  const navigate = useNavigate()

  // Parse hash from URL
  const getTabFromHash = (): TabId => {
    const hash = location.hash.replace('#', '')
    const validTab = tabs.find(t => t.id === hash)
    return validTab ? validTab.id : 'getting-started'
  }

  const [activeTab, setActiveTab] = useState<TabId>(getTabFromHash)

  // Update tab when hash changes
  useEffect(() => {
    setActiveTab(getTabFromHash())
  }, [location.hash])

  const handleTabChange = (tabId: TabId) => {
    setActiveTab(tabId)
    navigate(`/wiki#${tabId}`, { replace: true })
  }

  const renderContent = () => {
    switch (activeTab) {
      case 'getting-started':
        return <GettingStartedContent />
      case 'use-cases':
        return <UseCasesContent />
      case 'monitoring':
        return <MonitoringContent />
      case 'remote-access':
        return <RemoteAccessContent />
      default:
        return <GettingStartedContent />
    }
  }

  return (
    <div className="min-h-screen">
      {/* Header */}
      <div className="border-b border-gray-700/50 bg-gray-900/30">
        <div className="max-w-4xl mx-auto px-6 py-8">
          <div className="flex items-center space-x-3 mb-2">
            <div className="p-2 rounded-lg bg-cyan-500/20">
              <svg className="w-6 h-6 text-cyan-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253" />
              </svg>
            </div>
            <div>
              <h1 className="text-2xl font-bold text-white">Wiki</h1>
              <p className="text-sm text-gray-400">Learn how to use RalphX with step-by-step guides</p>
            </div>
          </div>
        </div>

        {/* Tabs */}
        <div className="max-w-4xl mx-auto px-6">
          <div className="flex space-x-1 overflow-x-auto pb-px">
            {tabs.map(tab => (
              <button
                key={tab.id}
                onClick={() => handleTabChange(tab.id)}
                className={`flex items-center space-x-2 px-4 py-3 text-sm font-medium whitespace-nowrap transition-colors border-b-2 ${
                  activeTab === tab.id
                    ? 'text-cyan-400 border-cyan-400'
                    : 'text-gray-400 border-transparent hover:text-gray-200 hover:border-gray-600'
                }`}
              >
                {tab.icon}
                <span>{tab.label}</span>
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Content */}
      <div className="max-w-4xl mx-auto px-6 py-8">
        {renderContent()}
      </div>
    </div>
  )
}
