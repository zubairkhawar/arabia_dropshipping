/** Grouped IANA zones for admin timezone dropdown. */

export type TimezoneOption = { id: string; label: string };

export type TimezoneGroup = { region: string; zones: TimezoneOption[] };

export const TIMEZONE_GROUPS: TimezoneGroup[] = [
  {
    region: 'UTC',
    zones: [{ id: 'UTC', label: 'UTC' }],
  },
  {
    region: 'Americas',
    zones: [
      { id: 'America/New_York', label: 'America/New_York (EST/EDT)' },
      { id: 'America/Chicago', label: 'America/Chicago (CST/CDT)' },
      { id: 'America/Denver', label: 'America/Denver (MST/MDT)' },
      { id: 'America/Los_Angeles', label: 'America/Los_Angeles (PST/PDT)' },
      { id: 'America/Phoenix', label: 'America/Phoenix (MST)' },
      { id: 'America/Toronto', label: 'America/Toronto (EST/EDT)' },
      { id: 'America/Vancouver', label: 'America/Vancouver (PST/PDT)' },
      { id: 'America/Mexico_City', label: 'America/Mexico_City (CST)' },
      { id: 'America/Sao_Paulo', label: 'America/Sao_Paulo (BRT)' },
      { id: 'America/Argentina/Buenos_Aires', label: 'America/Argentina/Buenos_Aires (ART)' },
    ],
  },
  {
    region: 'Europe',
    zones: [
      { id: 'Europe/London', label: 'Europe/London (GMT/BST)' },
      { id: 'Europe/Paris', label: 'Europe/Paris (CET/CEST)' },
      { id: 'Europe/Berlin', label: 'Europe/Berlin (CET/CEST)' },
      { id: 'Europe/Madrid', label: 'Europe/Madrid (CET/CEST)' },
      { id: 'Europe/Rome', label: 'Europe/Rome (CET/CEST)' },
      { id: 'Europe/Amsterdam', label: 'Europe/Amsterdam (CET/CEST)' },
      { id: 'Europe/Zurich', label: 'Europe/Zurich (CET/CEST)' },
      { id: 'Europe/Stockholm', label: 'Europe/Stockholm (CET/CEST)' },
      { id: 'Europe/Warsaw', label: 'Europe/Warsaw (CET/CEST)' },
      { id: 'Europe/Athens', label: 'Europe/Athens (EET/EEST)' },
      { id: 'Europe/Istanbul', label: 'Europe/Istanbul (TRT)' },
      { id: 'Europe/Moscow', label: 'Europe/Moscow (MSK)' },
    ],
  },
  {
    region: 'Middle East & Africa',
    zones: [
      { id: 'Asia/Dubai', label: 'Asia/Dubai (GST)' },
      { id: 'Asia/Riyadh', label: 'Asia/Riyadh (AST)' },
      { id: 'Asia/Baghdad', label: 'Asia/Baghdad (AST)' },
      { id: 'Asia/Tehran', label: 'Asia/Tehran (IRST)' },
      { id: 'Asia/Jerusalem', label: 'Asia/Jerusalem (IST/IDT)' },
      { id: 'Africa/Cairo', label: 'Africa/Cairo (EET)' },
      { id: 'Africa/Johannesburg', label: 'Africa/Johannesburg (SAST)' },
      { id: 'Africa/Lagos', label: 'Africa/Lagos (WAT)' },
    ],
  },
  {
    region: 'Asia',
    zones: [
      { id: 'Asia/Karachi', label: 'Asia/Karachi (PKT)' },
      { id: 'Asia/Kolkata', label: 'Asia/Kolkata (IST)' },
      { id: 'Asia/Dhaka', label: 'Asia/Dhaka (BST)' },
      { id: 'Asia/Bangkok', label: 'Asia/Bangkok (ICT)' },
      { id: 'Asia/Singapore', label: 'Asia/Singapore (SGT)' },
      { id: 'Asia/Hong_Kong', label: 'Asia/Hong_Kong (HKT)' },
      { id: 'Asia/Shanghai', label: 'Asia/Shanghai (CST)' },
      { id: 'Asia/Tokyo', label: 'Asia/Tokyo (JST)' },
      { id: 'Asia/Seoul', label: 'Asia/Seoul (KST)' },
      { id: 'Asia/Manila', label: 'Asia/Manila (PHT)' },
      { id: 'Asia/Jakarta', label: 'Asia/Jakarta (WIB)' },
    ],
  },
  {
    region: 'Pacific & Oceania',
    zones: [
      { id: 'Australia/Sydney', label: 'Australia/Sydney (AEST/AEDT)' },
      { id: 'Australia/Melbourne', label: 'Australia/Melbourne (AEST/AEDT)' },
      { id: 'Australia/Perth', label: 'Australia/Perth (AWST)' },
      { id: 'Pacific/Auckland', label: 'Pacific/Auckland (NZST/NZDT)' },
    ],
  },
];

export function findTimezoneLabel(id: string): string | undefined {
  for (const g of TIMEZONE_GROUPS) {
    const z = g.zones.find((x) => x.id === id);
    if (z) return z.label;
  }
  return undefined;
}
