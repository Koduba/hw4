// Chat client for the shopping assistant (PydanticAI agent behind
// POST /api/chat on the FastAPI backend). The backend identifies the shopper
// from cookies (session = logged in, cc_guest = guest) and keeps the history
// itself, so we only send the new message plus what's on screen (PageContext).

export type ChatRole = 'user' | 'assistant'

/** Mirrors ProductCard in backend/models.py. */
export interface ProductCard {
  product_id: string
  name: string
  category: string
  price: number
  image_url: string
  model_image_url?: string | null
  page_url: string
  short_info: string
  colors: string[]
  sizes_in_stock: string[]
  in_stock: boolean
  stock_label: string
  /** The assistant's one-line reason this item matches (showcase only). */
  note?: string | null
}

/**
 * Mirrors Showcase in backend/models.py: products the agent found for a
 * browse question ("what hoodies do you have?"), rendered on the page.
 */
export interface Showcase {
  id: string
  title: string
  query: string
  category: string | null
  total_matches: number
  products: ProductCard[]
}

export interface ChatMessage {
  role: ChatRole
  content: string
  products?: ProductCard[]
  showcase?: Showcase | null
}

/**
 * Mirrors PageContext in backend/models.py: what's on screen when a message is sent.
 * The server checks ids against the catalogue and treats the text as data.
 */
export interface PageContext {
  path: string
  /** Set on /products/:productId, so "do you have this in pink?" knows which item. */
  product_id: string | null
  search_query: string | null
  category: string | null
  showcase_title: string | null
  showcase_product_ids: string[]
}

export interface ChatRequest {
  message: string
  page: PageContext
}

export interface ChatResponse {
  reply: string
  products: ProductCard[]
  showcase: Showcase | null
  /** True when the turn was stored in the database (logged-in shoppers). */
  saved: boolean
}

export const MAX_CHAT_MESSAGE = 1000

export class ChatAuthError extends Error {}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response
  try {
    res = await fetch(path, { credentials: 'same-origin', ...init })
  } catch {
    throw new Error("Can't reach the shop server. Please try again.")
  }
  if (res.status === 401) throw new ChatAuthError('Please log in to chat.')
  if (res.status === 204) return undefined as T
  const data = await res.json().catch(() => ({}))
  if (!res.ok) {
    throw new Error(typeof data.detail === 'string' ? data.detail : 'Something went wrong. Please try again.')
  }
  return data as T
}

export const sendChatMessage = (req: ChatRequest) =>
  request<ChatResponse>('/api/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(req),
  })

export const fetchChatHistory = () => request<ChatMessage[]>('/api/chat/history')

export const clearChatHistory = () => request<void>('/api/chat/history', { method: 'DELETE' })
