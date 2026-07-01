import { ArrowRight } from 'lucide-react'
import { ICON } from './catalogIcons'

// Persistent value-chain lineage + customer switch. Always visible so any screen
// says where the number came from and who it's for.
export default function LineageBar({ personas, personaId, onPersona }) {
  const chip = 'rounded-full border border-gray-200 px-2.5 py-1 text-[11px] text-gray-600'
  return (
    <header className="flex items-center justify-between gap-4 border-b border-gray-200 bg-white px-5 py-2.5">
      <div className="flex items-center gap-2 text-[15px] font-semibold tracking-tight text-[#1d1d1f]">
        Climate <span className="text-[#0071e3]">Intelligence</span>
      </div>

      <div className="hidden items-center gap-2 md:flex">
        <span className={chip}>Live data</span>
        <ArrowRight size={13} className="text-gray-300" />
        <span className={chip}>AI engine</span>
        <ArrowRight size={13} className="text-gray-300" />
        <span className={chip}>Sector outputs</span>
        <span className="ml-1 flex items-center gap-1 text-[11px] font-medium text-emerald-600">
          <span className="h-1.5 w-1.5 rounded-full bg-emerald-500 animate-pulse" /> live
        </span>
      </div>

      <label className="flex items-center gap-2 text-[12px] text-gray-500">
        <span className="hidden sm:inline text-gray-400">Customer</span>
        <select value={personaId} onChange={e => onPersona(e.target.value)}
          className="rounded-lg border border-gray-200 bg-white px-2.5 py-1.5 text-[12px] font-medium text-[#1d1d1f] outline-none hover:border-gray-300 focus:border-[#0071e3]">
          {personas.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
        </select>
      </label>
    </header>
  )
}
