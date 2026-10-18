import { Drawer } from '../../components/Drawer'
import { CloseButton } from '../../components/Dialog'
import { StatGrid } from '../../components/ui'
import { StatusChip } from '../../components/StatusChip'
import { DetailsBody, HEADING, InfoButton, MessageLine, messageDetails } from '../../components/Details'
import { balance } from '../../lib/money'
import { PERIL_COLOR, PERIL_LABEL, regionName, type PerilBlock } from './types'

// One peril's standard-formula capital, region by region (S.27.01.01's rows): bars after reinsurance, how each region was
// charged one click away, the exact figures and the legal basis below.
const METHOD_TONE = { exact_zonal: 'good', grouped_art90b: 'warn', single_zone: 'neutral' } as const
const SCENARIO = { A: 'scenario A', B: 'scenario B' } as const      // the Regulation's two event sets, by its own names

export default function PerilDrawer({ b, onClose }: { b: PerilBlock; onClose: () => void }) {
  const name = PERIL_LABEL[b.peril]
  const regions = b.regions ?? []
  const o = b.other_regions
  const max = Math.max(1, ...regions.map(r => r.after_eur), o?.after_eur ?? 0)
  const methods = [...new Set(regions.map(r => r.method_message.label))]
  const one = methods.length === 1 ? regions[0] : null       // every region charged the same way: said once
  const how = (r: (typeof regions)[number]) => <>
    <StatusChip label={r.method_message.label} tone={METHOD_TONE[r.method]} />
    <InfoButton compact details={messageDetails(r.method_message)} />
  </>
  const h = (t: string) => <h4 className="text-[12px] font-semibold uppercase tracking-[0.08em] text-[var(--color-mute)] mt-6 mb-2">{t}</h4>
  return (
    <Drawer label={`${name} by region`} onClose={onClose} className="w-full max-w-lg h-full overflow-y-auto bg-[var(--color-bg-2)] border-l border-[var(--color-line)] p-5">
      <div className="flex items-center justify-between gap-3 mb-4">
        <div className="flex items-center gap-2 text-[16px] font-semibold text-[var(--color-ink)]">
          <span className="w-2.5 h-2.5 rounded-full" style={{ background: PERIL_COLOR[b.peril] }} />{name} by region
        </div>
        <CloseButton onClick={onClose} />
      </div>
      <StatGrid cols={3} items={[
        { label: 'After reinsurance', value: balance(b.after_eur), accent: 'var(--color-sky)' },
        { label: 'Before reinsurance', value: balance(b.before_eur) },
        { label: 'Diversification', value: balance(b.diversification_after_eur), sub: 'between regions' },
      ]} />
      {h('Capital by region, after reinsurance')}
      {one && <div className="flex items-center gap-2 mb-3 text-[12px] text-[var(--color-mute)]">Every region: {how(one)}</div>}
      <ul className="m-0 p-0 list-none space-y-3">
        {regions.map(r => (
          <li key={r.region}>
            <div className="flex items-baseline justify-between gap-3 text-[12.5px]">
              <span className="text-[var(--color-ink)]" title={r.region_name}>{regionName(r.region, r.region_name)}</span>
              <span className="tabular-nums text-[var(--color-ink)]">{balance(r.after_eur)}</span>
            </div>
            <div className="h-2.5 mt-1 rounded-full bg-[var(--color-panel-2)] relative overflow-hidden">
              <div className="absolute inset-y-0 left-0 rounded-full" style={{ width: `${Math.max(1.5, (r.after_eur / max) * 100)}%`, background: PERIL_COLOR[b.peril] }} />
            </div>
            <div className="flex flex-wrap items-center gap-2 mt-1.5 text-[11.5px] text-[var(--color-faint)] tabular-nums">
              {!one && how(r)}
              <span>{balance(r.exposure_eur)} insured · {r.n_policies} {r.n_policies === 1 ? 'policy' : 'policies'}</span>
            </div>
          </li>
        ))}
        {o && (
          <li>
            <div className="flex items-baseline justify-between gap-3 text-[12.5px]">
              <span className="text-[var(--color-ink)]">Other countries</span>
              <span className="tabular-nums text-[var(--color-ink)]">{o.after_eur != null ? balance(o.after_eur) : '—'}</span>
            </div>
            {o.after_eur != null && (
              <div className="h-2.5 mt-1 rounded-full bg-[var(--color-panel-2)] relative overflow-hidden">
                <div className="absolute inset-y-0 left-0 rounded-full" style={{ width: `${Math.max(1.5, (o.after_eur / max) * 100)}%`, background: PERIL_COLOR[b.peril] }} />
              </div>
            )}
            <div className="flex flex-wrap items-center gap-2 mt-1.5 text-[11.5px] tabular-nums">
              <MessageLine m={o.message} className={o.status === 'computed' ? 'text-[var(--color-mute)]' : 'text-[var(--color-warn)]'} />
              <span className="text-[var(--color-faint)]">{balance(o.exposure_eur)} insured</span>
            </div>
          </li>
        )}
      </ul>
      {!!b.not_charged_exposure_eur && (
        <div className="mt-4 flex items-center gap-1.5 text-[12px] text-[var(--color-mute)] tabular-nums">
          {balance(b.not_charged_exposure_eur)} insured where the Regulation sets no {name.toLowerCase()} charge
          <InfoButton compact details={{ title: 'Not charged for this peril', sections: [
            { heading: HEADING.shows, body: `These properties are in countries listed in Annex XIII but in no ${name.toLowerCase()} region of the Regulation, so this peril charges nothing for them.` },
          ] }} />
        </div>
      )}
      {h('Figures by region')}
      <div className="overflow-x-auto">
        <table className="w-full text-[12px] tabular-nums">
          <thead><tr className="text-left text-[var(--color-mute)] border-b border-[var(--color-line)]">
            <th className="py-1.5 pr-3 font-medium">Region</th><th className="pr-3 font-medium text-right">Insured</th>
            <th className="pr-3 font-medium text-right">Specified loss</th><th className="pr-3 font-medium text-right">Before</th>
            <th className="font-medium text-right">After</th>
          </tr></thead>
          <tbody>
            {regions.map(r => (
              <tr key={r.region} className="border-b border-[var(--color-line)]">
                <td className="py-1.5 pr-3 text-[var(--color-ink)]">{regionName(r.region, r.region_name)}{r.scenario && <span className="text-[var(--color-faint)]"> · {SCENARIO[r.scenario]}</span>}</td>
                <td className="pr-3 text-right">{balance(r.exposure_eur)}</td>
                <td className="pr-3 text-right">{balance(r.specified_gross_loss_eur)}</td>
                <td className="pr-3 text-right">{balance(r.before_eur)}</td>
                <td className="text-right text-[var(--color-ink)]">{balance(r.after_eur)}</td>
              </tr>
            ))}
            <tr><td className="py-1.5 pr-3 font-medium text-[var(--color-ink)]" colSpan={3}>After diversification between regions</td>
              <td className="pr-3 text-right">{balance(b.before_eur)}</td><td className="text-right font-medium text-[var(--color-ink)]">{balance(b.after_eur)}</td></tr>
          </tbody>
        </table>
      </div>
      {b.citation && <div className="mt-6"><DetailsBody sections={[{ heading: 'Legal basis', body: b.citation }]} /></div>}
    </Drawer>
  )
}
