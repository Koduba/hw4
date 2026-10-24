import { Link } from 'react-router-dom'

const values = [
  {
    title: 'Local first',
    body: 'We are a New Haven shop, not a faceless warehouse. Stop by Broadway and say hi.',
  },
  {
    title: 'Every corner of Yale',
    body: 'Fourteen residential colleges, more than twenty varsity sports and a dozen-plus graduate schools. If you belong to it, we want to make gear for it.',
  },
  {
    title: 'Built to last',
    body: 'Heavyweight fleece, tri-blend tees and embroidered crests made to survive many Harvard-Yale weekends.',
  },
]

export default function About() {
  return (
    <>
      <section className="hero hero--compact">
        <p className="eyebrow">About us</p>
        <h1>
          Outfitting the Yale community, <span className="accent">one crest at a time</span>.
        </h1>
        <p className="lead">
          Campus Customs started with a simple idea: Yale pride should not be
          limited to one blue hoodie. We carry gear for the first-year who just
          got sorted into a college, the rower up at dawn, the SOM grad
          heading off to a new job, and the grandparent who never misses
          Commencement.
        </p>
      </section>

      <section className="section split">
        <div>
          <h2>Our story</h2>
          <p>
            We set up shop on Broadway, a short walk from Old Campus, so
            students and visitors could find officially licensed Yale apparel
            without the guesswork. Since then the range has grown from a
            handful of classic sweatshirts into collections for every
            residential college, team and professional school.
          </p>
          <p>
            We still think about each piece the way a student would. Is it
            comfortable enough for a late night in the library? Sharp enough
            for a family photo on the Green? Tough enough for a cold afternoon
            at the Bowl?
          </p>
        </div>
        <aside className="card stat-card" aria-label="Shop at a glance">
          <dl>
            <div>
              <dt>Products</dt>
              <dd>100+</dd>
            </div>
            <div>
              <dt>Sizes</dt>
              <dd>XS–XXL</dd>
            </div>
            <div>
              <dt>Home base</dt>
              <dd>New Haven</dd>
            </div>
          </dl>
        </aside>
      </section>

      <section className="section" aria-labelledby="values-heading">
        <h2 id="values-heading">What we stand for</h2>
        <div className="grid grid--3">
          {values.map((v) => (
            <div key={v.title} className="card">
              <h3>{v.title}</h3>
              <p className="muted">{v.body}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="banner">
        <div>
          <h2>Come visit</h2>
          <p className="muted">57 Broadway, New Haven, CT 06511</p>
        </div>
        <Link to="/products" className="btn btn--primary btn--lg">
          Shop online
        </Link>
      </section>
    </>
  )
}
