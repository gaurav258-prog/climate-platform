// In-product documentation — the customer-facing help centre content.
//
// Real product documentation, authored against what the software actually does today. Where a capability is
// on the roadmap (direct integration, SSO), the docs say so plainly rather than implying it exists. Content
// is static and versioned with the app; sector-aware articles (AGRI vs financial) are gated by `sectors`.
// Rendered by pages/Docs.tsx with a small markdown subset (##/###, -, 1., **bold**, `code`, > callout).

export interface DocArticle {
  slug: string
  title: string
  category: string
  summary: string
  sectors?: string[]        // undefined = all sectors; else organizations.type values
  body: string
}

export const AGRI = ['manufacturer']
export const FIN = ['bank', 'insurer', 'asset_manager', 'reit']

// Display order of categories in the index.
export const DOC_CATEGORIES = [
  'Getting started', 'Your workspace', 'Compliance & filing', 'Governance & trust', 'Data foundation', 'Help',
]

export const DOCS: DocArticle[] = [
  {
    slug: 'welcome', title: 'Welcome to Tellumen', category: 'Getting started',
    summary: 'What Tellumen does, and the operating loop your team works through.',
    body: `
Tellumen turns **physical climate and nature risk** into decisions and disclosures you can defend. It scores
every located asset you hold against nine hazards — heat, drought, flood, fire, storm, seismic, frost, water
stress and deforestation — off authoritative satellite and agency data, then projects that risk forward under
recognised warming pathways.

## The operating loop
Everything in the product follows the same four-step loop:

1. **Sense** — bring your book in and locate it. We reconcile and geocode every asset to a precise grid cell.
2. **Score** — each asset is scored against the hazards that matter, from the golden source.
3. **Project** — see how the risk moves to 2030, 2050 and 2100 under different warming paths.
4. **Act** — produce a filing, a management report, or a risk decision — governed and reproducible.

## What you will not see
A number Tellumen cannot stand behind. Where a figure isn't sufficiently evidenced, it shows as **"—"**,
never a guess. See *Why a figure sometimes shows "—"* for the rule behind this.

> New here? Start with **Users, roles & access**, then **Getting your data in**.
`,
  },
  {
    slug: 'roles-access', title: 'Users, roles & access', category: 'Getting started',
    summary: 'The four roles, what each can do, and the two-person rule.',
    body: `
Your organization is set up with role-based access. A **super user (admin)** creates the other users and
assigns them roles — access is individual to your organization.

## The four roles
- **Admin** — manages users and roles, sets the reporting identity and basis, and keeps the house in order.
- **Analyst** — does the work: brings data in, runs scores, prepares filings (the *maker*).
- **Approver** — signs off what an analyst prepares (the *checker*).
- **Viewer** — read-only access to the workspace and reports.

## The two-person rule (4-eyes)
Anything sensitive — publishing a figure, releasing a filing, changing the reporting basis — needs a second
pair of eyes. The person who prepares a change **cannot approve their own**. This is enforced in the system,
not just by policy. See *Approvals & 4-eyes*.

> Only an admin sees the **Control center**. Only Tellumen staff see the platform console.
`,
  },
  {
    slug: 'data-in', title: 'Getting your data in', category: 'Your workspace',
    summary: 'The three ways to bring your book in, and the validation gate that checks it.',
    body: `
Your team feeds the software in one of three ways:

1. **Manual entry** — add an asset directly in the workspace.
2. **Template upload** — download the template for your sector, fill it, and upload the CSV. This is the
   fastest way to bring a whole book in.
3. **Direct integration** — a secure API push from your source systems using a tenant **ingest token**. An
   admin creates a token in **Control center › Integrations**; your system then POSTs rows to the ingest API,
   which validates, locates and scores them exactly like an upload. *(Live for banking today; other sectors'
   push endpoints are rolling out — the token and handshake work for every sector now.)*

## The validation gate
Nothing is silently accepted. On upload we check schema, units, and completeness, then return a **coverage
report** telling you exactly what landed, what's missing, and where a location could only be resolved coarsely.
We never invent a value to fill a gap — a missing field is reported, not guessed.

## What "your book" means for you
- **Bank** — your loan tape / financed assets.
- **Insurer** — your schedule of values (insured locations).
- **Asset manager** — your holdings (ISINs resolve to issuers automatically).
- **REIT** — your properties.
- **Agriculture** — your operational sites and sourcing plots.
`,
  },
  {
    slug: 'globe', title: 'The globe & your assets', category: 'Your workspace',
    summary: 'The front door — every asset you hold, at true coordinates, with its risk trajectory.',
    body: `
**Horizon** is the front door. It opens on a live globe of *your* assets at their real coordinates, each
carrying its worst-hazard score and how that score moves through 2030 / 2050 / 2100.

## Reading it
- **Colour / score** — the worst hazard for that asset at the chosen horizon.
- **Play to a year** — step the whole book forward under a warming path; the slider scrubs, the year chips
  set the target.
- **Click any asset** — see its per-hazard detail, the sector facts (loan, sum insured, position, NOI…), and
  the honest adaptation measures for that hazard.

## On-demand scoring
Zoom into the granular grid and Tellumen scores the cells around a site on demand, from the same golden
source — so you see the risk *texture* around a location, not just one cell. A cell stays blank only where the
underlying baselines genuinely have no coverage (open ocean, polar gaps).
`,
  },
  {
    slug: 'reporting-basis', title: 'Setting your reporting basis', category: 'Compliance & filing',
    summary: 'What you configure to suit your needs — and what stays locked for integrity.',
    body: `
Parameterisation is where the software is tuned to *your* needs and compliance requirements. Some of it is
yours to set; some of it is deliberately not.

## Yours to configure (governed by 4-eyes)
- **Reporting period** — the as-of window for a filing.
- **Scenario & horizon** — the warming pathway and the year you report against.
- **Materiality** — the threshold that decides what's surfaced.
- **Reporting identity** — your legal entity, LEI, EORI and filing contact (auto-filled from the GLEIF
  registry where possible).

## Locked — our integrity, not a setting
- **Model calibration** and the **r² ≥ 0.40 publish gate** are *not* customer-tunable. They are what keep a
  published number honest and comparable across clients. You can choose *what* to report; you cannot loosen
  the bar a figure must clear to be publishable. See *Why a figure sometimes shows "—"*.
`,
  },
  {
    slug: 'producing-a-filing', title: 'Producing a disclosure', category: 'Compliance & filing',
    summary: 'From scored book to a filed, frozen, auditable disclosure.',
    body: `
Tellumen assembles the mandated tables for the frameworks in scope and takes them through a governed release.

## Frameworks
- **SFDR** — the Principal Adverse Impact statement (Annex I), including the physical-climate indicators.
- **EU Taxonomy (Art. 8)** — alignment and the climate-adaptation objective, with DNSH / minimum-safeguards.
- **CSRD / ESRS** — E1 physical risk, E3 water, E4 deforestation, bound to the EFRAG taxonomy.
- **EUDR** — the due-diligence statement against forest-loss data *(TRACES submission is sandbox-ready)*.
- **PCAF / TCFD** — financed emissions and physical-risk scenario reporting.

## The release
1. An **analyst** prepares the filing on the chosen basis.
2. An **approver** signs it off (4-eyes).
3. On publish, the filing is **frozen to an immutable snapshot** — hash-sealed and version-stamped — so you
   can prove exactly what was filed and reproduce it later.
4. An **evidence pack** keyed to that snapshot is available for your auditor.

## Outputs
Human-readable (dashboard, PDF, Excel) and machine-readable (iXBRL/ESEF, CSV, API). You then forward the
output to your other systems, or use it directly for internal risk and management reporting.
`,
  },
  {
    slug: 'approvals', title: 'Approvals & 4-eyes', category: 'Governance & trust',
    summary: 'How a change is raised, routed, and decided by a second person.',
    body: `
Sensitive changes land in **Approvals** for a second person to action.

## The flow
1. A maker submits a change (publish a figure, release a filing, change the basis…). It becomes a **pending
   request**.
2. Optionally, route it to a **named approver** — select them and click *Send* (it doesn't execute on select).
3. An approver (anyone but the maker) **approves**, **rejects**, or **sends it back** with a comment.

## What you'll see
- A request you raised shows its controls greyed with the reason — you can't approve your own (4-eyes).
- The cockpit tells an approver *"N approvals waiting for you"*, counting only what they can actually action.

Every decision, comment and assignment is written to the audit trail.
`,
  },
  {
    slug: 'honesty-model', title: 'Why a figure sometimes shows "—"', category: 'Governance & trust',
    summary: 'The publish gate, the ranged tier, and the confidence grade — the rules that keep a number honest.',
    body: `
Tellumen would rather show nothing than show a number it can't defend. Three mechanisms enforce that.

## The publish gate (r² ≥ 0.40, out-of-sample)
A euro-at-risk figure only publishes when its driver explains the outcome **out-of-sample** at r² ≥ 0.40.
Below that bar the figure is **held** — you see the physical risk, but not a euro number that isn't earned.
This threshold is a fixed integrity constant; it is not a setting.

## The ranged tier
Where a driver explains an outcome *partly*, we publish a **band** with its r² stated, rather than a false
point estimate.

## The confidence grade (A–E)
Every published figure carries a composite **A–E confidence grade** folding in fit quality, data coverage and
input confidence — so you know how much to lean on it.

> €-at-risk is **climate-physical only**. It excludes non-climate drivers (war, fuel prices, policy). A
> missing or un-evidenced figure always reads as "—", never a guess.
`,
  },
  {
    slug: 'golden-source', title: 'The golden source & freshness', category: 'Data foundation',
    summary: 'Where the data comes from, and how it stays current on its own.',
    body: `
Your risk is scored off data **direct from Europe's and America's satellites and agencies** — reconciled,
versioned, and carrying its provenance on every row.

## The feeds
ERA5 / Copernicus (climate reanalysis), NASA FIRMS (active fire), NOAA IBTrACS (cyclones), USGS & GEM
(seismic), Hansen GFC (forest loss), GLEIF (legal-entity registry), EXIOBASE & Climate TRACE (emissions).

## It stays fresh on its own
Each feed refreshes on its own cadence — you don't press a button. A **health monitor** tracks every feed's
last status; if a refresh is overdue or fails, it surfaces as a pre-filing control (in the cockpit and in the
Control center) so a stale input can never quietly reach a filing.

## Provenance
Every score records the source vintage and the model version that produced it, so any number traces back to
the exact feed and calibration behind it.
`,
  },
  {
    slug: 'architecture', title: 'How Tellumen is built', category: 'Data foundation',
    summary: 'The layered architecture, in plain terms — for your risk, data and audit teams.',
    body: `
For teams that want to understand what sits under the workspace, Tellumen is a layered platform. Data flows
down; results feed back up.

## The layers
1. **People & access** — your admin, analysts, approvers and viewers, each scoped by role and tenant.
2. **Ingestion** — the golden feeds we bring and the data you bring (upload today, direct integration on the
   roadmap), through one validation gate.
3. **Knowledge** — reconciliation and data quality over a zoned database: raw as-landed, a curated golden
   record (append-only, write-once), your operational data, and a governance zone (audit + frozen snapshots).
4. **The engine** — the hazard models, scoring, projections and the r² publish gate, then 4-eyes and freeze.
5. **Output** — your portfolio book, disclosures, filings and evidence pack.

## The spine that runs through all of it
Named golden source → validated input → locked model → governed decision (4-eyes) → immutable snapshot →
auditable artifact. Every published figure is reproducible from its frozen, provenance-tracked snapshot.

> A fuller functional and technical architecture walkthrough is available from your Tellumen contact as a
> shareable one-pager.
`,
  },
  {
    slug: 'getting-help', title: 'Getting help & raising a request', category: 'Help',
    summary: 'How to reach the Tellumen team, and what to include.',
    body: `
If something looks wrong, a figure seems off, or you're unsure how something works, raise a request in
**Support** (in the Help section of the sidebar) and talk to the Tellumen team directly.

## Raising a good request
- Pick the **type** — bug, data, report/filing, onboarding, question.
- Give a **one-line subject** and, where you can, the **screen name and the specific asset or figure** (an
  asset id or a location helps us reproduce it fast).
- Set a **priority** if it's blocking a filing.

## What happens next
- The Tellumen team replies on the same thread; you'll see *"Tellumen replied"* in the cockpit's
  *what-needs-you-now* list.
- Reply back to keep the conversation going, or mark it **resolved** when you're happy.
- Every request and reply is recorded in **your** audit log — so support is auditable too.
`,
  },
]
