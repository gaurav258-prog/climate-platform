import { Eyebrow } from '../components/ui'
import FilingCockpit from '../components/FilingCockpit'
import ReportTabs from '../components/ReportTabs'

// Agri filing cockpit — the same lifecycle, register, obligations calendar, validation, 4-eyes, attestation
// and snapshot exports the financial sectors use, over the CSRD/ESRS reports (csrd_e1 · esrs_pack).

export default function Filings() {
  return (
    <div className="fadeup space-y-6">
      <ReportTabs />
      <div>
        <Eyebrow>Compliance · filings</Eyebrow>
        <h1 className="display text-3xl font-semibold mt-2 mb-1">Filings</h1>
        <p className="text-[var(--color-mute)] text-sm max-w-2xl">Prepare, review, attest and file your CSRD / ESRS reports — the same governed lifecycle (frozen snapshots, 4-eyes, attestation, exports) the financial sectors use.</p>
      </div>
      <FilingCockpit />
    </div>
  )
}
