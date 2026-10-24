// Account API client. The session lives in an HttpOnly cookie set by the
// backend, so this code (and any other script on the page) never sees the
// token. We only ever hold the public profile below.

export interface User {
  first_name: string
  last_name: string
  email: string
}

export interface SignupInput {
  first_name: string
  last_name: string
  email: string
  password: string
  confirm_password: string
}

export const MIN_PASSWORD = 10

async function post<T>(path: string, body?: unknown): Promise<T> {
  let res: Response
  try {
    res = await fetch(path, {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: body === undefined ? undefined : JSON.stringify(body),
    })
  } catch {
    throw new Error("Can't reach the shop server. Please try again.")
  }
  if (res.status === 204) return undefined as T
  const data = await res.json().catch(() => ({}))
  if (!res.ok) {
    const detail = typeof data.detail === 'string' ? data.detail : 'Something went wrong.'
    throw new Error(detail)
  }
  return data as T
}

export const signup = (input: SignupInput) => post<User>('/api/auth/signup', input)

export const login = (email: string, password: string) =>
  post<User>('/api/auth/login', { email, password })

export const logout = () => post<void>('/api/auth/logout')

export async function fetchMe(): Promise<User | null> {
  try {
    const res = await fetch('/api/auth/me', { credentials: 'same-origin' })
    return res.ok ? ((await res.json()) as User) : null
  } catch {
    return null
  }
}

/** Only allow redirects to our own pages (blocks ?next=https://evil.example). */
export function safeNext(next: string | null): string {
  return next && next.startsWith('/') && !next.startsWith('//') ? next : '/products'
}
