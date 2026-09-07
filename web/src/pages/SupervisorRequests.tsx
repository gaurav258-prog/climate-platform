import { PageHeader, Card } from '../components/ui'

// Planned surface — shown honestly as such, never as an empty shell pretending to work.
export default function SupervisorRequests() {
  return (
    <div className="fadeup space-y-6">
      <PageHeader eyebrow="Requests & findings · planned" title="Engage and follow up"
        lead="Information requests to supervised entities, site-access requests, findings and their remediation — tracked to closure, audited on both sides. This is the next surface on the agreed build order and is not live yet." />
      <Card className="p-6 text-[13px] text-[var(--color-mute)]">Until it ships, a request goes to the entity through your existing channels; the entity file records what you looked at, and the entity's Control center shows what it has granted.</Card>
    </div>
  )
}
