import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { matchPath, useLocation } from 'react-router-dom'
import type { Showcase } from './chat'

interface ShowcaseState {
  showcase: Showcase | null
  /**
   * Full stage vs. compact dock. Derived, not stored: the stage is full on the page
   * where it was shown/expanded, and collapses to a dock on any OTHER product
   * detail page — so clicking a card (in the stage, the chat, or the grid) always
   * lands on a detail view that is visible, not buried under the picks.
   */
  compact: boolean
  /** True while the assistant is working on a reply (drives the "searching" scanline). */
  searching: boolean
  show: (s: Showcase) => void
  expand: () => void
  close: () => void
  setSearching: (v: boolean) => void
}

const ShowcaseContext = createContext<ShowcaseState | null>(null)

const isProductPage = (path: string) => !!matchPath('/products/:productId', path)

/** Shared between the chat widget (which receives showcases) and the page stage (which renders them). */
export function ShowcaseProvider({ children }: { children: ReactNode }) {
  const { pathname } = useLocation()
  const [showcase, setShowcase] = useState<Showcase | null>(null)
  const [shownAt, setShownAt] = useState('')
  const [searching, setSearching] = useState(false)

  // Latest path, read when a reply arrives (the shopper may have navigated while waiting).
  const pathRef = useRef(pathname)
  useEffect(() => {
    pathRef.current = pathname
  }, [pathname])

  const show = useCallback((s: Showcase) => {
    setShowcase(s)
    setShownAt(pathRef.current)
  }, [])
  const expand = useCallback(() => setShownAt(pathRef.current), [])
  const close = useCallback(() => setShowcase(null), [])
  const compact = !!showcase && isProductPage(pathname) && pathname !== shownAt

  const value = useMemo(
    () => ({ showcase, compact, searching, show, expand, close, setSearching }),
    [showcase, compact, searching, show, expand, close],
  )
  return <ShowcaseContext.Provider value={value}>{children}</ShowcaseContext.Provider>
}

// eslint-disable-next-line react-refresh/only-export-components
export function useShowcase() {
  const ctx = useContext(ShowcaseContext)
  if (!ctx) throw new Error('useShowcase must be used inside <ShowcaseProvider>')
  return ctx
}
