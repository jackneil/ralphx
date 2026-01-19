import { ReactNode } from 'react'

interface ConceptCardProps {
  icon: ReactNode
  title: string
  description: string
  color?: 'cyan' | 'emerald' | 'amber' | 'violet'
}

export default function ConceptCard({ icon, title, description, color = 'cyan' }: ConceptCardProps) {
  const colorStyles = {
    cyan: {
      bg: 'bg-cyan-500/10',
      border: 'border-cyan-500/20 hover:border-cyan-500/40',
      iconBg: 'bg-cyan-500/20',
      iconText: 'text-cyan-400',
    },
    emerald: {
      bg: 'bg-emerald-500/10',
      border: 'border-emerald-500/20 hover:border-emerald-500/40',
      iconBg: 'bg-emerald-500/20',
      iconText: 'text-emerald-400',
    },
    amber: {
      bg: 'bg-amber-500/10',
      border: 'border-amber-500/20 hover:border-amber-500/40',
      iconBg: 'bg-amber-500/20',
      iconText: 'text-amber-400',
    },
    violet: {
      bg: 'bg-violet-500/10',
      border: 'border-violet-500/20 hover:border-violet-500/40',
      iconBg: 'bg-violet-500/20',
      iconText: 'text-violet-400',
    },
  }

  const styles = colorStyles[color]

  return (
    <div className={`rounded-lg border ${styles.border} ${styles.bg} p-4 transition-colors`}>
      <div className={`w-10 h-10 rounded-lg ${styles.iconBg} ${styles.iconText} flex items-center justify-center mb-3`}>
        {icon}
      </div>
      <h3 className="text-sm font-semibold text-white mb-1">{title}</h3>
      <p className="text-xs text-gray-400 leading-relaxed">{description}</p>
    </div>
  )
}
