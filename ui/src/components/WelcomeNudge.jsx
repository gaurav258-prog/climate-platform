import { useState, useEffect } from 'react'
import { Sparkles, X, Command, HelpCircle, MousePointerClick } from 'lucide-react'

const STORAGE_KEY = 'tellumen_welcome_seen'

function seenBy(email) {
  try { return JSON.parse(localStorage.getItem(STORAGE_KEY) || '[]').includes(email) }
  catch { return false }
}
function markSeen(email) {
  try {
    const seen = JSON.parse(localStorage.getItem(STORAGE_KEY) || '[]')
    if (!seen.includes(email)) localStorage.setItem(STORAGE_KEY, JSON.stringify([...seen, email]))
  } catch { /* localStorage unavailable — nudge just reappears next session, harmless */ }
}

// A first-login orientation for a demo-provisioned platform: no signup flow to
// walk through, so this is three things worth knowing rather than a multi-step
// tour. Shown once per user (localStorage), dismissible immediately.
export default function WelcomeNudge({ email, orgLabel, onOpenSearch }) {
  const [visible, setVisible] = useState(false)

  useEffect(() => {
    if (email && !seenBy(email)) setVisible(true)
  }, [email])

  const dismiss = () => { markSeen(email); setVisible(false) }

  if (!visible) return null

  return (
    <div className="fixed bottom-5 right-5 z-[9990] w-[340px] overflow-hidden rounded-2xl border border-gray-200/70 bg-white shadow-xl">
      <div className="flex items-start justify-between gap-2 px-4 pt-4">
        <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-[#0071e3]/10 text-[#0071e3]">
          <Sparkles size={15} />
        </span>
        <button onClick={dismiss} className="text-gray-300 hover:text-gray-500"><X size={16} /></button>
      </div>
      <div className="px-4 pb-4 pt-2">
        <h3 className="text-[14px] font-semibold text-[#1d1d1f]">Welcome to {orgLabel}'s workspace</h3>
        <p className="mt-1 text-[12px] text-gray-500">Three things that'll save you clicks:</p>
        <ul className="mt-3 space-y-2.5">
          <li className="flex items-start gap-2.5">
            <Command size={14} className="mt-0.5 shrink-0 text-gray-400" />
            <span className="text-[12px] text-gray-600"><b className="text-[#1d1d1f]">⌘K</b> jumps to any module, methodology page or support area from anywhere.</span>
          </li>
          <li className="flex items-start gap-2.5">
            <MousePointerClick size={14} className="mt-0.5 shrink-0 text-gray-400" />
            <span className="text-[12px] text-gray-600">Click any asset, property or holding row to drill into its full risk and provenance.</span>
          </li>
          <li className="flex items-start gap-2.5">
            <HelpCircle size={14} className="mt-0.5 shrink-0 text-gray-400" />
            <span className="text-[12px] text-gray-600">A <b className="text-[#1d1d1f]">Methodology</b> link sits next to every number that needs one.</span>
          </li>
        </ul>
        <div className="mt-4 flex gap-2">
          <button onClick={() => { dismiss(); onOpenSearch() }}
            className="flex-1 rounded-full bg-[#1d1d1f] px-3 py-1.5 text-[12px] font-medium text-white hover:bg-black">
            Try ⌘K search
          </button>
          <button onClick={dismiss}
            className="rounded-full border border-gray-200 px-3 py-1.5 text-[12px] font-medium text-gray-600 hover:border-gray-300">
            Got it
          </button>
        </div>
      </div>
    </div>
  )
}
