import { ScrollText, Percent, Scale, Leaf } from 'lucide-react'

// Every claim on this page traces to a primary source fetched and full-text-searched
// directly (not recalled from memory) during design — see the session's research pass
// against the actual ECB/EBA/EUR-Lex documents. Nothing here is invented.
export default function MethodologyPage() {
  return (
    <div className="h-full overflow-y-auto bg-[#f5f5f7] text-[#1d1d1f]">
      <div className="mx-auto max-w-5xl px-8 py-12">
        <header className="mb-8">
          <div className="flex items-center gap-1.5 text-xs font-medium uppercase tracking-[0.12em] text-gray-400">
            <ScrollText size={13} /> Trust &amp; assurance
          </div>
          <h1 className="mt-2 text-4xl font-semibold tracking-tight">Methodology</h1>
          <p className="mt-3 max-w-3xl text-[17px] leading-relaxed text-gray-500">
            How the three figures behind every lending decision — the collateral discount, the
            loan-to-value, and the EU Taxonomy status — are actually calculated, and exactly what
            each one is (and isn't) grounded in.
          </p>
        </header>

        <div className="space-y-5">
          <MethodologyCard icon={Percent} title="Collateral valuation discount"
            eyebrow="Risk-informed, not regulator-mandated">
            <p>
              Each asset's headline physical-risk bucket maps to a haircut: Low 0%, Moderate 5%,
              High 15%, Very High 30% (<code className="rounded bg-gray-100 px-1 py-0.5 text-[12px]">RECOMMENDED_DISCOUNT_PCT</code> in
              <code className="rounded bg-gray-100 px-1 py-0.5 text-[12px]"> ml/scoring/valuation_discount.py</code>). A human with
              approval rights can override any recommendation, and every override is audited.
            </p>
            <Quote source="ECB, Guide on climate-related and environmental risks (Nov 2020), Expectation 8.3">
              "Institutions are expected to consider climate-related and environmental risks in
              their collateral valuations... give particular consideration to the physical
              locations and the energy efficiency of commercial and residential real estate."
            </Quote>
            <p className="text-[13px] text-gray-500">
              That's the full extent of what the ECB Guide says — a qualitative expectation, not
              a formula. There is no published haircut schedule, percentage, or calculation
              method in the Guide or anywhere else we could find. The 0/5/15/30% schedule above
              is Tellumen's own methodology, motivated by that expectation but not derived from
              it — and it is disclosed as such, not badged as an ECB-mandated figure.
            </p>
          </MethodologyCard>

          <MethodologyCard icon={Scale} title="Loan-to-value (LTV)" eyebrow="A Tellumen credit metric, not an EBA disclosure field">
            <p>
              Original LTV = outstanding loan balance ÷ appraised value. Climate-adjusted LTV
              substitutes the climate-discounted value for the appraised value — the number a
              credit committee actually cares about once physical risk is priced in.
            </p>
            <p className="text-[13px] text-gray-500">
              "Climate-adjusted LTV" is not an EBA or ECB term. We searched the full text of the
              EBA's Pillar 3 ESG risk disclosure templates (EBA/ITS/2022/01 — 10 numbered
              templates covering transition risk, physical risk, and Green Asset Ratio) for
              "LTV" and "loan-to-value": zero matches. Template 5, the physical-risk template,
              discloses gross exposure by geography and sector, not loan-to-value. This is a
              genuinely useful internal credit metric — just not one to claim as regulator-defined.
            </p>
          </MethodologyCard>

          <MethodologyCard icon={Leaf} title="EU Taxonomy alignment" eyebrow="The one figure with a real mandated formula — used honestly">
            <p>
              EU Taxonomy Regulation (EU) 2020/852, Article 3, requires <b>all four</b> conditions
              for "aligned": substantial contribution to an environmental objective (per the
              Climate Delegated Act's technical screening criteria), do-no-significant-harm to
              the other five objectives, minimum safeguards (OECD/UN/ILO compliance), and the
              Commission's technical screening criteria. "Eligible" means only that an activity
              is described in the Annexes at all — alignment unassessed.
            </p>
            <p>
              Tellumen classifies against the Climate Change Mitigation objective only (Annex I
              of Delegated Regulation (EU) 2021/2139), by NACE code — conservatively, with no
              forced matches:
            </p>
            <ul className="space-y-1 text-[13px] text-gray-600">
              <li>· <code className="rounded bg-gray-100 px-1 py-0.5 text-[12px]">68.20</code> Real estate → <b>eligible</b> — Annex I §7.7, Acquisition and ownership of buildings</li>
              <li>· <code className="rounded bg-gray-100 px-1 py-0.5 text-[12px]">35.11</code> Electricity generation → <b>eligible</b> — Annex I §4</li>
              <li>· Manufacturing, warehousing, hospitality, agriculture → not covered by Annex I's Climate Change Mitigation activity list</li>
            </ul>
            <p className="text-[13px] text-gray-500">
              We do not, and cannot honestly, verify substantial contribution or minimum
              safeguards — those require building floor area + EPC ratings, generation-source
              mix, and counterparty-level OECD/ILO compliance diligence that this platform
              doesn't collect. So the classifier <b>never returns "aligned"</b> — only
              "eligible" or "not eligible" — until that data exists. An asset's own physical-risk
              score does feed one real diagnostic: a High/Very High bucket with no documented
              resilience measures is flagged as a genuine do-no-significant-harm concern under
              Article 17 — visible on the asset's own detail view, never silently ignored.
            </p>
          </MethodologyCard>
        </div>

        <footer className="mt-8 rounded-2xl border border-gray-200/70 bg-white p-6 text-sm leading-relaxed text-gray-500 shadow-sm">
          <span className="font-medium text-[#1d1d1f]">Why this page exists.</span> A number
          without its method is a claim, not evidence. Every figure here traces to either a
          disclosed internal methodology or a cited primary source — never the other way around.
        </footer>
      </div>
    </div>
  )
}

function MethodologyCard({ icon: Icon, title, eyebrow, children }) {
  return (
    <section className="rounded-2xl border border-gray-200/70 bg-white p-6 shadow-sm">
      <div className="flex items-center gap-3">
        <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-[#0071e3]/10 text-[#0071e3]">
          <Icon size={20} strokeWidth={1.5} />
        </span>
        <div>
          <h2 className="text-lg font-semibold tracking-tight text-[#1d1d1f]">{title}</h2>
          <p className="text-[12px] text-gray-400">{eyebrow}</p>
        </div>
      </div>
      <div className="mt-4 space-y-3 text-[14px] leading-relaxed text-gray-700">{children}</div>
    </section>
  )
}

function Quote({ source, children }) {
  return (
    <blockquote className="border-l-2 border-[#0071e3]/30 pl-4 text-[13px] italic leading-relaxed text-gray-600">
      {children}
      <footer className="mt-1 not-italic text-[11px] text-gray-400">— {source}</footer>
    </blockquote>
  )
}
