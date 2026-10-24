/** Campus Customs shield crest (brand mark used in the nav, footer and chat avatar). */
export default function Crest({ size = 34, className = '' }: { size?: number; className?: string }) {
  return (
    <svg className={`crest ${className}`} width={size} height={size} viewBox="0 0 64 64" aria-hidden="true">
      <path d="M8 6h48v30c0 12-10 20-24 24C18 56 8 48 8 36z" fill="var(--yale)" stroke="#fff" strokeWidth="2.5" />
      <path
        d="M13 11h38v25c0 9-8 15-19 18-11-3-19-9-19-18z"
        fill="none"
        stroke="var(--accent)"
        strokeWidth="2"
        strokeDasharray="3 3"
      />
      <text x="32" y="40" textAnchor="middle" fontFamily="Graduate, Georgia, serif" fontSize="20" fill="#fff">
        CC
      </text>
    </svg>
  )
}
