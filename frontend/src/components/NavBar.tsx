import { useState } from 'react'
import { Link, NavLink, useNavigate } from 'react-router-dom'
import { useAuth } from '../lib/AuthContext'
import Crest from './Crest'

const links = [
  { to: '/', label: 'Home', end: true },
  { to: '/products', label: 'Products' },
  { to: '/about', label: 'About Us' },
]

export default function NavBar() {
  const [open, setOpen] = useState(false)
  const close = () => setOpen(false)
  const { user, loading, logout } = useAuth()
  const navigate = useNavigate()

  async function handleLogout() {
    close()
    await logout()
    navigate('/')
  }

  return (
    <header className="nav">
      <div className="ticker" aria-label="Store announcements">
        <div className="ticker__track">
          {[0, 1].map((copy) => (
            <span key={copy} className="ticker__group" aria-hidden={copy === 1}>
              <span>Officially licensed Yale apparel</span>
              <span>57 Broadway · New Haven</span>
              <span>Sizes XS–XXL</span>
              <span>Ask the Bulldog: our AI shop assistant</span>
              <span>14 residential colleges · 20+ varsity sports</span>
            </span>
          ))}
        </div>
      </div>
      <div className="nav__inner">
        <Link to="/" className="nav__brand" onClick={close}>
          <Crest />
          <span className="nav__wordmark">
            Campus <span className="accent">Customs</span>
            <small>Yale gear · New Haven</small>
          </span>
        </Link>

        <button
          type="button"
          className="nav__toggle"
          aria-expanded={open}
          aria-controls="primary-nav"
          aria-label={open ? 'Close menu' : 'Open menu'}
          onClick={() => setOpen((o) => !o)}
        >
          <span />
          <span />
          <span />
        </button>

        <nav
          id="primary-nav"
          className={`nav__menu ${open ? 'is-open' : ''}`}
          aria-label="Primary"
        >
          <ul className="nav__links">
            {links.map((l) => (
              <li key={l.to}>
                <NavLink to={l.to} end={l.end} onClick={close}>
                  {l.label}
                </NavLink>
              </li>
            ))}
          </ul>
          <div className="nav__auth" aria-busy={loading}>
            {user ? (
              <>
                <span className="nav__user">
                  Hi, <strong>{user.first_name}</strong>
                </span>
                <button type="button" className="btn btn--ghost" onClick={handleLogout}>
                  Log Out
                </button>
              </>
            ) : (
              <>
                <NavLink to="/login" className="btn btn--ghost" onClick={close}>
                  Log In
                </NavLink>
                <NavLink to="/create-account" className="btn btn--primary" onClick={close}>
                  Create Account
                </NavLink>
              </>
            )}
          </div>
        </nav>
      </div>
    </header>
  )
}
