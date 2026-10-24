import { useEffect, useState, type CSSProperties, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import ModelSwap from '../components/ModelSwap'
import Reveal from '../components/Reveal'
import { fetchProducts, formatPrice, type Product } from '../lib/api'
import { askAssistant } from '../lib/assistantBus'

const STICKERS = ['district-vit-crewneck-vintage-bulldog', 'basic-hoodie-big-yale', '2025-yale-vs-harvard-t-shirt']
const FRESH = [
  'champion-reverse-weave-hoodie-1',
  'saybrook-college-crewneck',
  'boola-boola-t-shirt',
  'branford-1-4-zip',
  'benjamin-franklin-fleece-jacket',
  'yale-mom-hoodie',
  'district-vit-hoodie-vintage-sailor-bulldog',
  'school-of-management-crest-t-shirt',
]
const COLLEGES = [
  'Benjamin Franklin', 'Berkeley', 'Branford', 'Davenport', 'Ezra Stiles', 'Grace Hopper', 'Jonathan Edwards',
  'Morse', 'Pauli Murray', 'Pierson', 'Saybrook', 'Silliman', 'Timothy Dwight', 'Trumbull',
]
const PENNANTS = [
  { title: 'Residential Colleges', blurb: 'Rep the college you call home.', ask: 'Show me residential college gear' },
  { title: 'Varsity Sports', blurb: 'From the Bowl to the boathouse.', ask: 'Show me varsity sports gear' },
  { title: 'Yale Family', blurb: 'Mom, Dad, Grandpa… bragging rights.', ask: 'Show me Yale family gear like Mom and Dad' },
  { title: 'Grad & Professional', blurb: 'SOM, Law, Medicine, Art, Music.', ask: 'Show me graduate and professional school gear' },
]
const IDEAS = ['Navy hoodie in M under $70', 'Saybrook gear', 'Gift for a Yale mom', 'Anything with Handsome Dan']

export default function Home() {
  const [products, setProducts] = useState<Product[]>([])
  const [ask, setAsk] = useState('')

  useEffect(() => {
    fetchProducts().then(setProducts).catch(() => setProducts([]))
  }, [])

  const byId = new Map(products.map((p) => [p.product_id, p]))
  const stickers = STICKERS.map((id) => byId.get(id)).filter((p): p is Product => !!p)
  const fresh = FRESH.map((id) => byId.get(id)).filter((p): p is Product => !!p && p.total_stock > 0)

  function submit(e: FormEvent) {
    e.preventDefault()
    if (ask.trim()) askAssistant(ask.trim())
    setAsk('')
  }

  return (
    <>
      <section className="hero2">
        <div className="hero2__copy">
          <p className="eyebrow">Est. on Broadway · New Haven, CT</p>
          <h1 className="hero2__title">
            <span className="hero2__script">Wear your</span>
            <span className="hero2__varsity" data-text="BULLDOG">
              BULLDOG
            </span>
            <span className="hero2__script hero2__script--end">pride, everywhere.</span>
          </h1>
          <p className="lead">
            Officially licensed Yale hoodies, crewnecks, quarter-zips and tees, for every college, team and proud
            family. Not sure what you want? Just ask.
          </p>

          <form className="askbar" onSubmit={submit} role="search">
            <label htmlFor="askbar-input" className="visually-hidden">
              Ask the Bulldog, our shopping assistant
            </label>
            <span className="askbar__spark" aria-hidden="true">
              ✦
            </span>
            <input
              id="askbar-input"
              value={ask}
              onChange={(e) => setAsk(e.target.value)}
              placeholder="Ask the Bulldog… e.g. navy hoodie in M under $70"
              maxLength={300}
              autoComplete="off"
            />
            <button type="submit" className="btn btn--primary">
              Ask
            </button>
          </form>
          <div className="askbar__ideas">
            {IDEAS.map((idea) => (
              <button key={idea} type="button" className="idea-chip" onClick={() => askAssistant(idea)}>
                {idea}
              </button>
            ))}
          </div>
        </div>

        <div className="stickers" aria-label="Featured pieces">
          <span className="patch" aria-hidden="true">
            <span>Boola</span>
            <span>Boola</span>
          </span>
          {stickers.map((p, i) => (
            <Link
              key={p.product_id}
              to={`/products/${p.product_id}`}
              className={`sticker sticker--${i + 1}`}
              style={{ '--i': i } as CSSProperties}
            >
              <img src={p.model_image_url ?? p.image_url} alt={p.model_image_url ? `${p.name}, worn by a model` : p.name} />
              <span className="sticker__tag">
                <span>{p.name}</span>
                <strong>{formatPrice(p.price)}</strong>
              </span>
            </Link>
          ))}
        </div>
      </section>

      <div className="marquee" aria-label="Residential colleges we carry">
        <div className="marquee__track">
          {[0, 1].map((copy) => (
            <span key={copy} className="marquee__group" aria-hidden={copy === 1}>
              {COLLEGES.map((c) => (
                <span key={c}>
                  {c} <i aria-hidden="true">✦</i>
                </span>
              ))}
            </span>
          ))}
        </div>
      </div>

      <Reveal as="section" className="section">
        <div className="section-head">
          <h2>
            Fresh off <em>the shelf</em>
          </h2>
          <Link to="/products" className="section-head__link">
            Shop all 102 →
          </Link>
        </div>
        <ul className="fresh-grid">
          {fresh.map((p, i) => (
            <li key={p.product_id} style={{ '--i': i } as CSSProperties}>
              <Link to={`/products/${p.product_id}`} className="tile">
                <span className="tile__media">
                  <ModelSwap product={p} />
                </span>
                <span className="tile__body">
                  <span className="tile__cat">{p.category}</span>
                  <span className="tile__name">{p.name}</span>
                  <span className="tile__price">{formatPrice(p.price)}</span>
                </span>
              </Link>
            </li>
          ))}
        </ul>
      </Reveal>

      <Reveal as="section" className="section">
        <div className="section-head">
          <h2>
            Find your <em>corner of Yale</em>
          </h2>
          <p className="muted">Tap a pennant and the Bulldog lays out the collection for you.</p>
        </div>
        <div className="pennants">
          {PENNANTS.map((c, i) => (
            <button
              key={c.title}
              type="button"
              className="pennant"
              style={{ '--i': i } as CSSProperties}
              onClick={() => askAssistant(c.ask)}
            >
              <span className="pennant__title">{c.title}</span>
              <span className="pennant__blurb">{c.blurb}</span>
              <span className="pennant__cta">Ask the Bulldog →</span>
            </button>
          ))}
        </div>
      </Reveal>

      <Reveal as="section" className="scoreboard" aria-label="Campus Customs at a glance">
        {[
          ['102', 'styles'],
          ['6', 'sizes, XS–XXL'],
          ['14', 'residential colleges'],
          ['1', 'shop on Broadway'],
        ].map(([n, label]) => (
          <div key={label} className="scoreboard__cell">
            <span className="scoreboard__num">{n}</span>
            <span className="scoreboard__label">{label}</span>
          </div>
        ))}
      </Reveal>

      <Reveal as="section" className="assistant-promo">
        <div>
          <p className="eyebrow">Meet your shop assistant</p>
          <h2>
            Ask the <em>Bulldog</em>.
          </h2>
          <p className="muted">
            It checks live stock in your size, finds the closest colour when we don't have yours, and lays out picks
            right on the page. Log in and it remembers you next time.
          </p>
          <button type="button" className="btn btn--primary btn--lg" onClick={() => askAssistant()}>
            Start chatting
          </button>
        </div>
        <div className="promo-chat" aria-hidden="true">
          <p className="promo-bubble promo-bubble--user">do you have this in pink?</p>
          <p className="promo-bubble">
            This one only comes in navy and white, but the Big Yale Tri-Blend Tee comes in dusty coral for $32.
          </p>
          <p className="promo-bubble promo-bubble--user">ooh, in M?</p>
          <p className="promo-bubble promo-bubble--typing">
            <span />
            <span />
            <span />
          </p>
        </div>
      </Reveal>
    </>
  )
}
