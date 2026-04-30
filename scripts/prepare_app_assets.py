from __future__ import annotations

import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BRANDING_DIR = ROOT / "assets" / "branding"
FRONTEND_PUBLIC = ROOT / "frontend" / "public"
FRONTEND_BRAND = FRONTEND_PUBLIC / "brand"
DESKTOP_ASSETS = ROOT / "desktop" / "assets"

SOURCE_CANDIDATES = [
    BRANDING_DIR / "rasentinel-source.png",
    BRANDING_DIR / "source.png",
    BRANDING_DIR / "rasentinel.png",
    BRANDING_DIR / "app.png",
    BRANDING_DIR / "icon.png",
]

PNG_SIZES = {
    "rasentinel-mark.png": 512,
    "favicon-16x16.png": 16,
    "favicon-32x32.png": 32,
    "favicon-48x48.png": 48,
    "favicon-192x192.png": 192,
    "apple-touch-icon.png": 180,
}


def find_source() -> Path:
    for candidate in SOURCE_CANDIDATES:
        if candidate.exists():
            return candidate

    expected = "\n".join(f"  - {path}" for path in SOURCE_CANDIDATES)
    raise FileNotFoundError(
        "No RASentinel source PNG was found. Put the PNG in assets/branding as one of:\n"
        f"{expected}"
    )


def ensure_dirs() -> None:
    FRONTEND_PUBLIC.mkdir(parents=True, exist_ok=True)
    FRONTEND_BRAND.mkdir(parents=True, exist_ok=True)
    DESKTOP_ASSETS.mkdir(parents=True, exist_ok=True)


def copy_fallback(source_path: Path) -> None:
    """Fallback path used if Pillow is not installed.

    This still fixes the in-app sidebar mark and Electron dev PNG. ICO/favicon resizing
    needs Pillow, but the app can still run cleanly with the PNG assets.
    """
    ensure_dirs()
    for output in [
        FRONTEND_BRAND / "rasentinel-mark.png",
        FRONTEND_PUBLIC / "rasentinel.png",
        DESKTOP_ASSETS / "rasentinel.png",
    ]:
        shutil.copyfile(source_path, output)

    print("Pillow is not installed, copied PNG assets without resizing.")
    print("Install Pillow for ICO/favicon generation: python -m pip install pillow")


def make_square(image):
    image = image.convert("RGBA")
    width, height = image.size
    size = max(width, height)
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    canvas.alpha_composite(image, ((size - width) // 2, (size - height) // 2))
    return canvas


def save_resized_pngs(source_image) -> None:
    ensure_dirs()

    for filename, size in PNG_SIZES.items():
        resized = source_image.resize((size, size), Image.Resampling.LANCZOS)
        resized.save(FRONTEND_BRAND / filename)

    desktop_png = source_image.resize((512, 512), Image.Resampling.LANCZOS)
    desktop_png.save(DESKTOP_ASSETS / "rasentinel.png")
    desktop_png.save(FRONTEND_PUBLIC / "rasentinel.png")


def save_ico(source_image) -> None:
    ensure_dirs()

    desktop_sizes = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    browser_sizes = [(16, 16), (32, 32), (48, 48), (64, 64)]

    source_image.save(DESKTOP_ASSETS / "rasentinel.ico", format="ICO", sizes=desktop_sizes)
    source_image.save(FRONTEND_PUBLIC / "favicon.ico", format="ICO", sizes=browser_sizes)


def main() -> None:
    source_path = find_source()
    print(f"Using source image: {source_path}")

    try:
        global Image
        from PIL import Image  # type: ignore
    except Exception:
        copy_fallback(source_path)
        return

    source_image = make_square(Image.open(source_path))
    save_resized_pngs(source_image)
    save_ico(source_image)

    print("Generated RASentinel branding assets:")
    print(f"  {FRONTEND_PUBLIC / 'favicon.ico'}")
    print(f"  {FRONTEND_BRAND / 'rasentinel-mark.png'}")
    print(f"  {DESKTOP_ASSETS / 'rasentinel.ico'}")
    print(f"  {DESKTOP_ASSETS / 'rasentinel.png'}")


if __name__ == "__main__":
    main()
