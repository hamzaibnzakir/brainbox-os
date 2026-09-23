from __future__ import annotations

import base64
import io
import platform
from typing import Any


def _require_windows() -> None:
    if platform.system() != "Windows":
        raise RuntimeError("Brainbox vision tools require Windows")


def capture_screen(max_width: int = 1280, quality: int = 72) -> dict[str, Any]:
    """Capture the Windows desktop and return a compact image Brainbox can inspect."""
    _require_windows()
    import mss
    from PIL import Image

    max_width = max(640, min(int(max_width), 1920))
    quality = max(45, min(int(quality), 90))

    with mss.mss() as sct:
        monitor = sct.monitors[0]
        shot = sct.grab(monitor)
        image = Image.frombytes("RGB", shot.size, shot.rgb)

    if image.width > max_width:
        height = int(image.height * max_width / image.width)
        image = image.resize((max_width, height), Image.Resampling.LANCZOS)

    buf = io.BytesIO()
    image.save(buf, format="JPEG", quality=quality, optimize=True)
    encoded = base64.b64encode(buf.getvalue()).decode("ascii")
    return {
        "width": image.width,
        "height": image.height,
        "mime_type": "image/jpeg",
        "image_data_url": f"data:image/jpeg;base64,{encoded}",
        "bytes": len(buf.getvalue()),
    }


def screen_ocr(region: dict[str, int] | None = None) -> dict[str, Any]:
    """Read visible screen text using local OCR."""
    _require_windows()
    import mss
    import numpy as np
    from PIL import Image

    with mss.mss() as sct:
        monitor = sct.monitors[0]
        if region:
            monitor = {
                "left": int(region.get("left", 0)),
                "top": int(region.get("top", 0)),
                "width": int(region["width"]),
                "height": int(region["height"]),
            }
        shot = sct.grab(monitor)
        image = Image.frombytes("RGB", shot.size, shot.rgb)

    try:
        from rapidocr_onnxruntime import RapidOCR
    except ImportError as exc:
        raise RuntimeError(
            "RapidOCR is not installed. Run: pip install -e '.[vision]'"
        ) from exc

    engine = RapidOCR()
    result, _ = engine(np.asarray(image))
    items = []
    for item in result or []:
        box, text, score = item
        items.append({"text": str(text), "confidence": float(score), "box": box})
    return {"text": "\n".join(x["text"] for x in items), "items": items}


def active_window() -> dict[str, Any]:
    """Return the active Windows window title and rectangle."""
    _require_windows()
    from pywinauto import Desktop

    window = Desktop(backend="uia").get_active()
    rect = window.rectangle()
    return {
        "title": window.window_text(),
        "class_name": window.class_name(),
        "rectangle": {
            "left": rect.left,
            "top": rect.top,
            "right": rect.right,
            "bottom": rect.bottom,
        },
    }


def ui_tree(window_title: str | None = None, max_depth: int = 4) -> dict[str, Any]:
    """Inspect the accessible UI tree of the active or named Windows window."""
    _require_windows()
    from pywinauto import Desktop

    max_depth = max(1, min(int(max_depth), 8))
    desktop = Desktop(backend="uia")
    if window_title:
        window = desktop.window(title_re=window_title)
    else:
        window = desktop.get_active()

    def walk(control: Any, depth: int) -> dict[str, Any]:
        data: dict[str, Any] = {
            "control_type": control.element_info.control_type,
            "name": control.window_text(),
            "automation_id": getattr(control.element_info, "automation_id", ""),
        }
        if depth < max_depth:
            children = []
            try:
                descendants = control.children()
            except Exception:
                descendants = []
            for child in descendants[:80]:
                try:
                    children.append(walk(child, depth + 1))
                except Exception:
                    continue
            if children:
                data["children"] = children
        return data

    return walk(window, 0)


def register_vision_tools(registry: Any) -> None:
    if platform.system() != "Windows":
        return
    from .execution import ToolSpec
    from .policy import Risk

    registry.register(ToolSpec(
        name="capture_screen",
        function=capture_screen,
        risk=Risk.READ,
        description="Capture the Windows desktop. Use this when you need to visually inspect what is currently on screen.",
        input_schema={"type": "object", "properties": {
            "max_width": {"type": "integer", "minimum": 640, "maximum": 1920},
            "quality": {"type": "integer", "minimum": 45, "maximum": 90},
        }},
    ))
    registry.register(ToolSpec(
        name="screen_ocr",
        function=screen_ocr,
        risk=Risk.READ,
        description="Read visible text from the Windows screen using local OCR. Prefer this for finding text or labels.",
        input_schema={"type": "object", "properties": {
            "region": {"type": "object", "properties": {
                "left": {"type": "integer"}, "top": {"type": "integer"},
                "width": {"type": "integer"}, "height": {"type": "integer"},
            }},
        }},
    ))
    registry.register(ToolSpec(
        name="active_window",
        function=active_window,
        risk=Risk.READ,
        description="Inspect the currently focused Windows application and its screen rectangle.",
        input_schema={"type": "object", "properties": {}},
    ))
    registry.register(ToolSpec(
        name="ui_tree",
        function=ui_tree,
        risk=Risk.READ,
        description="Inspect the accessible controls of the active or named Windows window.",
        input_schema={"type": "object", "properties": {
            "window_title": {"type": "string"},
            "max_depth": {"type": "integer", "minimum": 1, "maximum": 8},
        }},
    ))
