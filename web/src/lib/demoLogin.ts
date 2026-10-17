// The demo tenants' sign-in passwords (the same values scripts/seed_demo_population.py seeds). Loaded only by a
// development server or a build marked as a demo (DEMO_LOGIN in pages/Login.tsx) — never part of a production bundle
// (E185; guard: web/tests/demoLogin.test.ts).
export const DEMO_ROLE_PASSWORDS: Record<string, string> = { admin: 'Demo!admin1', analyst: 'Demo!analyst1', approver: 'Demo!approve1' }
