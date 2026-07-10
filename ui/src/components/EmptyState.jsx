import { Inbox } from 'lucide-react'

// Standard SaaS empty-state convention: never a blank dashboard with zero
// values silently sitting in every stat tile. Explain what belongs here and
// give a one-click way to fill it — `action` is typically an already-expanded
// UploadPanel (see UploadPanel's `startOpen` prop).
export default function EmptyState({ icon: Icon = Inbox, title, description, action }) {
  return (
    <div className="mx-auto max-w-lg rounded-2xl border border-dashed border-gray-300 bg-white/60 px-8 py-12 text-center">
      <span className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-[#0071e3]/10 text-[#0071e3]">
        <Icon size={22} />
      </span>
      <h3 className="mt-4 text-[16px] font-semibold text-[#1d1d1f]">{title}</h3>
      {description && <p className="mt-1.5 text-[13px] leading-relaxed text-gray-500">{description}</p>}
      {action && <div className="mt-5 flex justify-center">{action}</div>}
    </div>
  )
}
