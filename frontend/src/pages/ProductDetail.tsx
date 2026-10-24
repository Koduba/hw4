import { useEffect, useState, type MouseEvent } from 'react'
import { Link, useParams } from 'react-router-dom'
import {
  fetchProduct,
  formatPrice,
  LOW_STOCK,
  NotFoundError,
  stockLabel,
  type Product,
} from '../lib/api'
import { askAssistant } from '../lib/assistantBus'

/** Moves the zoom origin to the cursor, so hovering inspects that part of the garment. */
function zoomTo(e: MouseEvent<HTMLDivElement>) {
  const r = e.currentTarget.getBoundingClientRect()
  e.currentTarget.style.setProperty('--zx', `${((e.clientX - r.left) / r.width) * 100}%`)
  e.currentTarget.style.setProperty('--zy', `${((e.clientY - r.top) / r.height) * 100}%`)
}

/** Product photo + (when available) the AI on-model photo, with a toggle. */
function Gallery({ product }: { product: Product }) {
  const [view, setView] = useState<'model' | 'product'>(product.model_image_url ? 'model' : 'product')
  const onModel = view === 'model' && !!product.model_image_url
  return (
    <div className="gallery">
      <div className={`product-detail__image zoom ${onModel ? 'is-model' : ''}`} onMouseMove={zoomTo}>
        <img
          key={view}
          src={onModel ? product.model_image_url! : product.image_url}
          alt={onModel ? `${product.name}, worn by a model (AI-styled preview)` : product.name}
        />
        <span className="zoom__hint" aria-hidden="true">
          Hover to zoom
        </span>
        {onModel && <span className="gallery__label">AI-styled preview · print and fit may vary slightly</span>}
      </div>
      {product.model_image_url && (
        <div className="gallery__thumbs" role="group" aria-label="Photos">
          {(
            [
              ['model', product.model_image_url, 'On model'],
              ['product', product.image_url, 'Product'],
            ] as const
          ).map(([key, src, label]) => (
            <button
              key={key}
              type="button"
              className={`gallery__thumb ${view === key ? 'is-active' : ''}`}
              aria-pressed={view === key}
              onClick={() => setView(key)}
            >
              <img src={src} alt="" />
              <span>{label}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

export default function ProductDetail() {
  const { productId = '' } = useParams()
  // Keyed so state resets cleanly when navigating between products.
  return <ProductView key={productId} productId={productId} />
}

function ProductView({ productId }: { productId: string }) {
  const [product, setProduct] = useState<Product | null>(null)
  const [error, setError] = useState('')
  const [missing, setMissing] = useState(false)

  useEffect(() => {
    fetchProduct(productId)
      .then(setProduct)
      .catch((e: Error) => (e instanceof NotFoundError ? setMissing(true) : setError(e.message)))
  }, [productId])

  useEffect(() => {
    if (product) document.title = `${product.name} | Campus Customs`
  }, [product])

  const back = (
    <Link to="/products" className="back-link">
      ← All products
    </Link>
  )

  if (missing)
    return (
      <section className="hero hero--compact">
        {back}
        <h1>We couldn't find that item.</h1>
        <p className="lead">It may have been removed from the collection.</p>
      </section>
    )

  if (error)
    return (
      <section className="section">
        {back}
        <p className="form-error" role="alert">
          {error}
        </p>
      </section>
    )

  if (!product)
    return (
      <section className="product-detail" aria-busy="true">
        <div className="product-detail__image skeleton" />
        <div className="skeleton skeleton--text" />
      </section>
    )

  const stock = stockLabel(product)

  return (
    <>
      <div className="section section--tight">{back}</div>
      <article className="product-detail">
        <Gallery product={product} />

        <div className="product-detail__info">
          <p className="eyebrow">{product.category}</p>
          <h1>{product.name}</h1>
          <p className="product-detail__price">{formatPrice(product.price)}</p>
          <p className={`stock stock--${stock.tone}`}>{stock.text}</p>
          <button
            type="button"
            className="ask-about"
            onClick={() => askAssistant('Tell me about this one. What sizes are in stock?')}
          >
            <span aria-hidden="true">✦</span> Ask the Bulldog about this
          </button>

          <p>{product.description}</p>

          {product.colors.length > 0 && (
            <div className="detail-block">
              <h2>Colours</h2>
              <ul className="tag-list">
                {product.colors.map((c) => (
                  <li key={c} className="tag">
                    {c}
                  </li>
                ))}
              </ul>
            </div>
          )}

          <div className="detail-block">
            <h2>Sizes</h2>
            <ul className="size-grid">
              {product.inventory.map((s) => (
                <li
                  key={s.size}
                  className={`size ${s.quantity === 0 ? 'size--out' : ''}`}
                >
                  <span className="size__label">{s.size}</span>
                  <span className="size__qty">
                    {s.quantity === 0
                      ? 'Sold out'
                      : s.quantity <= LOW_STOCK
                        ? `Only ${s.quantity} left`
                        : 'In stock'}
                  </span>
                </li>
              ))}
            </ul>
          </div>

          <dl className="spec-list">
            <div>
              <dt>Style</dt>
              <dd className="capitalize">{product.garment_type}</dd>
            </div>
            <div>
              <dt>Item #</dt>
              <dd>{product.product_id}</dd>
            </div>
          </dl>
        </div>
      </article>
    </>
  )
}
