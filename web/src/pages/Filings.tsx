import { PageHeader } from '../components/ui'
import { HEADING } from '../components/Details'
import FilingCockpit from '../components/FilingCockpit'
import ReportTabs from '../components/ReportTabs'

// The filing cockpit for every sector — lifecycle, register, obligations, checks, four eyes, attestation and the
// frozen report's downloads. Which reports appear comes from the organisation's own obligations, never from this page.

export default function Filings() {
  return (
    <div className="fadeup space-y-6">
      <ReportTabs />
      <PageHeader eyebrow="Compliance · filings" title="Filings" lead="Prepare, review, attest and file your regulatory reports."
        about={[{ heading: HEADING.read, body: 'Every figure is frozen with the filing, reviewed by a second person, attested by the accountable person and exported from the frozen report.' }]} />
      <FilingCockpit />
    </div>
  )
}
