'use client';

interface IconProps {
  className?: string;
}

export function InTransitIcon({ className = 'h-8 w-8' }: IconProps) {
  return (
    <img
      src="data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIyNCIgaGVpZ2h0PSIyNCIgdmlld0JveD0iMCAwIDI0IDI0IiBmaWxsPSJub25lIiBzdHJva2U9IiNFRjFEMUQiIHN0cm9rZS13aWR0aD0iMiIgc3Ryb2tlLWxpbmVjYXA9InJvdW5kIiBzdHJva2UtbGluZWpvaW49InJvdW5kIiBjbGFzcz0ibHVjaWRlIGx1Y2lkZS10cnVjay1pY29uIGx1Y2lkZS10cnVjayI+PHBhdGggZD0iTTE0IDE4VjZhMiAyIDAgMCAwLTItMkg0YTIgMiAwIDAgMC0yIDJ2MTFhMSAxIDAgMCAwIDEgMWgyIi8+PHBhdGggZD0iTTE1IDE4SDkiLz48cGF0aCBkPSJNMTkgMThoMmExIDEgMCAwIDAgMS0xdi0zLjY1YTEgMSAwIDAgMC0uMjItLjYyNGwtMy40OC00LjM1QTEgMSAwIDAgMCAxNy41MiA4SDE0Ii8+PGNpcmNsZSBjeD0iMTciIGN5PSIxOCIgcj0iMiIvPjxjaXJjbGUgY3g9IjciIGN5PSIxOCIgcj0iMiIvPjwvc3ZnPg=="
      alt="In transit"
      className={className}
    />
  );
}

export function TotalOrdersIcon({ className = 'h-8 w-8' }: IconProps) {
  return (
    <img
      src="data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIyNCIgaGVpZ2h0PSIyNCIgdmlld0JveD0iMCAwIDI0IDI0IiBmaWxsPSJub25lIiBzdHJva2U9IiNFRjFEMUQiIHN0cm9rZS13aWR0aD0iMiIgc3Ryb2tlLWxpbmVjYXA9InJvdW5kIiBzdHJva2UtbGluZWpvaW49InJvdW5kIiBjbGFzcz0ibHVjaWRlIGx1Y2lkZS1wYWNrYWdlLWljb24gbHVjaWRlLXBhY2thZ2UiPjxwYXRoIGQ9Ik0xMSAyMS43M2EyIDIgMCAwIDAgMiAwbDctNEEyIDIgMCAwIDAgMjEgMTZWOGEyIDIgMCAwIDAtMS0xLjczbC03LTRhMiAyIDAgMCAwLTIgMGwtNyA0QTIgMiAwIDAgMCAzIDh2OGEyIDIgMCAwIDAgMSAxLjczeiIvPjxwYXRoIGQ9Ik0xMiAyMlYxMiIvPjxwb2x5bGluZSBwb2ludHM9IjMuMjkgNyAxMiAxMiAyMC43MSA3Ii8+PHBhdGggZD0ibTcuNSA0LjI3IDkgNS4xNSIvPjwvc3ZnPg=="
      alt="Total orders"
      className={className}
    />
  );
}

