/**
 * Generate attendance report PDFs (all agents or single agent) for a selected month.
 * Uses jsPDF + jspdf-autotable. Run in browser only.
 */

import { jsPDF } from 'jspdf';
import autoTable from 'jspdf-autotable';
import type { DayAttendance, DaySession } from '@/components/agents/activity-bar';
import { formatTimeFromMinutes, formatDurationMinutes } from '@/components/agents/activity-bar';

const LOGO_URL = '/arabia_logo.png';
const LOGO_MAX_WIDTH = 50;
const LOGO_MAX_HEIGHT = 22;
const MARGIN = 14;
const PAGE_WIDTH_PORTRAIT = 210;
const PAGE_WIDTH_LANDSCAPE = 297;
const CONTENT_WIDTH_PORTRAIT = PAGE_WIDTH_PORTRAIT - MARGIN * 2;
const CONTENT_WIDTH_LANDSCAPE = PAGE_WIDTH_LANDSCAPE - MARGIN * 2;

export type AgentForReport = { id: string; name: string; email: string };

function getDaysInMonth(year: number, month: number): number {
  return new Date(year, month + 1, 0).getDate();
}

function filterByMonth(dayData: DayAttendance[], year: number, month: number): DayAttendance[] {
  return dayData.filter(
    (d) => d.date.getFullYear() === year && d.date.getMonth() === month
  );
}

function filterByDateRange(
  dayData: DayAttendance[],
  from: Date,
  to: Date
): DayAttendance[] {
  const fromT = from.getTime();
  const toT = to.getTime();
  return dayData.filter((d) => {
    const t = d.date.getTime();
    return t >= fromT && t <= toT;
  });
}

function loadLogoDataUrl(): Promise<string> {
  return fetch(LOGO_URL)
    .then((r) => r.blob())
    .then(
      (blob) =>
        new Promise<string>((resolve, reject) => {
          const reader = new FileReader();
          reader.onload = () => resolve(reader.result as string);
          reader.onerror = reject;
          reader.readAsDataURL(blob);
        })
    )
    .catch(() => ''); // no logo if fail
}

function formatSession(s: DaySession): string {
  return `${formatTimeFromMinutes(s.startMinutes)} – ${formatTimeFromMinutes(s.endMinutes)} (${formatDurationMinutes(s.endMinutes - s.startMinutes)})`;
}

function formatDayShort(d: Date): string {
  return d.toLocaleDateString(undefined, { weekday: 'short' });
}

export interface AllAgentsReportOptions {
  agents: AgentForReport[];
  getDayData: (agentId: string) => DayAttendance[];
  year: number;
  month: number;
}

export function buildAllAgentsPdf(options: AllAgentsReportOptions): Promise<void> {
  const { agents, getDayData, year, month } = options;
  const monthLabel = new Date(year, month).toLocaleDateString(undefined, {
    month: 'long',
    year: 'numeric',
  });
  const daysInMonth = getDaysInMonth(year, month);

  return loadLogoDataUrl().then((logoDataUrl) => {
    const doc = new jsPDF({ orientation: 'landscape', unit: 'mm' });
    let y = MARGIN;

    if (logoDataUrl) {
      doc.addImage(logoDataUrl, 'PNG', MARGIN, y, LOGO_MAX_WIDTH, LOGO_MAX_HEIGHT);
      y += LOGO_MAX_HEIGHT + 6;
    }

    doc.setFontSize(18);
    doc.setFont('helvetica', 'bold');
    doc.text('Attendance Report', MARGIN, y);
    y += 8;

    doc.setFontSize(11);
    doc.setFont('helvetica', 'normal');
    doc.text(`All employees — ${monthLabel}`, MARGIN, y);
    y += 10;

    const dayHeaders = ['Agent', 'ID', ...Array.from({ length: daysInMonth }, (_, i) => String(i + 1)), 'Total'];
    const body: (string | number)[][] = [];

    for (const agent of agents) {
      const dayData = filterByMonth(getDayData(agent.id), year, month);
      const byDay = new Map<number, number>();
      let total = 0;
      for (const d of dayData) {
        const dayNum = d.date.getDate();
        byDay.set(dayNum, d.hoursWorked);
        total += d.hoursWorked;
      }
      const row: (string | number)[] = [
        agent.name,
        agent.id,
        ...Array.from({ length: daysInMonth }, (_, i) => {
          const h = byDay.get(i + 1);
          return h != null && h > 0 ? (Math.round(h * 100) / 100) : '—';
        }),
        total > 0 ? (Math.round(total * 100) / 100) + 'h' : '—',
      ];
      body.push(row);
    }

    autoTable(doc, {
      startY: y,
      head: [dayHeaders],
      body,
      margin: { left: MARGIN, right: MARGIN },
      tableWidth: CONTENT_WIDTH_LANDSCAPE,
      styles: { fontSize: 8 },
      headStyles: { fillColor: [66, 66, 66], textColor: 255 },
      columnStyles: {
        0: { cellWidth: 28 },
        1: { cellWidth: 22 },
        [dayHeaders.length - 1]: { cellWidth: 14 },
      },
    });

    doc.save(`attendance-report-${monthLabel.replace(/\s+/g, '-')}-all.pdf`);
  });
}

export interface SingleAgentReportOptions {
  agent: AgentForReport;
  dayData: DayAttendance[];
  periodLabel: string; // e.g. "October 2025" or "1 Oct – 15 Oct 2025"
}

export function buildSingleAgentPdf(options: SingleAgentReportOptions): Promise<void> {
  const { agent, dayData, periodLabel } = options;

  return loadLogoDataUrl().then((logoDataUrl) => {
    const doc = new jsPDF({ orientation: 'portrait', unit: 'mm' });
    let y = MARGIN;

    if (logoDataUrl) {
      doc.addImage(logoDataUrl, 'PNG', MARGIN, y, LOGO_MAX_WIDTH, LOGO_MAX_HEIGHT);
      y += LOGO_MAX_HEIGHT + 6;
    }

    doc.setFontSize(18);
    doc.setFont('helvetica', 'bold');
    doc.text('Attendance Report', MARGIN, y);
    y += 8;

    doc.setFontSize(11);
    doc.setFont('helvetica', 'normal');
    doc.text(agent.name, MARGIN, y);
    y += 6;
    doc.setFontSize(10);
    doc.text(`Agent ID: ${agent.id}`, MARGIN, y);
    y += 5;
    doc.text(`Period: ${periodLabel}`, MARGIN, y);
    y += 10;

    const headers = ['Date', 'Day', 'Total hours', 'Activity (sessions)'];
    const body = dayData.map((d) => {
      const totalM = d.sessions.reduce((s, x) => s + (x.endMinutes - x.startMinutes), 0);
      const activity =
        d.sessions.length === 0
          ? '—'
          : d.sessions.map(formatSession).join('; ');
      return [
        d.date.toLocaleDateString(undefined, { day: '2-digit', month: 'short', year: 'numeric' }),
        formatDayShort(d.date),
        totalM > 0 ? (Math.round((totalM / 60) * 100) / 100) + 'h' : '—',
        activity,
      ];
    });

    if (body.length === 0) {
      doc.setFontSize(10);
      doc.text('No attendance data for this period.', MARGIN, y);
    } else {
      autoTable(doc, {
        startY: y,
        head: [headers],
        body,
        margin: { left: MARGIN, right: MARGIN },
        tableWidth: CONTENT_WIDTH_PORTRAIT,
        styles: { fontSize: 9 },
        headStyles: { fillColor: [66, 66, 66], textColor: 255 },
        columnStyles: {
          0: { cellWidth: 28 },
          1: { cellWidth: 22 },
          2: { cellWidth: 22 },
          3: { cellWidth: 'auto' },
        },
      });
    }

    doc.save(`attendance-report-${agent.name.replace(/\s+/g, '-')}-${periodLabel.replace(/\s+/g, '-').replace(/,/g, '')}.pdf`);
  });
}

export { filterByMonth, filterByDateRange, getDaysInMonth };
