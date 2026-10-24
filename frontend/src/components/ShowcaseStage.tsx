import { useEffect, useMemo, useRef, useState, type CSSProperties } from 'react'
import { Link, matchPath, useLocation } from 'react-router-dom'
import { formatPrice } from '../lib/api'
import type { ProductCard, Showcase } from '../lib/chat'
import { useShowcase } from '../lib/ShowcaseContext'
import ModelSwap from './ModelSwap'

type Sort = 'match' | 'price-asc' | 'price-desc'

/**
 * The on-page product showcase. When the assistant answers a browse question
 * ("what hoodies do you have?") it returns a Showcase, and this section slides
 * in under the nav with those products as animated cards.
 */
export default function ShowcaseStage() {
  const { showcase, compact, searching, expand, close } = useShowcase()
  return (
    <>
      <div className={`scanline ${searching ? 'is-active' : ''}`} aria-hidden="true" />
      {showcase &&
        (compact ? (
          // On a product page reached from a card: keep the picks one tap away
          // without pushing the detail view (image + info) off screen.
          <Dock showcase={showcase} onExpand={expand} onClose={close} />
        ) : (
          // Keyed by id so sort/filter state resets and the cards re-animate for each new result set.
          <Stage key={showcase.id} showcase={showcase} onClose={close} />
        ))}
    </>
  )
}

function Dock({ showcase, onExpand, onClose }: { showcase: Showcase; onExpand: () => void; onClose: () => void }) {
  const { pathname } = useLocation()
  const currentId = matchPath('/products/:productId', pathname)?.params.productId
  const list = showcase.products
  const index = list.findIndex((p) => p.product_id === currentId)
  const prev = index > 0 ? list[index - 1] : null
  const next = index >= 0 && index < list.length - 1 ? list[index + 1] : null
  const activeRef = useRef<HTMLAnchorElement>(null)

  useEffect(() => {
    activeRef.current?.scrollIntoView({ block: 'nearest', inline: 'center', behavior: 'smooth' })
  }, [currentId])

  return (
    <nav className="dock" aria-label={`Your assistant's picks: ${showcase.title}`}>
      <div className="dock__head">
        <p className="dock__title">
          <span className="spark" aria-hidden="true">✦</span> {showcase.title}
          <span className="dock__count">
            {index >= 0 ? `${index + 1} of ${list.length}` : `${list.length} picks`}
          </span>
        </p>
        <div className="dock__actions">
          {prev && (
            <Link to={prev.page_url} className="dock__step" aria-label={`Previous pick: ${prev.name}`}>
              ←
            </Link>
          )}
          {next && (
            <Link to={next.page_url} className="dock__step" aria-label={`Next pick: ${next.name}`}>
              →
            </Link>
          )}
          <button type="button" className="dock__expand" onClick={onExpand}>
            View all picks
          </button>
          <button type="button" className="dock__close" onClick={onClose} aria-label="Close picks">
            ×
          </button>
        </div>
      </div>
      <ul className="dock__strip">
        {list.map((p) => {
          const active = p.product_id === currentId
          return (
            <li key={p.product_id}>
              <Link
                ref={active ? activeRef : undefined}
                to={p.page_url}
                className={`dock__thumb ${active ? 'is-active' : ''} ${p.in_stock ? '' : 'is-out'}`}
                aria-current={active ? 'page' : undefined}
                title={p.name}
              >
                <ModelSwap product={p} />
              </Link>
            </li>
          )
        })}
      </ul>
    </nav>
  )
}

function Stage({ showcase, onClose }: { showcase: Showcase; onClose: () => void }) {
  const [sort, setSort] = useState<Sort>('match')
  const [inStockOnly, setInStockOnly] = useState(false)
  const ref = useRef<HTMLElement>(null)

  useEffect(() => {
    const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    ref.current?.scrollIntoView({ behavior: reduce ? 'auto' : 'smooth', block: 'start' })
    ref.current?.focus({ preventScroll: true })
  }, [])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  const products = useMemo(() => {
    const list = inStockOnly ? showcase.products.filter((p) => p.in_stock) : [...showcase.products]
    if (sort === 'price-asc') list.sort((a, b) => a.price - b.price)
    if (sort === 'price-desc') list.sort((a, b) => b.price - a.price)
    return list
  }, [showcase.products, sort, inStockOnly])

  const prices = showcase.products.map((p) => p.price)
  const low = Math.min(...prices)
  const high = Math.max(...prices)
  const seeAll = showcase.category
    ? `/products?category=${encodeURIComponent(showcase.category)}`
    : `/products${showcase.query ? `?q=${encodeURIComponent(showcase.query)}` : ''}`

  return (
    <section
      ref={ref}
      tabIndex={-1}
      className="showcase"
      aria-labelledby="showcase-title"
    >
      <div className="showcase__glow" aria-hidden="true" />
      <header className="showcase__header">
        <div>
          <p className="showcase__eyebrow">
            <span className="spark" aria-hidden="true">✦</span> Picked by your assistant
          </p>
          <h2 id="showcase-title" className="showcase__title">
            {showcase.title}
          </h2>
          <p className="showcase__meta" aria-live="polite">
            Showing {showcase.products.length}
            {showcase.total_matches > showcase.products.length && ` of ${showcase.total_matches}`}{' '}
            {showcase.products.length === 1 ? 'match' : 'matches'}
            {prices.length > 0 && (
              <> · {low === high ? formatPrice(low) : `${formatPrice(low)} – ${formatPrice(high)}`}</>
            )}
            {showcase.query && <> · “{showcase.query}”</>}
          </p>
        </div>
        <button type="button" className="showcase__close" onClick={onClose} aria-label="Close picks">
          ×
        </button>
      </header>

      <div className="showcase__controls">
        <div className="segmented" role="group" aria-label="Sort picks">
          {(
            [
              ['match', 'Best match'],
              ['price-asc', 'Price ↑'],
              ['price-desc', 'Price ↓'],
            ] as const
          ).map(([value, label]) => (
            <button
              key={value}
              type="button"
              aria-pressed={sort === value}
              className={sort === value ? 'is-active' : ''}
              onClick={() => setSort(value)}
            >
              {label}
            </button>
          ))}
        </div>
        <label className="switch">
          <input
            type="checkbox"
            checked={inStockOnly}
            onChange={(e) => setInStockOnly(e.target.checked)}
          />
          <span className="switch__track" aria-hidden="true" />
          In stock only
        </label>
        <Link to={seeAll} className="showcase__all">
          See all on Products →
        </Link>
      </div>

      {products.length === 0 ? (
        <p className="notice">Nothing in stock in this set. Turn off “In stock only” to see everything.</p>
      ) : (
        <ul className="showcase__grid">
          {products.map((p, i) => (
            <li key={p.product_id} style={{ '--i': i } as CSSProperties}>
              <ShowcaseCard product={p} rank={sort === 'match' ? i + 1 : undefined} />
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}

function ShowcaseCard({ product: p, rank }: { product: ProductCard; rank?: number }) {
  const tone = !p.in_stock ? 'out' : p.stock_label === 'In stock' ? 'ok' : 'low'
  return (
    <Link to={p.page_url} className={`sc-card ${!p.in_stock ? 'is-out' : ''}`}>
      <div className="sc-card__media">
        <img src={p.image_url} alt={p.name} loading="lazy" />
        {rank !== undefined && rank <= 3 && (
          <span className="sc-card__rank" aria-label={`Top pick ${rank}`}>
            #{rank}
          </span>
        )}
        <span className={`sc-card__stock sc-card__stock--${tone}`}>{p.stock_label}</span>
      </div>
      <div className="sc-card__body">
        <p className="sc-card__category">{p.category}</p>
        <h3 className="sc-card__name">{p.name}</h3>
        {p.note && (
          <p className="sc-card__note">
            <span aria-hidden="true">✦</span> {p.note}
          </p>
        )}
        <p className="sc-card__info">{p.short_info}</p>
        <div className="sc-card__footer">
          <span className="sc-card__price">{formatPrice(p.price)}</span>
          {p.sizes_in_stock.length > 0 && (
            <span className="sc-card__sizes" aria-label={`Sizes in stock: ${p.sizes_in_stock.join(', ')}`}>
              {p.sizes_in_stock.map((s) => (
                <span key={s}>{s}</span>
              ))}
            </span>
          )}
        </div>
      </div>
    </Link>
  )
}
