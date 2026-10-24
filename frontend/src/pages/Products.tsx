import { useEffect, useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import ModelSwap from '../components/ModelSwap'
import { fetchProducts, formatPrice, LOW_STOCK, stockLabel, type Product } from '../lib/api'

const ALL = 'All'
const SIZES = ['XS', 'S', 'M', 'L', 'XL', 'XXL']
const SORTS = [
  ['featured', 'Featured'],
  ['price-asc', 'Price: low to high'],
  ['price-desc', 'Price: high to low'],
  ['stock', 'Most in stock'],
  ['name', 'Name A–Z'],
] as const
type SortKey = (typeof SORTS)[number][0]

export default function Products() {
  const [products, setProducts] = useState<Product[] | null>(null)
  const [error, setError] = useState('')
  const [params, setParams] = useSearchParams()
  const query = params.get('q') ?? ''
  const category = params.get('category') ?? ALL
  const size = params.get('size') ?? ''
  const sort = (params.get('sort') ?? 'featured') as SortKey

  useEffect(() => {
    fetchProducts()
      .then(setProducts)
      .catch((e: Error) => setError(e.message))
  }, [])

  const categories = useMemo(() => {
    const counts = new Map<string, number>()
    products?.forEach((p) => counts.set(p.category, (counts.get(p.category) ?? 0) + 1))
    return [...counts.entries()].sort((a, b) => b[1] - a[1])
  }, [products])

  const visible = useMemo(() => {
    const q = query.trim().toLowerCase()
    const list = (products ?? []).filter((p) => {
      if (category !== ALL && p.category !== category) return false
      if (size && !p.inventory.some((s) => s.size === size && s.quantity > 0)) return false
      if (!q) return true
      return [p.name, p.description, p.garment_type, ...p.colors, ...p.search_tags]
        .join(' ')
        .toLowerCase()
        .includes(q)
    })
    const qty = (p: Product) => (size ? (p.inventory.find((s) => s.size === size)?.quantity ?? 0) : p.total_stock)
    if (sort === 'price-asc') list.sort((a, b) => a.price - b.price || a.name.localeCompare(b.name))
    if (sort === 'price-desc') list.sort((a, b) => b.price - a.price || a.name.localeCompare(b.name))
    if (sort === 'stock') list.sort((a, b) => qty(b) - qty(a))
    if (sort === 'name') list.sort((a, b) => a.name.localeCompare(b.name))
    return list
  }, [products, query, category, size, sort])

  const filtersOn = !!query || category !== ALL || !!size || sort !== 'featured'


  function setParam(key: string, value: string, empty: string) {
    const next = new URLSearchParams(params)
    if (value === empty) next.delete(key)
    else next.set(key, value)
    setParams(next, { replace: true })
  }

  return (
    <>
      <section className="hero hero--compact">
        <p className="eyebrow">Products</p>
        <h1>
          The full <span className="accent">collection</span>
        </h1>
        <p className="lead">
          Hoodies, crewnecks, quarter-zips, tees and jackets in sizes XS to
          XXL.
        </p>
      </section>

      <section className="toolbar" aria-label="Filter products">
        <label htmlFor="product-search" className="visually-hidden">
          Search products
        </label>
        <input
          id="product-search"
          type="search"
          placeholder="Search by name, colour, college, sport…"
          value={query}
          onChange={(e) => setParam('q', e.target.value, '')}
        />
        <div className="chips" role="group" aria-label="Category">
          {[[ALL, products?.length ?? 0] as const, ...categories].map(([c, n]) => (
            <button
              key={c}
              type="button"
              className={`chip ${category === c ? 'is-active' : ''}`}
              aria-pressed={category === c}
              onClick={() => setParam('category', c, ALL)}
            >
              {c} <span className="chip__count">{n}</span>
            </button>
          ))}
        </div>
      </section>

      <section className="refine" aria-label="Sort and size">
        <div className="refine__sizes" role="group" aria-label="In stock in size">
          <span className="refine__label">In stock in</span>
          {['', ...SIZES].map((s) => (
            <button
              key={s || 'any'}
              type="button"
              className={`size-chip ${size === s ? 'is-active' : ''}`}
              aria-pressed={size === s}
              onClick={() => setParam('size', s, '')}
            >
              {s || 'Any size'}
            </button>
          ))}
        </div>
        <label className="refine__sort">
          <span className="refine__label">Sort</span>
          <select value={sort} onChange={(e) => setParam('sort', e.target.value, 'featured')}>
            {SORTS.map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </label>
        {filtersOn && (
          <button type="button" className="refine__clear" onClick={() => setParams({}, { replace: true })}>
            Clear all
          </button>
        )}
      </section>

      {error && (
        <p className="form-error notice--error" role="alert">
          {error}
        </p>
      )}

      {!products && !error && (
        <div className="product-grid" aria-busy="true" aria-label="Loading products">
          {Array.from({ length: 8 }, (_, i) => (
            <div key={i} className="product-card skeleton" />
          ))}
        </div>
      )}

      {products && (
        <>
          <p className="muted result-count" aria-live="polite">
            {visible.length} {visible.length === 1 ? 'product' : 'products'}
            {size && ` in stock in ${size}`}
          </p>
          {visible.length === 0 ? (
            <p className="notice">
              No products match{size && ` in ${size}`}. Try a different size or search, or{' '}
              <button type="button" className="link-button" onClick={() => setParams({}, { replace: true })}>
                clear all filters
              </button>
              .
            </p>
          ) : (
            <ul className="product-grid">
              {visible.map((p) => (
                <li key={p.product_id}>
                  <ProductCard product={p} size={size} />
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </>
  )
}

function ProductCard({ product: p, size }: { product: Product; size: string }) {
  const sizeQty = size ? (p.inventory.find((s) => s.size === size)?.quantity ?? 0) : null
  const stock =
    sizeQty === null
      ? stockLabel(p)
      : { text: sizeQty <= LOW_STOCK ? `Only ${sizeQty} left in ${size}` : `${sizeQty} in stock in ${size}`, tone: sizeQty <= LOW_STOCK ? ('low' as const) : ('ok' as const) }
  return (
    <Link to={`/products/${p.product_id}`} className="product-card">
      <div className="product-card__image">
        <ModelSwap product={p} />
      </div>
      <div className="product-card__body">
        <p className="product-card__category">{p.category}</p>
        <h2 className="product-card__name">{p.name}</h2>
        {p.colors.length > 0 && (
          <p className="product-card__colors muted">{p.colors.join(' · ')}</p>
        )}
        <div className="product-card__footer">
          <span className="price">{formatPrice(p.price)}</span>
          <span className={`stock stock--${stock.tone}`}>{stock.text}</span>
        </div>
      </div>
    </Link>
  )
}
