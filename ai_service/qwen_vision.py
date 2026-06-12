from pathlib import Path
import os
import json
import base64
import requests
from PIL import Image
import uuid
import cv2
import numpy as np

BASE = Path(__file__).resolve().parent.parent
ENV_PATH = BASE / ".env"
TMP_DIR = BASE / "data" / "qwen_tmp"
UPLOADS = BASE / "data" / "uploads"

TMP_DIR.mkdir(parents=True, exist_ok=True)
UPLOADS.mkdir(parents=True, exist_ok=True)


def load_env():
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


def compress_to_1024(src_path: Path) -> Path:
    src_path = Path(src_path)
    out_path = TMP_DIR / f"qwen_1024_{uuid.uuid4().hex}.jpg"

    img = Image.open(src_path).convert("RGB")
    w, h = img.size
    max_side = max(w, h)

    if max_side > 1024:
        ratio = 1024 / max_side
        img = img.resize((int(w * ratio), int(h * ratio)))

    img.save(out_path, "JPEG", quality=82, optimize=True)
    return out_path


def image_to_base64(path: Path) -> str:
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def extract_json(text: str):
    text = str(text).strip()

    if text.startswith("```"):
        text = text.replace("```json", "").replace("```", "").strip()

    start = text.find("{")
    end = text.rfind("}")

    if start != -1 and end != -1 and end > start:
        text = text[start:end + 1]

    return json.loads(text)


def call_qwen_vision(image_path: str):
    load_env()

    api_key = os.environ.get("DASHSCOPE_API_KEY", "").strip()
    model = os.environ.get("QWEN_VL_MODEL", "qwen3-vl-plus").strip()

    if not api_key:
        return {
            "ok": False,
            "message": "未配置 DASHSCOPE_API_KEY",
            "result": None
        }

    compressed_path = compress_to_1024(Path(image_path))
    img_b64 = image_to_base64(compressed_path)

    prompt = """
你是一名工地安全AI视觉审查员。请识别图片中的复杂施工安全风险，并尽量给出可标注的位置框。

重点识别：
1. 墙体裂缝、地面裂缝、结构破损
2. 材料堆放、钢筋堆放、木板堆放、杂物堆放
3. 临边防护、护栏、围挡、防坠落措施不足
4. 通道占用、现场杂乱、明显安全隐患

请只返回 JSON，不要输出任何解释。
坐标 bbox 必须使用 0-1000 的归一化坐标，格式为 [x1, y1, x2, y2]。
如果无法确定准确位置，可以给出大致区域，但不要编造不存在的风险。

返回格式：
{
  "summary": "一句话总体结论",
  "risk_level": "高/中/低",
  "objects": [
    {
      "type": "墙体/地面裂缝/材料堆放/临边防护/通道占用/其他风险",
      "level": "高/中/低",
      "confidence": 0.0,
      "bbox": [x1, y1, x2, y2],
      "description": "从图片中看到的问题",
      "advice": "整改建议"
    }
  ],
  "need_manual_review": true
}

注意：
- bbox 数值范围必须是 0 到 1000。
- 如果图片中没有明显裂缝，不要硬说有裂缝。
- 如果看不清，description 写“画面不清晰，需人工复核”。
- 最多返回 5 个风险对象。
""".strip()

    url = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"

    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{img_b64}"
                        }
                    }
                ]
            }
        ],
        "temperature": 0.2
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=90)

        if resp.status_code != 200:
            return {
                "ok": False,
                "message": f"千问调用失败，状态码：{resp.status_code}，返回：{resp.text[:500]}",
                "result": None
            }

        data = resp.json()
        content = data["choices"][0]["message"]["content"]

        if isinstance(content, list):
            content = "".join([x.get("text", "") for x in content if isinstance(x, dict)])

        result = extract_json(str(content))

        return {
            "ok": True,
            "provider": "qwen",
            "model": model,
            "message": "千问视觉辅助识别成功",
            "result": result
        }

    except Exception as e:
        return {
            "ok": False,
            "message": f"千问视觉辅助识别异常：{repr(e)}",
            "result": None
        }


def draw_qwen_annotations(image_path: str, qwen_result: dict):
    image_path = Path(image_path)
    img = cv2.imread(str(image_path))

    if img is None:
        return {
            "ok": False,
            "message": "图片读取失败",
            "annotated_path": ""
        }

    h, w = img.shape[:2]
    objects = qwen_result.get("objects", []) or []

    # 用 PIL 绘制中文，避免 OpenCV 中文乱码
    from PIL import Image, ImageDraw, ImageFont
    img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    pil_img = Image.fromarray(img_rgb)
    draw = ImageDraw.Draw(pil_img)

    # macOS 常见中文字体
    font_paths = [
        "/System/Library/Fonts/PingFang.ttc",
        "/System/Library/Fonts/STHeiti Light.ttc",
        "/System/Library/Fonts/STHeiti Medium.ttc",
        "/Library/Fonts/Arial Unicode.ttf",
    ]

    font = None
    for fp in font_paths:
        try:
            if Path(fp).exists():
                font = ImageFont.truetype(fp, 28)
                break
        except Exception:
            pass

    if font is None:
        font = ImageFont.load_default()

    color_map = {
        "高": (255, 40, 40),
        "中": (255, 190, 0),
        "低": (40, 210, 120),
    }

    short_map = {
        "地面裂缝": "地面裂缝",
        "墙体裂缝": "墙体裂缝",
        "墙体/地面裂缝": "裂缝风险",
        "材料堆放": "材料堆放",
        "临边防护": "临边防护",
        "通道占用": "通道占用",
        "其他风险": "其他风险",
    }

    for obj in objects:
        bbox = obj.get("bbox", [])

        if not isinstance(bbox, list) or len(bbox) != 4:
            continue

        try:
            x1, y1, x2, y2 = [float(v) for v in bbox]
        except Exception:
            continue

        x1 = max(0, min(1000, x1))
        y1 = max(0, min(1000, y1))
        x2 = max(0, min(1000, x2))
        y2 = max(0, min(1000, y2))

        px1 = int(x1 / 1000 * w)
        py1 = int(y1 / 1000 * h)
        px2 = int(x2 / 1000 * w)
        py2 = int(y2 / 1000 * h)

        if px2 <= px1 or py2 <= py1:
            continue

        level = obj.get("level", "中")
        color = color_map.get(level, (255, 190, 0))

        raw_label = str(obj.get("type", "AI风险"))
        label = short_map.get(raw_label, raw_label)
        conf = obj.get("confidence", 0)

        try:
            conf_text = f"{int(float(conf) * 100)}%"
        except Exception:
            conf_text = ""

        text = f"AI辅助：{label} {conf_text}"

        # 画框
        for t in range(4):
            draw.rectangle(
                [px1 - t, py1 - t, px2 + t, py2 + t],
                outline=color
            )

        # 文字背景
        try:
            text_box = draw.textbbox((0, 0), text, font=font)
            tw = text_box[2] - text_box[0]
            th = text_box[3] - text_box[1]
        except Exception:
            tw, th = 260, 32

        bg_y1 = max(0, py1 - th - 16)
        bg_y2 = py1
        bg_x2 = min(w - 1, px1 + tw + 18)

        draw.rectangle([px1, bg_y1, bg_x2, bg_y2], fill=color)
        draw.text((px1 + 8, bg_y1 + 4), text, font=font, fill=(255, 255, 255))

    out_rgb = np.array(pil_img)
    out_bgr = cv2.cvtColor(out_rgb, cv2.COLOR_RGB2BGR)

    out_path = UPLOADS / f"annotated_qwen_{uuid.uuid4().hex}.jpg"
    cv2.imwrite(str(out_path), out_bgr)

    try:
        rel = str(out_path.relative_to(BASE))
    except Exception:
        rel = str(out_path)

    return {
        "ok": True,
        "message": "千问辅助标注图生成成功",
        "annotated_path": rel
    }


def analyze_and_draw(image_path: str):
    r = call_qwen_vision(image_path)

    if not r.get("ok"):
        return r

    draw = draw_qwen_annotations(image_path, r["result"])

    r["annotated_path"] = draw.get("annotated_path", "")
    return r


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("用法：python3 ai_service/qwen_vision.py 图片路径")
        raise SystemExit(1)

    r = analyze_and_draw(sys.argv[1])
    print(json.dumps(r, ensure_ascii=False, indent=2))
