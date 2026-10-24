import { useState, type ChangeEvent, type FormEvent } from 'react'
import { Link, Navigate, useNavigate } from 'react-router-dom'
import PasswordInput from '../components/PasswordInput'
import { MIN_PASSWORD, signup } from '../lib/auth'
import { useAuth } from '../lib/AuthContext'

export default function CreateAccount() {
  const { user, setUser } = useAuth()
  const navigate = useNavigate()
  const [form, setForm] = useState({
    firstName: '',
    lastName: '',
    email: '',
    password: '',
    confirm: '',
  })
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)

  if (user && !submitting) return <Navigate to="/products" replace />

  const update =
    (field: keyof typeof form) => (e: ChangeEvent<HTMLInputElement>) =>
      setForm((f) => ({ ...f, [field]: e.target.value }))

  const longEnough = form.password.length >= MIN_PASSWORD
  const matches = form.confirm.length > 0 && form.password === form.confirm

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    if (!form.firstName.trim() || !form.lastName.trim() || !form.email.trim()) {
      setError('Fill in your name and email.')
      return
    }
    if (!longEnough) {
      setError(`Password must be at least ${MIN_PASSWORD} characters.`)
      return
    }
    if (form.password !== form.confirm) {
      setError('Passwords do not match.')
      return
    }
    setError('')
    setSubmitting(true)
    try {
      const newUser = await signup({
        first_name: form.firstName.trim(),
        last_name: form.lastName.trim(),
        email: form.email.trim(),
        password: form.password,
        confirm_password: form.confirm,
      })
      setUser(newUser)
      navigate('/products', { replace: true })
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <section className="auth">
      <div className="auth__card card">
        <h1>Join Campus Customs</h1>
        <p className="muted">
          Save your favourites and get help from our shopping assistant.
        </p>

        <form onSubmit={handleSubmit} noValidate>
          <div className="form-row">
            <div>
              <label htmlFor="ca-first">First name</label>
              <input
                id="ca-first"
                autoComplete="given-name"
                maxLength={50}
                value={form.firstName}
                onChange={update('firstName')}
                required
              />
            </div>
            <div>
              <label htmlFor="ca-last">Last name</label>
              <input
                id="ca-last"
                autoComplete="family-name"
                maxLength={50}
                value={form.lastName}
                onChange={update('lastName')}
                required
              />
            </div>
          </div>

          <label htmlFor="ca-email">Email</label>
          <input
            id="ca-email"
            type="email"
            autoComplete="email"
            maxLength={254}
            value={form.email}
            onChange={update('email')}
            required
          />

          <label htmlFor="ca-password">Password</label>
          <PasswordInput
            id="ca-password"
            autoComplete="new-password"
            aria-describedby="ca-password-hint"
            maxLength={128}
            value={form.password}
            onChange={update('password')}
            required
          />
          <p id="ca-password-hint" className={`hint ${longEnough ? 'hint--ok' : 'muted'}`}>
            {longEnough ? '✓ ' : ''}At least {MIN_PASSWORD} characters. Avoid your name, your
            email or common passwords.
          </p>

          <label htmlFor="ca-confirm">Confirm password</label>
          <PasswordInput
            id="ca-confirm"
            autoComplete="new-password"
            aria-describedby="ca-confirm-hint"
            maxLength={128}
            value={form.confirm}
            onChange={update('confirm')}
            required
          />
          {form.confirm && (
            <p id="ca-confirm-hint" className={`hint ${matches ? 'hint--ok' : 'hint--bad'}`} aria-live="polite">
              {matches ? '✓ Passwords match' : 'Passwords do not match yet'}
            </p>
          )}

          {error && (
            <p className="form-error" role="alert">
              {error}
            </p>
          )}

          <button type="submit" className="btn btn--primary btn--block" disabled={submitting}>
            {submitting ? 'Creating account…' : 'Create Account'}
          </button>
        </form>

        <p className="auth__switch muted">
          Already have an account? <Link to="/login">Log in</Link>
        </p>
      </div>
    </section>
  )
}
