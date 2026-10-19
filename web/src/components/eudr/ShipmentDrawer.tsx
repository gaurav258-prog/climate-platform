import { type ReactNode } from 'react'
import { Drawer } from '../Drawer'
import { CloseButton } from '../Dialog'
import { InfoButton, type DetailSection } from '../Details'
import { StatusChip } from '../StatusChip'
import { fmtDate, kg, named, type Movement, type Names } from './types'

// The frame of one shipment, opened from the shipments table: its reference, what kind of movement it is and when, the
// product (its description one click away), the undertaking's role in it, where its record stands and the next action.

export function ShipmentDrawer({ m, names, chip, actions, product, children, onClose }: {
  m: Movement; names: Names; chip?: ReactNode; actions?: ReactNode; product?: DetailSection[]; children: ReactNode; onClose: () => void
}) {
  const title = m.external_ref ?? 'Shipment'
  return (
    <Drawer label={`Shipment ${title}`} onClose={onClose}
      className="h-full w-full max-w-4xl overflow-y-auto bg-[var(--color-bg)] border-l border-[var(--color-line)] shadow-2xl">
      <div className="sticky top-0 z-10 px-5 sm:px-6 py-4 border-b border-[var(--color-line)] bg-[var(--color-bg)]/95 backdrop-blur space-y-2.5">
        <div className="flex items-start gap-3">
          <div className="min-w-0 flex-1">
            <h2 className="display text-xl font-semibold m-0 break-words">{title}</h2>
            <div className="flex flex-wrap items-center gap-1.5 mt-1.5">
              <StatusChip tone="neutral" label={named(names, 'kind', m.kind)} />
              <StatusChip tone="neutral" label={fmtDate(m.planned_on)} />
              <span className="inline-flex items-center gap-1">
                <StatusChip tone="neutral" label={`HS ${m.hs_code}`} />
                <InfoButton compact details={{ title: `HS ${m.hs_code}`, sections: product ?? [{ heading: 'Product', body: m.description ?? '—' }] }} />
              </span>
              {m.net_mass_kg != null && <StatusChip tone="neutral" label={kg(m.net_mass_kg)} />}
              <StatusChip tone="neutral" label={named(names, 'actor', m.actor_role)} />
              {chip}
            </div>
          </div>
          <CloseButton onClick={onClose} />
        </div>
        {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
      </div>
      <div className="px-5 sm:px-6 py-5 space-y-6">{children}</div>
    </Drawer>
  )
}
