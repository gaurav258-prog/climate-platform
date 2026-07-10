import { HelpCircle } from 'lucide-react'

// Contextual help — jumps straight to a Documentation section instead of
// leaving the user to find it themselves (or, as several pages did before
// this, naming a section in plain text with no way to actually get there).
// section matches DocumentationPage.jsx's SECTIONS ids ('start' | 'method' |
// 'data' | 'api' | 'reg').
export default function HelpLink({ onGoto, section = 'method', children = 'Methodology' }) {
  if (!onGoto) return <>{children}</>
  return (
    <button onClick={() => onGoto(`docs:${section}`)}
      className="inline-flex items-center gap-1 font-medium text-[#0071e3] hover:underline">
      {children} <HelpCircle size={12} />
    </button>
  )
}
