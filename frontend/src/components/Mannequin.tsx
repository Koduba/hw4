/**
 * Illustrated mannequin "wearing" the real product: an SVG figure with the actual
 * catalogue photo (background removed by backend/make_cutouts.py) layered on top.
 * The garment is never redrawn, so the mockup always shows the real item.
 * Skin tone, hair and trousers vary by product so the catalogue shows a varied cast.
 */
const SKIN = ['#f3cfae', '#e0ac85', '#bd8360', '#8d5a3b', '#5c3a26']
const HAIR = ['#1f1a17', '#4a2e1d', '#8a5a2b', '#caa25e', '#2e2a33']
const PANTS = ['#2f4a6d', '#1d1d24', '#b9a985', '#3a3f4b', '#5b6b7f']
const WIDTH: Record<string, number> = {
  'T-Shirts': 214,
  Crewnecks: 224,
  Hoodies: 226,
  'Quarter-Zips': 226,
  'Jackets & Fleece': 230,
  'Long Sleeves': 232,
}

function hash(s: string) {
  let h = 0
  for (const ch of s) h = (h * 31 + ch.charCodeAt(0)) >>> 0
  return h
}

interface Props {
  id: string
  cutoutUrl: string
  aspect?: number | null
  category: string
  name: string
  className?: string
}

export default function Mannequin({ id, cutoutUrl, aspect, category, name, className = '' }: Props) {
  const h = hash(id)
  const skin = SKIN[h % SKIN.length]
  const hair = HAIR[(h >> 3) % HAIR.length]
  const pants = PANTS[(h >> 6) % PANTS.length]
  const hairStyle = (h >> 9) % 4 // 0 bald mannequin, 1 crop, 2 bun, 3 long
  const hooded = category === 'Hoodies'

  // Garment box (viewBox 300×400), sized from the real cutout's aspect ratio.
  const gw = WIDTH[category] ?? 224
  const gh = Math.min(gw / (aspect || 0.85), 300)
  const gx = (300 - gw) / 2
  const gy = hooded ? 64 : 92
  const neckY = hooded ? gy + gh * 0.2 : gy + 8 // where the collar sits
  const headCy = neckY - 34
  const legTop = gy + gh - 14
  const id_ = `mq-${id}`

  const head = (
    <g>
      {hairStyle === 3 && <path d={`M118 ${headCy - 6} q32 -52 64 0 v44 h-64z`} fill={hair} />}
      <rect x="138" y={headCy + 18} width="24" height={neckY - headCy - 6} rx="10" fill={skin} />
      <ellipse cx="150" cy={headCy} rx="25" ry="31" fill={skin} />
      <ellipse cx="141" cy={headCy - 11} rx="7" ry="11" fill="#fff" opacity="0.22" />
      {hairStyle === 1 && <path d={`M125 ${headCy - 4} q25 -46 50 0 q-8 -18 -25 -18 q-17 0 -25 18z`} fill={hair} />}
      {hairStyle === 2 && (
        <>
          <path d={`M125 ${headCy - 2} q25 -44 50 0 q-10 -16 -25 -16 q-15 0 -25 16z`} fill={hair} />
          <circle cx="150" cy={headCy - 38} r="11" fill={hair} />
        </>
      )}
      {hairStyle === 3 && <path d={`M125 ${headCy - 2} q25 -46 50 0 q-10 -18 -25 -18 q-15 0 -25 18z`} fill={hair} />}
    </g>
  )

  return (
    <svg
      className={`mannequin ${className}`}
      viewBox="0 0 300 400"
      role="img"
      aria-label={`${name} shown on an illustrated mannequin (real product photo)`}
    >
      <defs>
        <radialGradient id={`${id_}-bg`} cx="50%" cy="38%" r="70%">
          <stop offset="0%" stopColor="#f4f8ff" />
          <stop offset="100%" stopColor="#d6e6ff" />
        </radialGradient>
      </defs>
      <rect width="300" height="400" fill={`url(#${id_}-bg)`} />
      <ellipse cx="150" cy="388" rx="78" ry="9" fill="#031126" opacity="0.14" />

      {/* legs + sneakers */}
      <path d={`M112 ${legTop} h37 l-4 ${372 - legTop} h-27z`} fill={pants} />
      <path d={`M151 ${legTop} h37 l-6 ${372 - legTop} h-27z`} fill={pants} />
      <path d={`M112 ${legTop} h76 v14 h-76z`} fill="#000" opacity="0.12" />
      <rect x="110" y="370" width="38" height="14" rx="7" fill="#f7f2f5" />
      <rect x="152" y="370" width="38" height="14" rx="7" fill="#f7f2f5" />

      {!hooded && head}
      <image href={cutoutUrl} x={gx} y={gy} width={gw} height={gh} preserveAspectRatio="xMidYMin meet" />
      {hooded && head}
    </svg>
  )
}
