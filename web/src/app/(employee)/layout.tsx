// Task D-02. Employee shell: phone-first, bottom tab bar (Home, Hours, Paystubs, Account); see docs/design/screens/Emp-Home.dc.html. Former employees get no tab bar.
// Guard: useMe(); if the user doesn't belong here, router.replace(homePathFor(me)).
export default function Layout({ children }: { children: React.ReactNode }) {
  return <div className="min-h-dvh bg-paper text-ink">{children}</div>;
}
