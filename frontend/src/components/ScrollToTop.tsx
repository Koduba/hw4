import { useEffect } from 'react'
import { useLocation } from 'react-router-dom'

/**
 * React Router keeps the old scroll position on navigation, so clicking a card
 * far down a page used to open the product page part-way down. Reset to the top
 * whenever the path changes (not for ?q=/?category= filter changes on /products).
 */
export default function ScrollToTop() {
  const { pathname } = useLocation()
  useEffect(() => {
    window.scrollTo({ top: 0, left: 0, behavior: 'instant' })
  }, [pathname])
  return null
}
