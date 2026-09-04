// Single source of human, external-facing names for machine action / request / event codes.
//
// Codes like "filing.approve" or "asset.valuation.override" are how the backend records what happened; they must
// never reach a user as-is. Every surface that shows one — the approvals queue, the audit trail, platform
// activity, admin events, filing history, decisions — calls actionLabel(), so the wording is consistent and
// professional everywhere and a new code degrades gracefully instead of leaking a raw dotted string.

const LABELS: Record<string, string> = {
  // ---- approval request types (maker-checker queue) ----
  'supply.site.update': 'Edit site', 'supply.site.delete': 'Delete site',
  'supply.plot.update': 'Edit plot', 'supply.plot.delete': 'Delete plot',
  'submission.create': 'Create submission', 'submission.release': 'Release submission',
  'submissions.release': 'Release submission', 'report.publish': 'Publish report', 'reports.publish': 'Publish report',
  'config.reporting_settings': 'Change reporting basis', 'config.calc_settings': 'Change calculation settings',
  'supply.eudr.determine': 'Run EUDR determination', 'eudr.determine': 'Run EUDR determination',
  'filing.approve': 'Approve disclosure', 'filing.accept': 'Accept disclosure', 'filing.attest': 'Attest disclosure',
  'filing.submit': 'Submit disclosure', 'filing.submit_for_review': 'Submit disclosure for review',
  'filing.release': 'Release disclosure', 'filing.refresh': 'Refresh disclosure', 'filing.restate': 'Restate disclosure',
  'filing.generate': 'Generate disclosure', 'filing.frozen': 'Freeze disclosure',
  'filing.cell_override': 'Override a reported figure', 'filing.cell_override.propose': 'Propose a figure override',
  'pricing.approve': 'Approve valuation override', 'pricing.view': 'View pricing',
  'entity.create': 'Add counterparty', 'entity.update': 'Edit counterparty', 'entity.delete': 'Delete counterparty',
  'organization.update': 'Update organisation', 'user.update': 'Update user',
  'role_permission.update': 'Change role permissions', 'approval_policy.update': 'Change approval policy',
  'kri_appetite.update': 'Change risk appetite', 'decision_playbook.update': 'Edit decision playbook',

  // ---- audit-trail actions ----
  'approval.create': 'Requested approval', 'approval.request': 'Requested approval',
  'approval.assign': 'Routed approval', 'approval.decide': 'Decided approval',
  'asset.valuation.override': 'Overrode valuation', 'asset.valuation.override_cleared': 'Cleared valuation override',
  'holding.valuation.override': 'Overrode valuation', 'holding.valuation.override_cleared': 'Cleared valuation override',
  'property.valuation.override': 'Overrode valuation', 'property.valuation.override_cleared': 'Cleared valuation override',
  'commodity.cogs_at_risk.override': 'Overrode COGS-at-risk', 'commodity.cogs_at_risk.override_cleared': 'Cleared COGS-at-risk override',
  'assets.upload': 'Uploaded book', 'assets.attributes.upload': 'Uploaded loan attributes',
  'holdings.upload': 'Uploaded holdings', 'policies.upload': 'Uploaded policies',
  'properties.upload': 'Uploaded properties', 'plots.upload': 'Uploaded plots', 'plots.add': 'Added plots',
  'ingest.bank.assets': 'Ingested book', 'data_feed.refresh': 'Refreshed data feed',
  'reports.snapshot.create': 'Froze a report', 'reports.assurance_pack.export': 'Exported assurance pack',
  'eudr.dds.assemble': 'Assembled DDS', 'eudr.dds.submit': 'Submitted DDS', 'eudr.dds.filed': 'Filed DDS',
  'contract.uploaded': 'Uploaded contract', 'contract.downloaded': 'Downloaded contract', 'contract.removed': 'Removed contract',
  'esign.requested': 'Requested e-signature', 'esign.completed': 'Completed e-signature',
  'billing.plan_changed': 'Changed plan', 'impersonation.start': 'Started operator session',
  'sso.config_updated': 'Updated SSO', 'sso.login': 'Signed in via SSO', 'sso.scim_token_issued': 'Issued SCIM token',
  'account.mfa_enrolled': 'Enrolled MFA', 'account.mfa_reset': 'Reset MFA',
  'account.password_set': 'Set password', 'account.password_reset': 'Reset password',
  'account.sessions_revoked': 'Revoked sessions',
  'ingest.token.create': 'Created ingest token', 'ingest.token.revoke': 'Revoked ingest token',
  'source_system.register': 'Registered source system', 'drill_through.resolve': 'Resolved drill-through',
  'intake.created': 'Created intake', 'policy.trigger_config.set': 'Set parametric trigger',
  login: 'Signed in', logout: 'Signed out',
}

// Turn any unlisted code into a readable phrase — "asset.valuation.override" → "Asset · valuation override" —
// so nothing ever renders as a raw machine code.
export function actionLabel(code: string | null | undefined): string {
  if (!code) return '—'
  if (LABELS[code]) return LABELS[code]
  const cap = (s: string) => (s ? s[0].toUpperCase() + s.slice(1) : s)
  const [domain, ...rest] = code.split('.')
  const tail = rest.join(' ').replace(/_/g, ' ')
  return tail ? `${cap(domain.replace(/_/g, ' '))} · ${tail}` : cap(domain.replace(/_/g, ' ')) || 'Activity'
}
