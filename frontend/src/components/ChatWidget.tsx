import { useEffect, useRef, useState, type FormEvent } from 'react'
import { Link, matchPath, useLocation, useSearchParams } from 'react-router-dom'
import { formatPrice } from '../lib/api'
import { useAuth } from '../lib/AuthContext'
import { useShowcase } from '../lib/ShowcaseContext'
import QuickReplies from './QuickReplies'
import Crest from './Crest'
import { onAskAssistant } from '../lib/assistantBus'
import {
  ChatAuthError,
  clearChatHistory,
  fetchChatHistory,
  MAX_CHAT_MESSAGE,
  sendChatMessage,
  type ChatMessage,
  type PageContext,
} from '../lib/chat'

const greeting = (name?: string): ChatMessage => ({
  role: 'assistant',
  content: `Hi${name ? ` ${name}` : ' there'}! Looking for something Yale? Ask me about sizes, colours, colleges, sports or gift ideas.`,
})

const GUEST = 'guest'

export default function ChatWidget() {
  const { user, setUser } = useAuth()
  const { showcase: onPage, show: showOnPage, setSearching } = useShowcase()
  const [open, setOpen] = useState(false)
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [historyFor, setHistoryFor] = useState<string | null>(null)
  const [draft, setDraft] = useState('')
  const [sending, setSending] = useState(false)
  const [error, setError] = useState('')
  const listRef = useRef<HTMLOListElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)
  const { pathname } = useLocation()
  const [params] = useSearchParams()
  const currentProductId = matchPath('/products/:productId', pathname)?.params.productId
  // Whose conversation is on screen: the logged-in email, or this browser's guest chat.
  const who = user?.email ?? GUEST

  // Load the conversation when the panel opens, and again whenever the person changes
  // (log in → their saved history from the DB; log out → this visit's guest chat, if any).
  useEffect(() => {
    if (!open || historyFor === who) return
    let cancelled = false
    fetchChatHistory()
      .then((h) => !cancelled && setMessages(h))
      .catch(() => !cancelled && setMessages([]))
      .finally(() => !cancelled && setHistoryFor(who))
    return () => {
      cancelled = true
    }
  }, [open, who, historyFor])

  // "Ask the Bulldog" from anywhere on the site: open the panel and send the question.
  const pendingAsk = useRef<string | null>(null)
  useEffect(
    () =>
      onAskAssistant((message) => {
        setOpen(true)
        if (message) pendingAsk.current = message
      }),
    [],
  )
  useEffect(() => {
    if (open && !loadingHistory && !sending && pendingAsk.current) {
      const text = pendingAsk.current
      pendingAsk.current = null
      void send(text)
    }
  })

  /** What's on screen, sent with every message so "this one" / "these" make sense. */
  function pageContext(): PageContext {
    return {
      path: pathname,
      product_id: currentProductId ?? null,
      search_query: pathname === '/products' ? params.get('q') : null,
      category: pathname === '/products' ? params.get('category') : null,
      showcase_title: onPage?.title ?? null,
      showcase_product_ids: onPage?.products.map((p) => p.product_id) ?? [],
    }
  }

  useEffect(() => {
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight })
  }, [messages, sending, open])

  useEffect(() => {
    if (open) inputRef.current?.focus()
  }, [open])

  // Never show one person's messages to another: only render history loaded for `who`.
  const shown = historyFor === who ? messages : []
  const loadingHistory = open && historyFor !== who

  function handleSubmit(e: FormEvent) {
    e.preventDefault()
    void send(draft)
  }

  async function send(raw: string) {
    const text = raw.trim()
    if (!text || sending) return
    setMessages((m) => [...m, { role: 'user', content: text }])
    setDraft('')
    setError('')
    setSending(true)
    setSearching(true)
    try {
      const res = await sendChatMessage({ message: text, page: pageContext() })
      setMessages((m) => [
        ...m,
        { role: 'assistant', content: res.reply, products: res.products, showcase: res.showcase },
      ])
      if (res.showcase) {
        showOnPage(res.showcase)
        // On small screens the chat panel covers the page; tuck it away so the picks are visible.
        if (window.matchMedia('(max-width: 700px)').matches) setOpen(false)
      }
    } catch (err) {
      if (err instanceof ChatAuthError) setUser(null)
      setError((err as Error).message)
      setDraft(text) // let them retry without retyping
      setMessages((m) => m.slice(0, -1))
    } finally {
      setSending(false)
      setSearching(false)
    }
  }

  async function handleClear() {
    try {
      await clearChatHistory()
      setMessages([])
      setError('')
    } catch (err) {
      setError((err as Error).message)
    }
  }

  return (
    <div className="chat">
      {open && (
        <section id="chat-panel" className="chat__panel" aria-label="Shopping assistant">
          <header className="chat__header">
            <Crest size={36} className="chat__avatar" />
            <div className="chat__who">
              <p className="chat__title">
                Ask the Bulldog <span className="chat__online" aria-label="online" />
              </p>
              <p className="chat__subtitle">
                {user ? `Signed in as ${user.first_name} · chat saved` : 'Guest chat · not saved'}
              </p>
            </div>
            <div className="chat__actions">
              {shown.length > 0 && (
                <button type="button" className="chat__clear" onClick={handleClear}>
                  New chat
                </button>
              )}
              <button
                type="button"
                className="chat__close"
                aria-label="Close chat"
                onClick={() => setOpen(false)}
              >
                ×
              </button>
            </div>
          </header>

          {!user && (
            <p className="chat__guest">
              You're chatting as a guest, so this conversation won't be saved.{' '}
              <Link to={`/login?next=${encodeURIComponent(pathname)}`} onClick={() => setOpen(false)}>
                Log in
              </Link>{' '}
              to keep it.
            </p>
          )}
          <>
              <ol className="chat__messages" ref={listRef} aria-live="polite" aria-busy={loadingHistory}>
                {loadingHistory ? (
                  <li className="bubble bubble--assistant muted">Loading your conversation…</li>
                ) : (
                  [greeting(user?.first_name), ...shown].map((m, i) => (
                    <li key={i} className={`bubble-row bubble-row--${m.role}`}>
                      {m.role === 'assistant' && <Crest size={22} className="bubble__avatar" />}
                      <div className={`bubble bubble--${m.role}`}>
                        <span className="visually-hidden">
                          {m.role === 'user' ? 'You said:' : 'Assistant said:'}
                        </span>
                        {m.content}
                      </div>
                      {m.showcase && (
                        <button
                          type="button"
                          className="showcase-pill"
                          onClick={() => m.showcase && showOnPage(m.showcase)}
                        >
                          <span className="spark" aria-hidden="true">✦</span>
                          <span>
                            <strong>{m.showcase.title}</strong> · {m.showcase.products.length} on the page
                          </span>
                          <span className="showcase-pill__cta">View</span>
                        </button>
                      )}
                      {!!m.products?.length && (
                        <ul className="chat-products" aria-label="Suggested products">
                          {m.products.map((p) => (
                            <li key={p.product_id}>
                              <Link to={p.page_url} className="chat-product">
                                <img src={p.image_url} alt="" loading="lazy" />
                                <span className="chat-product__name">{p.name}</span>
                                <span className="chat-product__price">
                                  {formatPrice(p.price)}
                                  {!p.in_stock && <span className="chat-product__out"> · Sold out</span>}
                                </span>
                              </Link>
                            </li>
                          ))}
                        </ul>
                      )}
                    </li>
                  ))
                )}
                {sending && (
                  <li className="bubble bubble--assistant bubble--typing" aria-label="Assistant is typing">
                    <span />
                    <span />
                    <span />
                  </li>
                )}
              </ol>

              {error && (
                <p className="chat__error" role="alert">
                  {error}
                </p>
              )}

              <QuickReplies
                onProductPage={!!currentProductId}
                category={pathname === '/products' ? params.get('category') : null}
                showcase={onPage}
                loggedIn={!!user}
                hasHistory={shown.length > 0}
                disabled={sending || loadingHistory}
                onPick={(text) => void send(text)}
              />
              <form className="chat__form" onSubmit={handleSubmit}>
                <label htmlFor="chat-input" className="visually-hidden">
                  Message
                </label>
                <input
                  id="chat-input"
                  ref={inputRef}
                  value={draft}
                  maxLength={MAX_CHAT_MESSAGE}
                  onChange={(e) => setDraft(e.target.value)}
                  placeholder={currentProductId ? 'Ask about this item…' : 'Ask about a product…'}
                  autoComplete="off"
                  disabled={loadingHistory}
                />
                <button type="submit" className="btn btn--primary" disabled={!draft.trim() || sending}>
                  Send
                </button>
              </form>
          </>
        </section>
      )}

      {!open && pathname === '/' && (
        <button type="button" className="chat__nudge" onClick={() => setOpen(true)} tabIndex={-1} aria-hidden="true">
          Ask the Bulldog
        </button>
      )}
      <button
        type="button"
        className={`chat__launcher ${open ? '' : 'is-idle'}`}
        aria-expanded={open}
        aria-controls="chat-panel"
        aria-label={open ? 'Close shopping assistant' : 'Open shopping assistant'}
        onClick={() => setOpen((o) => !o)}
      >
        {open ? '×' : (
          <svg viewBox="0 0 24 24" width="26" height="26" aria-hidden="true">
            <path
              fill="currentColor"
              d="M12 3C6.5 3 2 6.6 2 11c0 2.4 1.3 4.5 3.4 6L4.5 21l4.3-2.3c1 .2 2.1.3 3.2.3 5.5 0 10-3.6 10-8s-4.5-8-10-8Z"
            />
          </svg>
        )}
      </button>
    </div>
  )
}
