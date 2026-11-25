"use client";
/** Gallery of every UI primitive (W-01). Dev-only reference at /dev/ui. */
import { useEffect, useState } from "react";

import { Countdown } from "@/components/countdown";
import {
  Banner,
  Button,
  Card,
  ConfirmDialog,
  DateField,
  EmptyState,
  ErrorState,
  HoursField,
  LoadingState,
  Money,
  MoneyField,
  PageHeader,
  RadioGroup,
  RunStateTracker,
  Select,
  StatusPill,
  Table,
  TextField,
} from "@/components/ui";
import type { RunState } from "@/components/ui";

const STATES: RunState[] = ["draft", "submitted", "approved", "processing", "paid", "failed", "cancelled"];
const HOUR = 3_600_000;

type Row = { name: string; hours: string; gross: number };
const ROWS: Row[] = [
  { name: "Maya Okafor", hours: "80.0", gross: 196000 },
  { name: "Daniel Reyes", hours: "72.5", gross: 147098 },
];

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="flex flex-col gap-4">
      <h2 className="text-heading m-0">{title}</h2>
      {children}
    </section>
  );
}

export default function UiGalleryPage() {
  const [name, setName] = useState("");
  const [role, setRole] = useState("");
  const [pay, setPay] = useState("");
  const [payCents, setPayCents] = useState<number | null>(null);
  const [hours, setHours] = useState("");
  const [minutes, setMinutes] = useState<number | null>(null);
  const [date, setDate] = useState("");
  const [freq, setFreq] = useState("biweekly");
  const [open, setOpen] = useState(false);
  const [times, setTimes] = useState<Record<"server" | "day2" | "today" | "urgent" | "late", string> | null>(null);
  useEffect(() => {
    const t = setTimeout(() => {
      const now = Date.now();
      setTimes({
        server: new Date(now).toISOString(),
        day2: new Date(now + 40 * HOUR).toISOString(),
        today: new Date(now + 10 * HOUR).toISOString(),
        urgent: new Date(now + 1 * HOUR).toISOString(),
        late: new Date(now - 1 * HOUR).toISOString(),
      });
    }, 0);
    return () => clearTimeout(t);
  }, []);

  return (
    <main className="mx-auto flex max-w-4xl flex-col gap-12 p-8">
      <PageHeader eyebrow="Dev" title="UI kit" lead="Every shared primitive, in one place." />

      <Section title="Buttons, pills, cards, money">
        <div className="flex flex-wrap gap-3">
          <Button variant="primary">Primary</Button>
          <Button>Secondary</Button>
          <Button variant="quiet">Quiet</Button>
          <Button disabled>Disabled</Button>
        </div>
        <div className="flex gap-2">
          <StatusPill>Step</StatusPill>
          <StatusPill current>Current</StatusPill>
        </div>
        <Card eyebrow="Eyebrow" title="Card title">
          Gross pay <Money cents={196000} />
        </Card>
      </Section>

      <Section title="Fields">
        <div className="grid gap-6 sm:grid-cols-2">
          <TextField label="Legal name" hint="As it appears on the EIN letter." value={name} onChange={(e) => setName(e.target.value)} />
          <TextField label="With an error" error="Enter the legal name." defaultValue="" />
          <Select
            label="Role"
            placeholder="Choose a role"
            value={role}
            onChange={(e) => setRole(e.target.value)}
            options={[
              { value: "admin", label: "Admin" },
              { value: "pm", label: "Payroll Manager" },
            ]}
          />
          <DateField label="Start date" hint="First day of work." value={date} onChange={setDate} />
          <MoneyField
            label="Hourly rate"
            hint={payCents === null ? "Dollars, like 24.50." : `Stored as ${payCents} cents.`}
            value={pay}
            onChange={(v, c) => {
              setPay(v);
              setPayCents(c);
            }}
          />
          <HoursField
            label="Hours worked"
            hint={minutes === null ? "Decimal or h:mm." : `Stored as ${minutes} minutes.`}
            value={hours}
            onChange={(v, m) => {
              setHours(v);
              setMinutes(m);
            }}
          />
        </div>
        <RadioGroup
          legend="Pay schedule"
          name="freq"
          value={freq}
          onChange={setFreq}
          options={[{ value: "biweekly", label: "Biweekly", hint: "Every other Friday." }]}
        />
      </Section>

      <Section title="Table">
        <Table
          caption="Run items"
          rows={ROWS}
          rowKey={(r) => r.name}
          columns={[
            { key: "name", header: "Employee", cell: (r) => r.name },
            { key: "hours", header: "Hours", numeric: true, muted: true, cell: (r) => r.hours },
            { key: "gross", header: "Gross", numeric: true, cell: (r) => <Money cents={r.gross} /> },
          ]}
          total={{ name: "Total", gross: <Money cents={343098} /> }}
        />
      </Section>

      <Section title="Banners">
        <Banner tone="info" title="Info">Plain information.</Banner>
        <Banner tone="preview" title="Preview">Nothing is final until you approve.</Banner>
        <Banner tone="warning" title="Warning">Two timesheets are still open.</Banner>
        <Banner tone="alert" title="Alert">The payment failed.</Banner>
      </Section>

      <Section title="States">
        <EmptyState title="No runs yet" action={<Button>Start a run</Button>}>
          Your first run appears here.
        </EmptyState>
        <LoadingState />
        <ErrorState
          error={{ detail: { code: "past_cutoff", message: "The cutoff has passed." } }}
          onRetry={() => undefined}
        />
      </Section>

      <Section title="Dialog">
        <div>
          <Button onClick={() => setOpen(true)}>Open dialog</Button>
        </div>
        <ConfirmDialog
          open={open}
          title="Approve this run?"
          confirmLabel="Approve"
          onConfirm={() => setOpen(false)}
          onCancel={() => setOpen(false)}
        >
          An approved run locks. Nobody can edit it, not even you.
        </ConfirmDialog>
      </Section>

      <Section title="Run state tracker">
        {STATES.map((s) => (
          <div key={s} className="flex flex-col gap-1">
            <p className="text-note m-0">{s}</p>
            <RunStateTracker state={s} />
          </div>
        ))}
      </Section>

      <Section title="Countdown">
        {times ? (
          <div className="grid gap-4 sm:grid-cols-2">
            <Countdown cutoffAt={times.day2} serverTime={times.server} />
            <Countdown cutoffAt={times.today} serverTime={times.server} />
            <Countdown cutoffAt={times.urgent} serverTime={times.server} />
            <Countdown cutoffAt={times.late} serverTime={times.server} />
          </div>
        ) : (
          <LoadingState />
        )}
      </Section>
    </main>
  );
}
