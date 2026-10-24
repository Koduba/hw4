import { useEffect, useRef, useState, type ElementType, type HTMLAttributes, type ReactNode } from 'react'

/** Fades/slides its children in the first time they scroll into view. */
export default function Reveal({
  children,
  as: Tag = 'div',
  className = '',
  delay = 0,
  ...rest
}: HTMLAttributes<HTMLElement> & {
  children: ReactNode
  as?: ElementType
  className?: string
  delay?: number
}) {
  const ref = useRef<HTMLElement>(null)
  const [shown, setShown] = useState(false)

  useEffect(() => {
    const el = ref.current
    if (!el) return
    const io = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setShown(true)
          io.disconnect()
        }
      },
      { rootMargin: '0px 0px -8% 0px' },
    )
    io.observe(el)
    return () => io.disconnect()
  }, [])

  return (
    <Tag {...rest} ref={ref} className={`reveal ${shown ? 'is-in' : ''} ${className}`} style={{ transitionDelay: `${delay}ms` }}>
      {children}
    </Tag>
  )
}
