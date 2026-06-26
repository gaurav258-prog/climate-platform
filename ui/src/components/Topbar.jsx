import { Radio, Bell } from 'lucide-react'

export default function Topbar({ alertCount = 0 }) {
  return (
    <header className="h-12 bg-white border-b border-gray-200 flex items-center justify-between px-6 shrink-0 z-20">
      <div className="flex items-center gap-2">
        <span className="text-lg font-light text-gray-900 tracking-tight">Climate</span>
        <span className="text-lg font-light bg-gradient-to-r from-blue-600 to-green-600 bg-clip-text text-transparent tracking-tight">Intelligence</span>
      </div>

      <div className="flex items-center gap-6 text-sm text-gray-600">
        {/* Live data sources */}
        <div className="flex items-center gap-2 border border-gray-200 rounded-full px-4 py-2 bg-gray-50">
          <Radio size={16} strokeWidth={1.5} className="text-green-600" />
          <span className="text-gray-700 font-light">Copernicus · ERA5 · FIRMS</span>
          <span className="mx-2 text-gray-300">·</span>
          <span className="text-green-600 font-light uppercase tracking-wider text-xs">Live</span>
        </div>

        {/* Bell */}
        <div className="relative">
          <Bell size={20} strokeWidth={1.5} className="text-gray-600 hover:text-gray-900 transition-colors cursor-pointer" />
          {alertCount > 0 && (
            <span className="absolute -top-2 -right-2 bg-red-500 text-white text-xs font-bold rounded-full w-5 h-5 flex items-center justify-center">
              {alertCount}
            </span>
          )}
        </div>

        <span className="text-gray-500 font-light">Rhine Basin · Jun 2026</span>
      </div>
    </header>
  )
}
