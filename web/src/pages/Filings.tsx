import { Eyebrow } from '../components/ui'
import FilingCockpit from '../components/FilingCockpit'
import ReportTabs from '../components/ReportTabs'

// The filing cockpit for every sector — lifecycle, register, obligations calendar, validation, 4-eyes, attestation and
// snapshot exports. Which reports appear comes from the organisation's own obligations, never from this page.

export default function Filings() {
  return (
    <div className="fadeup space-y-6">
      <ReportTabs />
      <div>
        <Eyebrow>Compliance · filings</Eyebrow>
        <h1 className="display text-3xl font-semibold mt-2 mb-1">Filings</h1>
        <p className="text-[var(--color-mute)] text-sm max-w-2xl">Prepare, review, attest and file your regulatory reports — every number frozen, reviewed by a second person, attested and exported.</p>
      </div>
      <FilingCockpit />
    </div>
  )
}
