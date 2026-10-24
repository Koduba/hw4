import Mannequin from './Mannequin'

interface Wearable {
  product_id: string
  name: string
  category: string
  image_url: string
  model_image_url?: string | null
  cutout_url?: string | null
  cutout_aspect?: number | null
}

/**
 * Product photo that cross-fades on hover to the product "being worn": an AI on-model
 * photo if one exists, otherwise the illustrated mannequin dressed in the real photo.
 * Used by the Products grid, Home tiles and the chat showcase cards.
 */
export default function ModelSwap({ product: p }: { product: Wearable }) {
  const worn = p.model_image_url ? (
    <img className="model-swap" src={p.model_image_url} alt="" aria-hidden="true" loading="lazy" />
  ) : p.cutout_url ? (
    <span className="model-swap" aria-hidden="true">
      <Mannequin id={p.product_id} cutoutUrl={p.cutout_url} aspect={p.cutout_aspect} category={p.category} name={p.name} />
    </span>
  ) : null
  return (
    <>
      <img src={p.image_url} alt={p.name} loading="lazy" />
      {worn}
      {worn && <span className="model-badge">{p.model_image_url ? 'On model' : 'Try-on view'}</span>}
    </>
  )
}
