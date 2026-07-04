import { useState, useEffect, useCallback } from 'react'
import { Bolt, Zap, Wallet, ShieldCheck, Loader2 } from 'lucide-react'
import ContextBar from '../../components/ContextBar'
import { fetchInsuranceTriggers, fetchInsurancePortfolio, setTriggerConfig } from '../../api/client'

const mn = n => '€' + ((n || 0) / 1e6).toFixed(2) + 'm'
const HAZARDS = ['flood', 'heat_acute', 'heat_chronic', 'wildfire', 'drought', 'storm', 'seismic', 'volcanic', 'pollution']

export default function ParametricTriggers({ auth }) {
  const [scenario, setScenario] = useState('baseline')
  const [horizon, setHorizon] = useState('current')
  const [data, setData] = useState(null)
  const [policies, setPolicies] = useState([])

  const reload = useCallback(() => {
    fetchInsuranceTriggers({ scenario, horizon }).then(setData).catch(() => setData(null))
    fetchInsurancePortfolio({ scenario, horizon }).then(x => setPolicies(x.policies || [])).catch(() => {})
  }, [scenario, horizon])
  useEffect(() => { setData(null); reload() }, [reload])

  const canConfigure = new Set(auth?.permissions || []).has('pricing.approve')
  const r = data?.rollup

  return (
    <div className="flex h-full flex-col bg-[#f5f5f7]">
      <ContextBar scenario={scenario} horizon={horizon} onScenario={setScenario} onHorizon={setHorizon}
        vintage="2024-10-29" label={`Insurance · ${data?.org?.name || 'Iberia Mutual (demo)'}`} />

      <div className="flex-1 overflow-y-auto px-8 py-8">
        <header className="mb-6">
          <div className="flex items-center gap-1.5 text-xs font-medium uppercase tracking-[0.12em] text-gray-400">
            <Bolt size={13} /> Parametric
          </div>
          <h1 className="mt-2 text-3xl font-semibold tracking-tight text-[#1d1d1f]">Trigger monitoring</h1>
          <p className="mt-2 max-w-2xl text-[15px] text-gray-500">
            No claims process — a policy's live hazard score crossing its agreed attachment/exhaustion band
            <i> is</i> the payout decision, computed off the exact same golden source every other view reads.
          </p>
        </header>

        {!r ? <p className="text-gray-400">loading…</p> : (
          <>
            <div className="grid grid-cols-3 gap-4">
              <Stat icon={Zap} label="Configured triggers" value={r.n_configured} />
              <Stat icon={Bolt} label="Triggered now" value={r.n_triggered_now} accent="#c2410c" />
              <Stat icon={Wallet} label="Total payout if triggered" value={mn(r.total_payout_if_triggered_eur)} accent="#0071e3" />
            </div>

            <section className="mt-6 rounded-2xl border border-gray-200/70 bg-white p-5 shadow-sm">
              <h2 className="text-[13px] font-semibold text-[#1d1d1f]">Triggered now <span className="font-normal text-gray-400">— band crossed, payout due</span></h2>
              {data.triggered_now.length ? (
                <div className="mt-3 divide-y divide-gray-100">
                  {data.triggered_now.map(p => <TriggerRow key={p.policy_id} p={p} />)}
                </div>
              ) : (
                <div className="mt-4 flex items-center gap-2 rounded-xl bg-emerald-50 px-3 py-3 text-[13px] text-emerald-700">
                  <ShieldCheck size={16} /> No configured trigger is currently in its payout band.
                </div>
              )}
            </section>

            <section className="mt-6 rounded-2xl border border-gray-200/70 bg-white p-5 shadow-sm">
              <h2 className="text-[13px] font-semibold text-[#1d1d1f]">All configured triggers</h2>
              {data.configured.length ? (
                <div className="mt-3 divide-y divide-gray-100">
                  {data.configured.map(p => <TriggerRow key={p.policy_id} p={p} />)}
                </div>
              ) : <p className="mt-3 text-[12px] text-gray-400">No policy has a trigger band configured yet.</p>}
            </section>

            {canConfigure && (
              <section className="mt-6 rounded-2xl border border-gray-200/70 bg-white p-5 shadow-sm">
                <h2 className="text-[13px] font-semibold text-[#1d1d1f]">Set up a trigger</h2>
                <ConfigForm policies={policies} onSaved={reload} />
              </section>
            )}
          </>
        )}
      </div>
    </div>
  )
}

function TriggerRow({ p }) {
  const t = p.trigger
  return (
    <div className="flex items-center justify-between py-2.5">
      <div className="min-w-0">
        <div className="truncate text-[13px] font-medium text-[#1d1d1f]">{p.policy_name}</div>
        <div className="text-[11px] text-gray-400">
          {p.region} · {t.hazard_type} · band {t.attachment_score}–{t.exhaustion_score}
          {t.current_score != null && ` · current ${t.current_score}`}
        </div>
      </div>
      <div className="text-right">
        <div className={`text-[15px] font-semibold ${t.is_triggered ? 'text-[#c2410c]' : 'text-gray-400'}`}>
          {t.payout_pct}% · {mn(t.payout_eur)}
        </div>
        {t.updated_at && <div className="text-[10px] text-gray-400">set {String(t.updated_at).slice(0, 10)}</div>}
      </div>
    </div>
  )
}

function ConfigForm({ policies, onSaved }) {
  const [policyId, setPolicyId] = useState('')
  const [hazard, setHazard] = useState('flood')
  const [attachment, setAttachment] = useState(60)
  const [exhaustion, setExhaustion] = useState(90)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  async function save() {
    if (!policyId) { setError('Choose a policy'); return }
    setBusy(true); setError(null)
    try {
      await setTriggerConfig(policyId, hazard, Number(attachment), Number(exhaustion))
      onSaved()
    } catch (e) {
      setError(e.message || 'Could not save trigger config.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="mt-3 grid grid-cols-5 gap-3">
      <select value={policyId} onChange={e => setPolicyId(e.target.value)}
        className="col-span-2 rounded-lg border border-gray-200 px-2 py-1.5 text-[13px] outline-none focus:border-[#0071e3]">
        <option value="">Select a policy…</option>
        {policies.map(p => <option key={p.policy_id} value={p.policy_id}>{p.policy_name} — {p.region}</option>)}
      </select>
      <select value={hazard} onChange={e => setHazard(e.target.value)}
        className="rounded-lg border border-gray-200 px-2 py-1.5 text-[13px] capitalize outline-none focus:border-[#0071e3]">
        {HAZARDS.map(h => <option key={h} value={h}>{h.replace('_', ' ')}</option>)}
      </select>
      <input type="number" min={0} max={100} value={attachment} onChange={e => setAttachment(e.target.value)}
        placeholder="Attachment" className="rounded-lg border border-gray-200 px-2 py-1.5 text-[13px] outline-none focus:border-[#0071e3]" />
      <input type="number" min={0} max={100} value={exhaustion} onChange={e => setExhaustion(e.target.value)}
        placeholder="Exhaustion" className="rounded-lg border border-gray-200 px-2 py-1.5 text-[13px] outline-none focus:border-[#0071e3]" />
      <div className="col-span-5 flex items-center gap-3">
        <button onClick={save} disabled={busy}
          className="rounded-full bg-[#0071e3] px-4 py-1.5 text-[12px] font-medium text-white disabled:opacity-50">
          {busy ? <Loader2 size={13} className="animate-spin" /> : 'Save trigger'}
        </button>
        {error && <span className="text-[12px] text-red-600">{error}</span>}
      </div>
    </div>
  )
}

function Stat({ icon: Icon, label, value, accent }) {
  return (
    <div className="rounded-2xl border border-gray-200/70 bg-white p-4 shadow-sm">
      <div className="flex items-center gap-1.5 text-[11px] uppercase tracking-wide text-gray-400"><Icon size={13} /> {label}</div>
      <div className="mt-1.5 text-2xl font-semibold tracking-tight" style={{ color: accent || '#1d1d1f' }}>{value}</div>
    </div>
  )
}
