import { ExternalLink } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { labelForRelation, useSimilarHints } from '../api/similar.ts'

export default function SimilarHints({ text }: { text: string }) {
  const draft = text.trim()
  const [settled, setSettled] = useState('')

  useEffect(() => {
    const timer = window.setTimeout(() => setSettled(draft), 800)
    return () => window.clearTimeout(timer)
  }, [draft])

  const { data } = useSimilarHints(draft === settled ? settled : '')
  if (!data?.nearest.length) return null

  return (
    <aside aria-label="Podobne rozwiązania" aria-live="polite" className="space-y-2 rounded-xl bg-brand-50 px-4 py-3">
      <p className="text-sm font-semibold text-brand-700">Świeżość w radarze · {data.novelty}/100</p>
      <p className="text-sm text-slate-700">
        Zobacz, co zrobili inni, lub odezwij się do twórców. Możesz dalej zgłosić swoją innowację.
      </p>
      <ul className="space-y-2">
        {data.nearest.slice(0, 3).map(({ innovation, relation }) => (
          <li key={innovation.id}>
            <Link
              to={`/innowacje/${innovation.id}`}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-baseline gap-1.5 text-sm font-medium text-brand-700 hover:underline"
            >
              {innovation.title}
              <ExternalLink className="size-3 shrink-0 self-center" aria-hidden="true" />
              <span className="sr-only"> (otwiera się w nowej karcie)</span>
            </Link>
            <p className="text-xs text-slate-600">{labelForRelation(relation)}</p>
          </li>
        ))}
      </ul>
    </aside>
  )
}
