import { useId } from "react";

/** The JettsTUI prism mark: four facets, matching the desktop app icon. */
export function PrismMark({ className }: { className?: string }) {
  // useId can contain ":" / "«»", which break url(#…) references.
  const id = `prism${useId().replace(/[^a-zA-Z0-9_-]/g, "")}`;
  const tl = `${id}-tl`;
  const br = `${id}-br`;

  return (
    <svg aria-hidden className={className} viewBox="0 0 32 32">
      <defs>
        <linearGradient id={tl} x1="0" x2="1" y1="0" y2="1">
          <stop offset="0" stopColor="#B9AEFF" />
          <stop offset="1" stopColor="#7357FF" />
        </linearGradient>
        <linearGradient id={br} x1="1" x2="0" y1="0" y2="1">
          <stop offset="0" stopColor="#5EEAD4" />
          <stop offset="1" stopColor="#3B82F6" />
        </linearGradient>
      </defs>
      <path d="M16 2 16 16 2.5 16Z" fill={`url(#${tl})`} />
      <path d="M16 2 29.5 16 16 16Z" fill="#E2DCFF" />
      <path d="M2.5 16 16 16 16 30Z" fill="#4A30D6" />
      <path d="M16 16 29.5 16 16 30Z" fill={`url(#${br})`} />
      <path
        d="M16 2 29.5 16 16 30 2.5 16Z"
        fill="none"
        stroke="#FFFFFF"
        strokeLinejoin="round"
        strokeOpacity="0.2"
      />
    </svg>
  );
}
