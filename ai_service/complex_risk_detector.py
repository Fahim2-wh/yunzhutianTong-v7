from pathlib import Path
import cv2

COMPLEX_RISK_CN = {
    "wall_crack": "墙体裂缝",
    "material_stack": "材料堆放",
    "edge_guardrail": "临边防护/护栏",
}

COMPLEX_RISK_LEVEL = {
    "wall_crack": "高风险",
    "material_stack": "中风险",
    "edge_guardrail": "低风险",
}

COMPLEX_RISK_ADVICE = {
    "wall_crack": "发现疑似墙体裂缝，建议记录裂缝位置、长度和宽度，设置观测标记；若裂缝贯穿墙体或持续发展，应由专业工程师复核。",
    "material_stack": "发现材料堆放区域，建议检查是否占用通道、是否分类码放、是否存在倾倒风险，并及时清理影响通行的材料。",
    "edge_guardrail": "识别到临边防护或护栏设施，建议现场复核其连续性、牢固性和警示标识是否完整。",
}

def detect_complex_risk(image_path, model_path="models/complex_risk.pt", conf=0.08):
    try:
        from ultralytics import YOLO
    except Exception as e:
        return {
            "engine": "complex-risk-unavailable",
            "items": [],
            "summary": "复杂风险模型不可用：" + str(e),
            "level": "低风险",
            "advice": []
        }

    image_path = Path(image_path)
    model_path = Path(model_path)

    if not model_path.exists():
        return {
            "engine": "complex-risk-missing",
            "items": [],
            "summary": "未找到 complex_risk.pt",
            "level": "低风险",
            "advice": []
        }

    model = YOLO(str(model_path))
    results = model.predict(str(image_path), conf=conf, imgsz=416, verbose=False)

    items = []
    level_rank = {"低风险": 1, "中风险": 2, "高风险": 3}
    max_level = "低风险"

    for r in results:
        names = r.names
        if r.boxes is None:
            continue

        for box in r.boxes:
            cls_id = int(box.cls[0])
            cls_name = names.get(cls_id, str(cls_id))
            score = float(box.conf[0])

            level = COMPLEX_RISK_LEVEL.get(cls_name, "低风险")
            if level_rank[level] > level_rank[max_level]:
                max_level = level

            xyxy = box.xyxy[0].tolist()
            x1, y1, x2, y2 = xyxy

            # ===== 展示稳定过滤：避免复杂风险误检 =====
            h, w = r.orig_shape

            # 1. 护栏容易把塔吊、脚手架误识别成 guardrail
            #    这里要求护栏框不能出现在天空/画面顶部，且更偏向右侧或下方临边区域
            if cls_name == "edge_guardrail":
                cx = (x1 + x2) / 2
                cy = (y1 + y2) / 2
                if cy < h * 0.28:
                    continue
                if cx < w * 0.45 and cy < h * 0.55:
                    continue
                if score < 0.18:
                    continue

            # 2. 材料堆放置信度太低时不展示，避免乱框
            if cls_name == "material_stack" and score < 0.10:
                continue

            # 3. 裂缝允许低一点，因为裂缝本来细小
            if cls_name == "wall_crack" and score < 0.08:
                continue
            # ===== 展示稳定过滤结束 =====

            items.append({
                "name": cls_name,
                "label": COMPLEX_RISK_CN.get(cls_name, cls_name),
                "confidence": round(score, 3),
                "level": level,
                "box": [round(x, 1) for x in xyxy],
                "advice": COMPLEX_RISK_ADVICE.get(cls_name, "建议现场安全员复核。")
            })

    if not items:
        return {
            "engine": "real-yolo-complex-risk",
            "items": [],
            "summary": "未识别到明显墙体裂缝、材料堆放或临边护栏目标。",
            "level": "低风险",
            "advice": ["未发现明显复杂风险，但仍建议现场安全员复核。"]
        }

    summary = "；".join([
        f'{x["label"]}({x["level"]}, 置信度{x["confidence"]})'
        for x in items[:8]
    ])

    advice = []
    for x in items:
        if x["advice"] not in advice:
            advice.append(x["advice"])

    return {
        "engine": "real-yolo-complex-risk",
        "items": items,
        "summary": summary,
        "level": max_level,
        "advice": advice
    }
