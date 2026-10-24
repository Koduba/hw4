// Lets any part of the site open the chat and (optionally) send a question,
// e.g. the Home "Ask the Bulldog" bar or "Ask about this" on a product page.
const EVENT = 'cc:ask-assistant'

export function askAssistant(message?: string) {
  window.dispatchEvent(new CustomEvent<string | undefined>(EVENT, { detail: message }))
}

export function onAskAssistant(handler: (message?: string) => void) {
  const listener = (e: Event) => handler((e as CustomEvent<string | undefined>).detail)
  window.addEventListener(EVENT, listener)
  return () => window.removeEventListener(EVENT, listener)
}
