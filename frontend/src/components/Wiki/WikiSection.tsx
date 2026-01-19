import { ReactNode } from 'react'

interface WikiSectionProps {
  icon: ReactNode
  title: string
  description?: string
  children: ReactNode
  id?: string
}

export default function WikiSection({ icon, title, description, children, id }: WikiSectionProps) {
  return (
    <section id={id} className="mb-10">
      <div className="flex items-start space-x-3 mb-4">
        <div className="p-2 rounded-lg bg-cyan-500/10 text-cyan-400 mt-0.5">
          {icon}
        </div>
        <div>
          <h2 className="text-xl font-semibold text-white">{title}</h2>
          {description && (
            <p className="text-sm text-gray-400 mt-1">{description}</p>
          )}
        </div>
      </div>
      <div className="ml-12">
        {children}
      </div>
    </section>
  )
}
