
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import HTMLResponse, FileResponse
from pathlib import Path
import time
import html
import csv
import uuid

router = APIRouter()


def esc(v):
    return html.escape(str(v if v is not None else ""))


def getv(row, key, default=""):
    try:
        return row[key] if key in row.keys() and row[key] is not None else default
    except Exception:
        return default


def fmt_ts(main, v):
    try:
        if not v:
            return ""
        return main.dt(int(v))
    except Exception:
        return ""


def risk_level_weight(level):
    if level == "高":
        return 3
    if level == "中":
        return 2
    if level == "低":
        return 1
    return 0


def build_report_html(main, user, project, risks, pid):
    total = len(risks)
    high = sum(1 for r in risks if getv(r, "risk_level") == "高")
    mid = sum(1 for r in risks if getv(r, "risk_level") == "中")
    low = sum(1 for r in risks if getv(r, "risk_level") == "低")
    wait = sum(1 for r in risks if getv(r, "status", "待整改") == "待整改")
    doing = sum(1 for r in risks if getv(r, "status") == "整改中")
    review = sum(1 for r in risks if getv(r, "status") == "待复查")
    done = sum(1 for r in risks if getv(r, "status") == "已完成")
    reject = sum(1 for r in risks if getv(r, "status") == "已驳回")
    closed_rate = round(done / total * 100, 1) if total else 0
    score = max(0, 100 - high * 18 - mid * 9 - low * 4 - wait * 5 - reject * 6 + done * 2)
    score = min(100, score)

    stats = [
        ("安全评分", score), ("闭环率", f"{closed_rate}%"), ("总隐患数", total),
        ("高风险", high), ("中风险", mid), ("低风险", low),
        ("待整改", wait), ("整改中", doing), ("待复查", review), ("已完成", done), ("已驳回", reject),
    ]
    stat_html = "".join([f"<div class='stat'><b>{esc(v)}</b><span>{esc(k)}</span></div>" for k, v in stats])

    sorted_risks = sorted(risks, key=lambda r: (risk_level_weight(getv(r, "risk_level")), getv(r, "id", 0)), reverse=True)
    rows = ""
    for i, r in enumerate(sorted_risks, 1):
        level = getv(r, "risk_level", "中")
        status = getv(r, "status", "待整改")
        rows += f"""
        <tr>
          <td>{i}</td>
          <td>#{esc(getv(r, "id", ""))}</td>
          <td>{esc(getv(r, "risk_type", "未知隐患"))}</td>
          <td><span class="lv lv-{esc(level)}">{esc(level)}</span></td>
          <td>{esc(getv(r, "confidence", ""))}</td>
          <td>{esc(getv(r, "responsible", "未指定"))}</td>
          <td>{esc(getv(r, "deadline", "未设置"))}</td>
          <td><b>{esc(status)}</b></td>
          <td>{esc(getv(r, "advice", ""))}</td>
          <td>{esc(getv(r, "rectification_note", ""))}</td>
          <td>{esc(getv(r, "review_note", ""))}</td>
          <td>{esc(getv(r, "submitter", ""))}</td>
          <td>{esc(getv(r, "reviewer", ""))}</td>
          <td>{esc(fmt_ts(main, getv(r, "updated_at", 0)))}</td>
        </tr>
        """
    if not rows:
        rows = "<tr><td colspan='14' class='empty'>暂无隐患记录</td></tr>"

    if high > 0:
        conclusion = "当前项目存在高风险隐患，建议立即组织专项整改，并优先复查临边防护、脚手架、结构裂缝、材料堆放等关键风险点。"
    elif wait + doing + review > 0:
        conclusion = "当前项目仍存在未完全闭环隐患，建议按责任人与整改期限持续跟踪，形成整改、提交、复查、归档的闭环证据链。"
    else:
        conclusion = "当前项目隐患闭环情况较好，可继续保持日常巡检频次，并通过AI巡检记录沉淀安全管理台账。"

    report_no = f"YZTT-RPT-{pid}-{int(time.time())}"
    gen_time = time.strftime("%Y-%m-%d %H:%M:%S")

    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>云筑天瞳工程安全智能巡检报告</title>
<style>
body{{margin:0;background:#f5f7fb;color:#101828;font-family:-apple-system,BlinkMacSystemFont,"PingFang SC","Microsoft YaHei",Arial,sans-serif;}}
.wrap{{max-width:1280px;margin:0 auto;padding:34px 28px 60px;}}
.hero{{background:linear-gradient(135deg,#0f172a,#1d4ed8 58%,#38bdf8);color:white;border-radius:28px;padding:36px;box-shadow:0 24px 60px rgba(15,23,42,.22);position:relative;overflow:hidden;}}
.hero:after{{content:"";position:absolute;right:-80px;top:-80px;width:260px;height:260px;border-radius:999px;background:rgba(255,255,255,.13);}}
.hero h1{{margin:0 0 12px;font-size:36px;letter-spacing:.02em;}}
.hero p{{margin:6px 0;color:rgba(255,255,255,.86);}}
.badge{{display:inline-block;margin-top:12px;padding:8px 14px;border-radius:999px;background:rgba(255,255,255,.15);border:1px solid rgba(255,255,255,.24);}}
.section{{background:white;border:1px solid #e6ebf2;border-radius:24px;padding:24px;margin-top:22px;box-shadow:0 12px 36px rgba(16,24,40,.06);}}
.section h2{{margin:0 0 18px;font-size:22px;}}
.grid{{display:grid;grid-template-columns:repeat(3,1fr);gap:14px;}}
.item{{background:#f8fafc;border-radius:16px;padding:14px;border:1px solid #eef2f7;}}
.k{{font-size:12px;color:#667085;}}
.v{{font-size:16px;font-weight:800;margin-top:6px;}}
.stats{{display:grid;grid-template-columns:repeat(6,1fr);gap:12px;}}
.stat{{background:linear-gradient(180deg,#fff,#f8fbff);border:1px solid #e6ebf2;border-radius:18px;padding:16px;}}
.stat b{{display:block;font-size:28px;color:#0f172a;}}
.stat span{{font-size:13px;color:#667085;}}
table{{width:100%;border-collapse:collapse;font-size:13px;}}
th{{background:#f1f5f9;text-align:left;padding:12px;color:#475467;white-space:nowrap;position:sticky;top:0;}}
td{{border-bottom:1px solid #eef2f7;padding:12px;vertical-align:top;line-height:1.55;}}
.lv{{padding:4px 9px;border-radius:999px;font-weight:800;font-size:12px;white-space:nowrap;}}
.lv-高{{background:#fee2e2;color:#b91c1c;}}
.lv-中{{background:#fef3c7;color:#92400e;}}
.lv-低{{background:#dcfce7;color:#166534;}}
.notice{{background:#fff7ed;border:1px solid #fed7aa;border-radius:18px;padding:16px;color:#7c2d12;line-height:1.7;}}
.conclusion{{background:#eff6ff;border:1px solid #bfdbfe;border-radius:18px;padding:16px;color:#1e3a8a;line-height:1.8;font-weight:700;}}
.empty{{text-align:center;color:#667085;padding:28px;}}
.footer{{text-align:center;color:#98a2b3;font-size:12px;margin-top:26px;}}
.toolbar{{margin-top:16px;display:flex;gap:10px;flex-wrap:wrap;}}
.toolbar button{{border:0;border-radius:12px;padding:10px 14px;font-weight:800;cursor:pointer;background:#fff;color:#0f172a;}}
@media print{{body{{background:white}}.wrap{{padding:0}}.section,.hero{{box-shadow:none}}.toolbar{{display:none}}}}
</style>
</head>
<body>
<div class="wrap">
  <div class="hero">
    <h1>云筑天瞳工程安全智能巡检报告</h1>
    <p>报告编号：{esc(report_no)}</p>
    <p>生成时间：{esc(gen_time)}　生成用户：{esc(user.get("username", ""))}</p>
    <span class="badge">AI巡检 · 隐患闭环2.0 · 正式报告V2</span>
    <div class="toolbar"><button onclick="window.print()">打印 / 另存为 PDF</button><button onclick="location.href='/api/export/risks-v2.csv'">导出增强CSV</button></div>
  </div>

  <div class="section">
    <h2>一、项目信息</h2>
    <div class="grid">
      <div class="item"><div class="k">项目名称</div><div class="v">{esc(getv(project, "name"))}</div></div>
      <div class="item"><div class="k">项目位置</div><div class="v">{esc(getv(project, "location"))}</div></div>
      <div class="item"><div class="k">项目类型</div><div class="v">{esc(getv(project, "category"))}</div></div>
      <div class="item"><div class="k">负责人</div><div class="v">{esc(getv(project, "owner"))}</div></div>
      <div class="item"><div class="k">项目状态</div><div class="v">{esc(getv(project, "status"))}</div></div>
      <div class="item"><div class="k">项目ID</div><div class="v">{esc(pid)}</div></div>
    </div>
  </div>

  <div class="section"><h2>二、风险统计</h2><div class="stats">{stat_html}</div></div>
  <div class="section"><h2>三、AI综合研判结论</h2><div class="conclusion">{esc(conclusion)}</div></div>

  <div class="section">
    <h2>四、隐患明细与整改闭环</h2>
    <table>
      <thead><tr><th>序号</th><th>ID</th><th>隐患类型</th><th>等级</th><th>置信度</th><th>责任人</th><th>期限</th><th>状态</th><th>整改建议</th><th>整改说明</th><th>复查意见</th><th>提交人</th><th>复查人</th><th>更新时间</th></tr></thead>
      <tbody>{rows}</tbody>
    </table>
  </div>

  <div class="section"><h2>五、AI 辅助说明</h2><p>本系统综合使用 YOLO 本地目标识别、通义千问视觉辅助研判、DeepSeek AI 安全员等能力，对现场图像、巡检记录与隐患闭环数据进行辅助分析，为项目安全管理提供参考。</p></div>
  <div class="section"><h2>六、免责声明</h2><div class="notice">本报告由云筑天瞳系统基于现场图像、巡检记录与AI辅助模型自动生成，结果仅作为安全管理辅助参考，不替代具备资质的专业人员现场复核、结构鉴定与最终安全责任认定。</div></div>
  <div class="footer">云筑天瞳 · 工程安全智能巡检平台</div>
</div>
</body>
</html>"""


@router.get("/api/report-v2/{pid}")
def report_v2(pid: int, req: Request):
    from backend import main
    user = main.user_from_req(req)
    try:
        main.ensure_risk_workflow_v2_columns()
    except Exception:
        pass
    c = main.conn()
    try:
        project = c.execute("SELECT * FROM projects WHERE id=?", (pid,)).fetchone()
        if not project:
            raise HTTPException(404, "项目不存在")
        risks = c.execute("SELECT * FROM risks WHERE project_id=? ORDER BY id DESC", (pid,)).fetchall()
        html_doc = build_report_html(main, user, project, risks, pid)
        try:
            main.REPORTS.mkdir(parents=True, exist_ok=True)
            fp = main.REPORTS / f"report_v2_project_{pid}_{int(time.time())}.html"
            fp.write_text(html_doc, encoding="utf-8")
            c.execute("INSERT INTO reports(project_id,file_path,created_by,created_at) VALUES(?,?,?,?)", (pid, str(fp.relative_to(main.BASE)), user["id"], main.now()))
            c.execute("INSERT INTO logs(user_id,action,detail,created_at) VALUES(?,?,?,?)", (user["id"], "生成正式报告V2", f"项目ID {pid} 生成HTML报告", main.now()))
            c.commit()
        except Exception:
            pass
        return HTMLResponse(html_doc)
    finally:
        c.close()


@router.get("/api/export/risks-v2.csv")
def export_risks_v2(req: Request):
    from backend import main
    user = main.user_from_req(req)
    try:
        main.ensure_risk_workflow_v2_columns()
    except Exception:
        pass
    main.EXPORTS.mkdir(parents=True, exist_ok=True)
    fp = main.EXPORTS / f"risks_v2_{uuid.uuid4().hex[:8]}.csv"
    c = main.conn()
    try:
        rows = c.execute("""
            SELECT risks.*, projects.name AS project
            FROM risks LEFT JOIN projects ON projects.id=risks.project_id
            ORDER BY risks.id DESC
        """).fetchall()
        with fp.open("w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerow(["编号","项目","隐患类型","等级","置信度","状态","责任人","期限","建议","整改说明","复查意见","提交人","复查人","提交时间","复查时间","更新时间"])
            for r in rows:
                writer.writerow([
                    getv(r,"id"), getv(r,"project"), getv(r,"risk_type"), getv(r,"risk_level"), getv(r,"confidence"),
                    getv(r,"status"), getv(r,"responsible"), getv(r,"deadline"), getv(r,"advice"),
                    getv(r,"rectification_note"), getv(r,"review_note"), getv(r,"submitter"), getv(r,"reviewer"),
                    fmt_ts(main, getv(r,"submitted_at",0)), fmt_ts(main, getv(r,"reviewed_at",0)), fmt_ts(main, getv(r,"updated_at",0)),
                ])
        c.execute("INSERT INTO logs(user_id,action,detail,created_at) VALUES(?,?,?,?)", (user["id"], "导出增强隐患CSV", "risks-v2.csv", main.now()))
        c.commit()
    finally:
        c.close()
    return FileResponse(fp, filename="云筑天瞳_隐患闭环增强台账.csv")
