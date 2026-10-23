# Сборка index.html (страница-плакат) из REPORT_v4.md.
# Нужен пакет markdown. Стиль (CSS) берётся из существующего index.html рядом со скриптом.
# Запуск: python build_page.py REPORT_v4.md index.html
import re, sys, html as _html
import markdown
import base64, os
EMBED = True   # True: рисунки встраиваются в HTML (файл самодостаточен); False: относительные пути results_v2/
def img_src(fname):
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "results_v2", fname)
    if EMBED and os.path.exists(path):
        return "data:image/png;base64," + base64.b64encode(open(path, "rb").read()).decode("ascii")
    return "results_v2/" + fname
FIGFILES = {"fig1": "fig1_sac_isa.png", "fig9": "fig9_era5_sac_fraction.png", "fig2": "fig2_optics_tau.png", "fig5": "fig5_mass_budget.png",
            "fig6": "fig6_shear_spreading.png", "fig8": "fig8_cocip_like_spreading.png", "fig7": "fig7_substance_sedimentation.png",
            "fig11": "fig11_residence_time_conc.png", "fig10": "fig10_ground_level.png", "fig12": "fig12_payload_comparison.png", "fig13": "fig13_improve_check.png"}
import json
CALC_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "calc_blocks.json")
CALC = json.load(open(CALC_PATH, encoding="utf-8")) if os.path.exists(CALC_PATH) else {}
EXTRA_CSS = """<style>
details.calc{margin:14px 0 22px;border:2px solid var(--rule,#16140f);background:var(--paper,#f5f2ea);box-shadow:4px 4px 0 var(--rule,#16140f)}
details.calc>summary{cursor:pointer;padding:9px 14px;font-weight:700;list-style:none;background:var(--accent-soft,#f6d31c)}
details.calc>summary::-webkit-details-marker{display:none}
details.calc>summary::before{content:"▸ ";}
details.calc[open]>summary::before{content:"▾ ";}
details.calc .calc-body{padding:6px 16px 10px;font-size:.95em}
details.calc .calc-body p{margin:.55em 0}
.box.brief{border-width:3px;box-shadow:7px 7px 0 var(--accent-soft,#f6d31c)}
.box.brief p{font-size:1.05em;line-height:1.5}
p.local{border-left:6px solid var(--accent-soft,#f6d31c);padding:6px 12px;background:rgba(246,211,28,.12)}
</style>"""
def calc_html(key):
    body = markdown.markdown(CALC.get(key, "Расчёт не найден: " + key))
    return f'<details class="calc"><summary>Пошаговый расчёт для проверки ({key})</summary><div class="calc-body">{body}</div></details>'
def build_page(md_text, css):
    css = css + "\n" + EXTRA_CSS
    lines = md_text.replace("\r\n", "\n").split("\n")
    title = next(l[2:].strip() for l in lines if l.startswith("# "))
    secs, cur = [], None
    for l in lines:
        if l.startswith("## "): cur = [l[3:].strip(), []]; secs.append(cur)
        elif cur is not None: cur[1].append(l)
    figno = [0]
    def render(block):
        text = "\n".join(block)
        text = re.sub(r"^\{\{CALC:([0-9.]+)\}\}\s*$", lambda mm: "\n\n@@CALC" + mm.group(1) + "@@\n\n", text, flags=re.M)
        parts = re.split(r"^\{\{FIG:([a-z0-9]+)\|(.*?)\}\}\s*$", text, flags=re.M)
        out, i = "", 0
        while i < len(parts):
            if i % 3 == 0:
                chunk = markdown.markdown(parts[i], extensions=["tables"])
                chunk = re.sub(r"<p>@@CALC([0-9.]+)@@</p>", lambda mm: calc_html(mm.group(1)), chunk)
                chunk = re.sub(r"<p><strong>Локальный вывод\.</strong>", '<p class="local"><strong>Локальный вывод.</strong>', chunk)
                out += chunk; i += 1
            else:
                name, cap = parts[i], parts[i + 1]; i += 2
                figno[0] += 1; n = figno[0]
                out += (f'<div class="figs"><figure><img src="{img_src(FIGFILES[name])}" alt="Рис. {n}. {_html.escape(cap)}">'
                        f'<figcaption><b>Рис. {n}.</b> {cap}</figcaption></figure></div>')
        return out
    body, abstract = "", ""
    for name, block in secs:
        if name.lower().startswith("коротко"):
            abstract = f'<section class="box brief"><span class="tag">Коротко</span>{render(block)}</section>' + abstract; continue
        if name.lower().startswith("реферат"):
            abstract = abstract + f'<section class="box"><span class="tag">Реферат</span>{render(block)}</section>'; continue
        m = re.match(r"^(\d+)\.\s*(.*)$", name)
        body += f'<section class="sec"><div class="num">{m.group(1) if m else "·"}</div><h2>{m.group(2) if m else name}</h2><div class="body">{render(block)}</div></section>\n'
    return (f'<!DOCTYPE html>\n<html lang="ru">\n<head>\n<meta charset="utf-8">\n<meta name="viewport" content="width=device-width, initial-scale=1">\n'
            f'<title>{title}</title>\n{css}\n</head>\n<body>\n<main class="app">\n<header class="head">\n'
            f'<p class="eyebrow">Научный отчёт · расчёт воспроизводим двумя скриптами</p>\n<h1>{title}</h1>\n</header>\n{abstract}\n{body}'
            f'<footer class="foot">Иллюстрации встроены в страницу; исходные PNG — в папке results_v2.</footer>\n</main>\n</body>\n</html>\n')
if __name__ == "__main__":
    src, dst = sys.argv[1], sys.argv[2]
    old = open(dst, encoding="utf-8").read()
    css = old[old.find("<style"):old.find("</style>") + 8]  # только базовый стиль
    open(dst, "w", encoding="utf-8").write(build_page(open(src, encoding="utf-8").read(), css))
