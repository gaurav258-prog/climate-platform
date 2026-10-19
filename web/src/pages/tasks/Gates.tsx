import { useState } from 'react'
import { Check, Send } from 'lucide-react'
import clsx from 'clsx'
import { Button } from '../../components/ui'
import { Dialog } from '../../components/Dialog'
import { StatusChip } from '../../components/StatusChip'
import { COL_LABEL, gateItemsFor, type Task } from './model'

// Ask a second person to approve completion — this does not move the card. It opens a real approval request that only a
// different colleague can grant on Approvals (services/governance/tasks.request_completion).
export function CompletionModal({ task, onClose, onConfirm }: { task: Task; onClose: () => void; onConfirm: (note: string) => void }) {
  const [note, setNote] = useState('')
  return (
    <Dialog title="Ask for completion" onClose={onClose} overlayClassName="z-[60] p-4">
      <div className="space-y-3">
        <div className="inline-flex items-center gap-1.5"><StatusChip tone="warn" label="Needs a second person" /></div>
        <p className="m-0 text-[12.5px] text-[var(--color-mute)]">“{task.title}” moves to Done once a different colleague approves it on Approvals. You cannot approve your own request.</p>
        <textarea autoFocus value={note} onChange={e => setNote(e.target.value)} rows={3} aria-label="Outcome" placeholder="The outcome — such as filed as version three, accepted by the authority"
          className="w-full bg-[var(--color-panel)] border border-[var(--color-line)] rounded-lg px-3 py-2 text-[13px] outline-none focus:border-[var(--color-sky)]" />
        <div className="flex items-center justify-end gap-2">
          <Button variant="ghost" onClick={onClose}>Cancel</Button>
          <Button variant="primary" disabled={!note.trim()} onClick={() => onConfirm(note.trim())}><Send size={14} /> Ask for approval</Button>
        </div>
      </div>
    </Dialog>
  )
}

// The stage gate: the checklist a card must clear to enter a stage. Verified items come from the task's own state and are
// locked; the others are confirmed by the person moving it. Confirm unlocks only when every item is satisfied.
export function GateModal({ task, target, onClose, onConfirm }: { task: Task; target: string; onClose: () => void; onConfirm: (attestations: string[]) => void }) {
  const items = gateItemsFor(target, task)
  const autoOk = (i: { auto?: (t: Task) => boolean }) => (i.auto ? i.auto(task) : false)
  const [checked, setChecked] = useState<Record<string, boolean>>(() => Object.fromEntries(items.map(i => [i.id, autoOk(i)])))
  const allOk = items.every(i => (i.auto ? autoOk(i) : checked[i.id]))
  return (
    <Dialog title={`Move to ${COL_LABEL[target]}`} onClose={onClose} overlayClassName="z-[60] p-4">
      <div className="space-y-3">
        <p className="m-0 text-[12.5px] text-[var(--color-mute)]">Confirm these checks before the card enters {COL_LABEL[target]}.</p>
        <div className="space-y-2">
          {items.map(i => {
            const auto = !!i.auto, ok = auto ? autoOk(i) : !!checked[i.id]
            return (
              <button key={i.id} disabled={auto} aria-pressed={ok} onClick={() => !auto && setChecked(c => ({ ...c, [i.id]: !c[i.id] }))}
                className={clsx('w-full flex items-start gap-2.5 text-left rounded-lg border p-2.5 transition', ok ? 'border-[var(--color-good)] bg-[color-mix(in_oklab,var(--color-good)_8%,transparent)]' : 'border-[var(--color-line-2)] hover:border-[var(--color-sky)]', auto && 'cursor-default')}>
                <span className={clsx('mt-0.5 w-4 h-4 rounded flex items-center justify-center shrink-0', ok ? 'bg-[var(--color-good)] text-[var(--color-on-accent)]' : 'border border-[var(--color-line-2)]')}>{ok && <Check size={12} />}</span>
                <span className="text-[12.5px] text-[var(--color-ink)] leading-snug flex-1">{i.label}</span>
                {auto && <StatusChip tone={ok ? 'good' : 'bad'} label={ok ? 'Verified' : 'Not met'} />}
              </button>
            )
          })}
        </div>
        {items.some(i => i.auto && !autoOk(i)) && <p className="m-0 text-[12px] text-[var(--color-bad)]">A verified check is not met yet — assign an owner, clear the dependencies or record the work, then move the card.</p>}
        <div className="flex items-center justify-end gap-2">
          <Button variant="ghost" onClick={onClose}>Cancel</Button>
          <Button variant="primary" disabled={!allOk} onClick={() => onConfirm(items.map(i => i.label))}><Check size={14} /> Confirm move</Button>
        </div>
      </div>
    </Dialog>
  )
}
