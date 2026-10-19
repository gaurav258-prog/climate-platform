// The control center's tabs, grouped by purpose and ordered as an organisation is set up and run: where you stand ·
// who, and what they may do · the approvals and audit those settings drive · structure, appetite and method ·
// connections. Each tab has a stable key; a link into the page names it as /admin?tab=<key> (the readiness checks,
// the method-gap notes, Loss and Portfolio do). Kept free of imports so a node test reads it (web/tests/adminTabs.test.ts).

export type AdminTab = { key: string; label: string; perm: string; aliases?: string[] }

export const TAB_GROUPS: AdminTab[][] = [
  [{ key: 'overview', label: 'Overview', perm: 'admin.users.manage' }],
  [{ key: 'team', label: 'People', perm: 'admin.users.manage', aliases: ['users'] },
   { key: 'roles', label: 'Roles', perm: 'admin.roles.manage' },
   { key: 'matrix', label: 'Approval matrix', perm: 'admin.approval_policy.manage' }],
  [{ key: 'approvals', label: 'Approvals', perm: 'approvals.view' },
   { key: 'audit', label: 'Audit', perm: 'admin.audit.view' }],
  [{ key: 'entities', label: 'Entities', perm: 'admin.users.manage' },
   { key: 'appetite', label: 'Risk appetite', perm: 'admin.approval_policy.manage', aliases: ['kri appetite'] },
   { key: 'methodology', label: 'Methodology', perm: 'admin.roles.manage' }],
  [{ key: 'integrations', label: 'Integrations', perm: 'admin.users.manage' }],
]

export const ALL_TABS = TAB_GROUPS.flat()

// The tab a link names — by its key, its label or an older name, in any case; null when it names none.
export function resolveTab(name: string | null | undefined): string | null {
  const n = (name ?? '').trim().toLowerCase()
  if (!n) return null
  return ALL_TABS.find(t => t.key === n || t.label.toLowerCase() === n || (t.aliases ?? []).includes(n))?.key ?? null
}

// The groups a person sees: only the tabs their permissions open, empty groups dropped.
export const visibleGroups = (perms: string[]) =>
  TAB_GROUPS.map(g => g.filter(t => perms.includes(t.perm))).filter(g => g.length)
