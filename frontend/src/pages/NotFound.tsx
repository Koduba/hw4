import { Link } from 'react-router-dom'

export default function NotFound() {
  return (
    <section className="hero hero--compact">
      <p className="eyebrow">404</p>
      <h1>This page wandered off campus.</h1>
      <Link to="/" className="btn btn--primary">
        Back to home
      </Link>
    </section>
  )
}
