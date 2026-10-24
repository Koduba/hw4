import type { Showcase } from '../lib/chat'

interface Props {
  onProductPage: boolean
  category?: string | null
  showcase?: Showcase | null
  loggedIn: boolean
  hasHistory: boolean
  disabled: boolean
  onPick: (text: string) => void
}

/**
 * Context-aware suggestion chips above the chat input (Problem 9).
 * Shoppers often don't know what the assistant can do; these show it, and change
 * with the page: product questions on a product page, browsing ideas elsewhere.
 */
function suggestions({ onProductPage, category, showcase, loggedIn, hasHistory }: Omit<Props, 'disabled' | 'onPick'>) {
  if (onProductPage) {
    return ['Do you have this in M?', 'What colours does it come in?', 'Show me similar items under $60']
  }
  const list: string[] = []
  if (showcase && showcase.products.length > 2) list.push('Is the first one in stock in M?')
  if (category) list.push(`Which ${category.toLowerCase()} are in stock in L?`)
  list.push('What hoodies do you have?', 'Gift ideas under $60', 'Anything with Handsome Dan?')
  if (loggedIn && hasHistory) list.push('What did you show me last time?')
  return list.slice(0, 4)
}

export default function QuickReplies({ disabled, onPick, ...context }: Props) {
  const items = suggestions(context)
  return (
    <div className="quick-replies" role="group" aria-label="Suggested questions">
      {items.map((text) => (
        <button key={text} type="button" className="quick-reply" disabled={disabled} onClick={() => onPick(text)}>
          {text}
        </button>
      ))}
    </div>
  )
}
