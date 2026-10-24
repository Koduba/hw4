// Typed client for the FastAPI backend (hw4/backend/main.py).
// Vite proxies /api and /media to http://127.0.0.1:8000 in dev.

export interface SizeStock {
  size: string
  quantity: number
}

export interface Product {
  product_id: string
  name: string
  garment_type: string
  category: string
  description: string
  colors: string[]
  search_tags: string[]
  image_url: string
  /** AI-styled photo of a person wearing it (only for some products). */
  model_image_url?: string | null
  price: number
  total_stock: number
  inventory: SizeStock[]
}

export class NotFoundError extends Error {}

async function getJson<T>(path: string): Promise<T> {
  let res: Response
  try {
    res = await fetch(path)
  } catch {
    throw new Error("Can't reach the shop server. Is the backend running?")
  }
  if (res.status === 404) throw new NotFoundError('Not found')
  if (!res.ok) throw new Error(`Server error (${res.status}). Please try again.`)
  return res.json() as Promise<T>
}

export const fetchProducts = () => getJson<Product[]>('/api/products')

export const fetchProduct = (id: string) =>
  getJson<Product>(`/api/products/${encodeURIComponent(id)}`)

export const formatPrice = (price: number) =>
  price.toLocaleString('en-US', { style: 'currency', currency: 'USD' })

export const LOW_STOCK = 5

export function stockLabel(p: Pick<Product, 'inventory' | 'total_stock'>) {
  if (p.total_stock === 0) return { text: 'Sold out', tone: 'out' as const }
  const sizesIn = p.inventory.filter((s) => s.quantity > 0).length
  if (sizesIn < p.inventory.length)
    return { text: `${sizesIn} of ${p.inventory.length} sizes in stock`, tone: 'low' as const }
  return { text: 'All sizes in stock', tone: 'ok' as const }
}
