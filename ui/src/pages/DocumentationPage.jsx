import { useState, useEffect } from 'react'
import { Rocket, Cpu, Database, Code2, Scale } from 'lucide-react'
import { fetchModels } from '../api/client'

const SECTIONS = [
  { id: 'start',   label: 'Getting started', icon: Rocket },
  { id: 'method',  label: 'Methodology & model cards', icon: Cpu },
  { id: 'data',    label: 'Data sources', icon: Database },
  { id: 'api',     label: 'API reference', icon: Code2 },
  { id: 'reg',     label: 'Regulatory mapping', icon: Scale },
]

const SKILL = (auc) =>
  auc == null ? { t: 'physics-based', c: 'text-gray-500 bg-gray-100' }
  : auc >= 0.75 ? { t: 'strong', c: 'text-emerald-700 bg-emerald-50' }
  : auc >= 0.6  ? { t: 'moderate', c: 'text-amber-700 bg-amber-50' }
  : { t: 'limited', c: 'text-red-700 bg-red-50' }

export default function DocumentationPage({ auth }) {
  const [section, setSection] = useState('start')
  return (
    <div className="flex h-full overflow-hidden bg-[#f5f5f7]">
      <aside className="w-60 shrink-0 border-r border-gray-200 bg-white p-3">
        <p className="px-3 pb-2 pt-1 text-[11px] font-medium uppercase tracking-[0.12em] text-gray-400">Documentation</p>
        {SECTIONS.map(s => {
          const on = section === s.id, Icon = s.icon
          return (
            <button key={s.id} onClick={() => setSection(s.id)}
              className={`flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-left text-[13px] transition ${
                on ? 'bg-[#0071e3]/10 font-medium text-[#0071e3]' : 'text-gray-600 hover:bg-gray-100'}`}>
              <Icon size={15} strokeWidth={1.8} /> {s.label}
            </button>
          )
        })}
      </aside>
      <div className="flex-1 overflow-y-auto">
        <div className="mx-auto max-w-3xl px-8 py-10">
          {section === 'start'  && <GettingStarted auth={auth} />}
          {section === 'method' && <Methodology />}
          {section === 'data'   && <DataSources />}
          {section === 'api'    && <ApiRef />}
          {section === 'reg'    && <RegMapping />}
        </div>
      </div>
    </div>
  )
}

function H({ children }) { return <h1 className="text-2xl font-semibold tracking-tight text-[#1d1d1f]">{children}</h1> }
function P({ children }) { return <p className="mt-3 text-[15px] leading-relaxed text-gray-600">{children}</p> }
function Card({ children }) { return <div className="mt-4 rounded-2xl border border-gray-200/70 bg-white p-5 shadow-sm">{children}</div> }
function Sub({ children }) { return <h2 className="mt-8 text-[15px] font-semibold text-[#1d1d1f]">{children}</h2> }

function GettingStarted({ auth }) {
  return (
    <div>
      <H>Getting started</H>
      <P>
        Welcome{auth?.user?.full_name ? `, ${auth.user.full_name.split(' ')[0]}` : ''}. Your organization
        <b> {auth?.org?.name}</b> licenses the modules shown under <b>Modules</b>. Everything reads one
        live view of climate risk — you apply your own maths on top.
      </P>
      <Sub>The operating loop</Sub>
      <Card>
        <ol className="space-y-2 text-[14px] text-gray-600">
          <li><b>1 · Sense</b> — live satellite, weather and seismic data land continuously.</li>
          <li><b>2 · Score</b> — the engine turns it into one 0–100 risk per hazard, per location.</li>
          <li><b>3 · Project</b> — scores are projected onto your assets under chosen scenarios & horizons.</li>
          <li><b>4 · Act</b> — disclose, price, and act — every figure traceable to model version + data vintage.</li>
        </ol>
      </Card>
      <Sub>Your access</Sub>
      <P>
        You are signed in as <b>{(auth?.roles || []).join(', ') || 'user'}</b>. Your role determines which
        actions you can take (e.g. publishing a disclosure may require a separate approver under the
        four-eyes principle). Admins manage users and permissions under <b>Admin</b>.
      </P>
    </div>
  )
}

function Methodology() {
  const [models, setModels] = useState(null)
  useEffect(() => { fetchModels().then(d => setModels(d.models || [])).catch(() => setModels([])) }, [])
  return (
    <div>
      <H>Methodology & model cards</H>
      <P>
        Each hazard is scored by a dedicated model. We report <b>out-of-sample</b> skill (leave-one-event-out),
        not in-sample fit — and we publish where a model has limited skill rather than hiding it. ROC-AUC is
        shown with the honest caveat that it overstates rare-event models; treat it alongside the validation note.
      </P>
      {models === null && <P>Loading model registry…</P>}
      {models && models.length === 0 && <P>Model registry unavailable.</P>}
      <div className="mt-4 space-y-3">
        {(models || []).filter(m => m.is_active !== false).map((m, i) => {
          const s = SKILL(m.auc)
          return (
            <div key={i} className="rounded-2xl border border-gray-200/70 bg-white p-5 shadow-sm">
              <div className="flex items-center justify-between">
                <h3 className="text-[15px] font-semibold capitalize">{(m.hazard_type || '').replace('_', ' ')}</h3>
                <span className={`rounded-full px-2 py-0.5 text-[11px] font-semibold ${s.c}`}>{s.t}</span>
              </div>
              <div className="mt-2 flex flex-wrap gap-x-6 gap-y-1 text-[13px] text-gray-500">
                <span>Algorithm: <b className="text-gray-700">{m.algorithm || '—'}</b></span>
                <span>Version: <b className="text-gray-700">{m.model_version || '—'}</b></span>
                {m.auc != null && <span>AUC (LOEO): <b className="text-gray-700">{Number(m.auc).toFixed(3)}</b></span>}
                {m.avg_precision != null && <span>Avg precision: <b className="text-gray-700">{Number(m.avg_precision).toFixed(3)}</b></span>}
              </div>
              {m.validation_note && <p className="mt-2 border-l-2 border-gray-200 pl-3 text-[13px] italic text-gray-500">{m.validation_note}</p>}
            </div>
          )
        })}
      </div>
    </div>
  )
}

function DataSources() {
  const rows = [
    ['Copernicus ERA5', 'Reanalysis weather (temperature, precipitation)', 'Hourly · global'],
    ['GloFAS', 'Global flood forecasting & river discharge', 'Daily'],
    ['NASA FIRMS', 'Active fire / thermal anomalies', 'Near-real-time'],
    ['Sentinel', 'Optical & radar earth observation', 'Per overpass'],
    ['EMSC · USGS', 'Global seismicity (events, magnitude, depth)', 'Real-time'],
    ['Sen · ISS', 'Live Earth imagery from orbit', 'Live'],
  ]
  return (
    <div>
      <H>Data sources</H>
      <P>The golden source is built from primary, authoritative feeds keyed to a global H3 hex grid (res-8, ~0.7km² cells). Every score records the data vintage it was computed from.</P>
      <Card>
        <table className="w-full text-[13px]">
          <thead><tr className="text-left text-gray-400"><th className="pb-2 font-medium">Source</th><th className="pb-2 font-medium">What</th><th className="pb-2 font-medium">Cadence</th></tr></thead>
          <tbody>
            {rows.map(r => (
              <tr key={r[0]} className="border-t border-gray-100">
                <td className="py-2 font-medium text-[#1d1d1f]">{r[0]}</td>
                <td className="py-2 text-gray-600">{r[1]}</td>
                <td className="py-2 text-gray-500">{r[2]}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
    </div>
  )
}

function ApiRef() {
  const eps = [
    ['POST', '/v1/auth/login', 'Exchange email + password for a session token'],
    ['GET',  '/v1/auth/me', 'Current profile, roles, permissions, entitlements'],
    ['GET',  '/v1/bank/portfolio', 'Loan book projected onto the golden source'],
    ['GET',  '/v1/bank/summary', 'Command-center rollup (value-at-risk, buckets)'],
    ['GET',  '/v1/bank/disclosure', 'TCFD / EU-Taxonomy disclosure pack'],
    ['GET',  '/v1/platform/models', 'Model registry with honest skill metrics'],
    ['POST', '/v1/approvals', 'Submit a request for four-eyes approval'],
    ['GET',  '/v1/portal/requests', 'Your organization’s service requests'],
  ]
  const color = { GET: 'text-emerald-700 bg-emerald-50', POST: 'text-blue-700 bg-blue-50', PATCH: 'text-amber-700 bg-amber-50' }
  return (
    <div>
      <H>API reference</H>
      <P>All endpoints are under <code className="rounded bg-gray-100 px-1.5 py-0.5 text-[13px]">/api</code> and take a Bearer token: <code className="rounded bg-gray-100 px-1.5 py-0.5 text-[13px]">Authorization: Bearer &lt;token&gt;</code>. Access is scoped to your organization and gated by your permissions.</P>
      <Card>
        <div className="space-y-2">
          {eps.map(e => (
            <div key={e[1]} className="flex items-center gap-3 border-b border-gray-100 py-2 last:border-0">
              <span className={`w-14 shrink-0 rounded px-2 py-0.5 text-center text-[11px] font-semibold ${color[e[0]]}`}>{e[0]}</span>
              <code className="w-56 shrink-0 text-[13px] text-[#1d1d1f]">{e[1]}</code>
              <span className="text-[13px] text-gray-500">{e[2]}</span>
            </div>
          ))}
        </div>
      </Card>
    </div>
  )
}

function RegMapping() {
  const rows = [
    ['TCFD', 'Physical risk exposure, scenario analysis', 'Command center · Reports'],
    ['EU Taxonomy (Art. 8)', 'Alignment, eligibility, DNSH screening', 'Reports'],
    ['CSRD / ESRS E1', 'Material physical risks by time horizon', 'Reports'],
    ['ECB / EBA Pillar 3', 'Geographic & hazard exposure tables', 'Portfolio · Reports'],
  ]
  return (
    <div>
      <H>Regulatory mapping</H>
      <P>How the platform’s outputs line up with the disclosure frameworks. Every figure is traceable to the model version and data vintage that produced it — the evidence an auditor asks for.</P>
      <Card>
        <table className="w-full text-[13px]">
          <thead><tr className="text-left text-gray-400"><th className="pb-2 font-medium">Framework</th><th className="pb-2 font-medium">What we provide</th><th className="pb-2 font-medium">Where</th></tr></thead>
          <tbody>
            {rows.map(r => (
              <tr key={r[0]} className="border-t border-gray-100">
                <td className="py-2 font-medium text-[#1d1d1f]">{r[0]}</td>
                <td className="py-2 text-gray-600">{r[1]}</td>
                <td className="py-2 text-gray-500">{r[2]}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
    </div>
  )
}
