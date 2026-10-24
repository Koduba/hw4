import { Link } from 'react-router-dom'

const YEAR = new Date().getFullYear()

export default function Footer() {
  return (
    <footer className="footer">
      <div className="footer__inner">
        <div>
          <p className="footer__brand">
            Campus <span className="accent">Customs</span>
          </p>
          <p className="muted">57 Broadway, New Haven, CT 06511</p>
        </div>
        <nav aria-label="Footer">
          <ul className="footer__links">
            <li>
              <Link to="/products">Shop</Link>
            </li>
            <li>
              <Link to="/about">About Us</Link>
            </li>
            <li>
              <Link to="/login">Log In</Link>
            </li>
          </ul>
        </nav>
      </div>
      <p className="footer__fine muted">
        © {YEAR} Campus Customs. A class project for Yale
        SOM, not an official store.
      </p>
    </footer>
  )
}
