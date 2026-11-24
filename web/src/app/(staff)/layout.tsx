// Task C-01. Staff shell: left nav per role (Admin vs Payroll Manager), company name, signed-in user, 'Sandbox. No real money moves.' footer. Desktop first; see docs/design/screens/Admin-Home.dc.html.
// Guard: useMe(); if the user doesn't belong here, router.replace(homePathFor(me)).
export default function Layout({ children }: { children: React.ReactNode }) {
  return <div className="min-h-dvh bg-paper text-ink">{children}</div>;
}
