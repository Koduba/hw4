"""Generate AI "on-model" photos: a person wearing the real product.

Route (picked automatically):
  1. Portkey (PORTKEY_API_KEY, the project default): set PORTKEY_IMAGE_DEPLOYMENT to the
     name of an Azure image deployment on the class gateway. The request goes through the
     chat model's image_generation tool with header x-ms-oai-image-generation-deployment.
     (As of now the class key routes only to the gpt-5.6-luna chat deployment, so this
     needs an image deployment added on the class/Portkey side first.)
  2. Direct OpenAI (OPENAI_API_KEY), if set and no Portkey image deployment is configured.
Each request sends the real catalogue photo as the reference image, so the garment,
colours and print stay as close as possible to the actual item.

    cd hw4/backend
    .venv/bin/python generate_model_shots.py            # the 8 featured products
    .venv/bin/python generate_model_shots.py --force    # regenerate even if a file exists
    .venv/bin/python generate_model_shots.py basic-hoodie-big-yale   # just one

Output: data/model_shots/<product_id>.jpg plus data/model_shots/manifest.json.
The API exposes them as `model_image_url`; the site labels them "AI-styled preview".
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from openai import BadRequestError, NotFoundError, OpenAI

HERE = Path(__file__).resolve().parent
DATA = HERE.parent / "data"
OUT = DATA / "model_shots"
load_dotenv(HERE / ".env")
load_dotenv(HERE.parent / ".env")  # hw4/.env (see .env.example)
load_dotenv(HERE.parent.parent / ".env")  # class-folder .env

IMAGE_MODELS = [m for m in [os.getenv("OPENAI_IMAGE_MODEL"), "gpt-image-1.5", "gpt-image-1"] if m]
PORTKEY_BASE_URL = "https://api.portkey.ai/v1"
PORTKEY_IMAGE_DEPLOYMENT = os.getenv("PORTKEY_IMAGE_DEPLOYMENT")
CHAT_MODEL = os.getenv("OPENAI_MODEL", "gpt-5.6-luna")

# Featured products and the scene for each. Varied, fictional adult models in New Haven settings.
SHOTS = {
    "basic-hoodie-big-yale": "a young woman with curly dark hair, laughing, walking along a brick path on Old Campus in early autumn",
    "district-vit-crewneck-vintage-bulldog": "a young man with short locs leaning on a stone archway, relaxed smile, soft afternoon light",
    "2025-yale-vs-harvard-t-shirt": "a fan in their twenties in the stands at a football stadium on game day, crowd softly blurred behind",
    "champion-reverse-weave-hoodie-1": "a young East Asian man with a backpack outside a gothic library entrance, overcast day",
    "saybrook-college-crewneck": "a smiling young South Asian woman sitting on stone steps in a residential college courtyard",
    "boola-boola-t-shirt": "a young man with red hair and freckles on a New Haven street near a coffee shop, golden hour",
    "branford-1-4-zip": "a woman in her fifties with silver hair, warm smile, on a tree-lined campus green, crisp fall day",
    "yale-mom-hoodie": "a mother in her forties with a proud smile at a college move-in day, cardboard boxes softly blurred behind",
}

PROMPT = """Photorealistic lifestyle fashion photo for a college apparel shop.
Model and scene: {scene}.
The model is wearing EXACTLY the garment in the reference image: same garment type, same fabric colour,
same printed or embroidered text, logo and graphic, same placement and size on the garment. Do not change,
add, remove or misspell any lettering. No other logos or brand marks anywhere in the image.
Natural, flattering fit; three-quarter or waist-up framing with the garment's front design clearly visible
and unobstructed (no crossed arms, bags or hair covering the print). Realistic skin and hands, natural light,
shallow depth of field, editorial quality. No text overlays, no watermark."""


def generate_portkey(client: OpenAI, product_id: str, scene: str) -> dict:
    """Through the class Portkey gateway: chat model + image_generation tool + reference photo."""
    ref = DATA / "products" / f"{product_id}.jpg"
    started = time.time()
    photo = base64.b64encode(ref.read_bytes()).decode()
    response = client.responses.create(
        model=CHAT_MODEL,
        input=[{"role": "user", "content": [
            {"type": "input_text", "text": PROMPT.format(scene=scene)},
            {"type": "input_image", "image_url": f"data:image/jpeg;base64,{photo}"},
        ]}],
        tools=[{"type": "image_generation", "size": "1024x1536", "quality": "high",
                "output_format": "jpeg", "input_fidelity": "high"}],
        tool_choice={"type": "image_generation"},
        extra_headers={
            "x-ms-oai-image-generation-deployment": PORTKEY_IMAGE_DEPLOYMENT,
            "x-portkey-forward-headers": "x-ms-oai-image-generation-deployment",
        },
    )
    images = [o.result for o in response.output if o.type == "image_generation_call" and getattr(o, "result", None)]
    if not images:
        raise RuntimeError(f"{product_id}: Portkey returned no image")
    (OUT / f"{product_id}.jpg").write_bytes(base64.b64decode(images[0]))
    return {
        "file": f"{product_id}.jpg",
        "model": f"portkey:{PORTKEY_IMAGE_DEPLOYMENT}",
        "scene": scene,
        "seconds": round(time.time() - started, 1),
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def generate(client: OpenAI, product_id: str, scene: str) -> dict:
    """Direct OpenAI images.edit with the reference photo."""
    ref = DATA / "products" / f"{product_id}.jpg"
    last_error = None
    for model in IMAGE_MODELS:
        try:
            started = time.time()
            with ref.open("rb") as f:
                result = client.images.edit(
                    model=model,
                    image=f,
                    prompt=PROMPT.format(scene=scene),
                    size="1024x1536",
                    quality="high",
                    output_format="jpeg",
                    output_compression=88,
                    input_fidelity="high",  # keep the reference garment's details
                )
            (OUT / f"{product_id}.jpg").write_bytes(base64.b64decode(result.data[0].b64_json))
            return {
                "file": f"{product_id}.jpg",
                "model": model,
                "scene": scene,
                "seconds": round(time.time() - started, 1),
                "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            }
        except (NotFoundError, BadRequestError) as e:  # model not available / param unsupported → try next
            last_error = e
            continue
    raise RuntimeError(f"{product_id}: no image model worked ({type(last_error).__name__}: {str(last_error)[:200]})")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("products", nargs="*", help="product_ids (default: the 8 featured ones)")
    parser.add_argument("--force", action="store_true", help="regenerate even if the image exists")
    args = parser.parse_args()

    if PORTKEY_IMAGE_DEPLOYMENT and os.getenv("PORTKEY_API_KEY"):
        route, run = f"Portkey (image deployment {PORTKEY_IMAGE_DEPLOYMENT!r})", generate_portkey
        client = OpenAI(api_key=os.environ["PORTKEY_API_KEY"], base_url=PORTKEY_BASE_URL, timeout=300)
    elif os.getenv("OPENAI_API_KEY"):
        route, run = f"direct OpenAI ({IMAGE_MODELS[0]})", generate
        client = OpenAI(timeout=300)  # reads OPENAI_API_KEY
    else:
        sys.exit(
            "No image route configured.\n"
            "  Portkey (default): set PORTKEY_IMAGE_DEPLOYMENT=<Azure image deployment name> next to PORTKEY_API_KEY.\n"
            "    The class key currently only reaches the gpt-5.6-luna chat deployment, so an image\n"
            "    deployment (e.g. gpt-image-1.5) has to be added to the class Portkey/Azure setup first.\n"
            "  Or: set OPENAI_API_KEY to call OpenAI directly."
        )

    OUT.mkdir(parents=True, exist_ok=True)
    manifest_path = OUT / "manifest.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}

    wanted = args.products or list(SHOTS)
    todo = [p for p in wanted if args.force or not (OUT / f"{p}.jpg").exists()]
    unknown = [p for p in todo if p not in SHOTS]
    if unknown:
        sys.exit(f"No scene defined for: {', '.join(unknown)}")
    print(f"Generating {len(todo)} on-model photo(s) via {route} …")
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(run, client, p, SHOTS[p]): p for p in todo}
        for fut in as_completed(futures):
            pid = futures[fut]
            try:
                manifest[pid] = fut.result()
                print(f"  ✓ {pid}  ({manifest[pid]['model']}, {manifest[pid]['seconds']}s)")
            except Exception as e:  # keep going; report at the end
                print(f"  ✗ {pid}: {e}")
            manifest_path.write_text(json.dumps(manifest, indent=2))
    print(f"Done. {len(manifest)} photo(s) listed in {manifest_path.relative_to(HERE.parent)}")


if __name__ == "__main__":
    main()
