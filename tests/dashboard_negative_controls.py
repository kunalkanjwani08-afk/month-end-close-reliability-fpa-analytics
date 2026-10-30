"""Negative controls: re-introduce each reported defect into a TEMP COPY of the dashboard and confirm that the checks used by the QA suite
detect it (so a green QA run is meaningful). The real HTML is never modified.  Run: python tests/dashboard_negative_controls.py"""
import asyncio, json, re, tempfile
from pathlib import Path
from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "dashboard/fpa_financial_analytics_dashboard.html"
OUT = ROOT / "build/dashboard_qa/negative_controls.json"
RES = []


def lum(c):
    n = [float(x) for x in re.findall(r"[\d.]+", c)[:3]]; v = [x / 255 for x in n]; v = [x / 12.92 if x <= .03928 else ((x + .055) / 1.055) ** 2.4 for x in v]
    return .2126 * v[0] + .7152 * v[1] + .0722 * v[2]


def cr(a, b):
    la, lb = lum(a), lum(b); return (max(la, lb) + .05) / (min(la, lb) + .05)


def mutate(html, old, new, count=1):
    assert html.count(old) == count, f"mutation anchor not unique/found: {old[:60]!r} ({html.count(old)})"
    return html.replace(old, new)


async def run(browser, name, html, probe):
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "mutant.html"; p.write_text(html, encoding="utf-8")
        pg = await browser.new_page(viewport={"width": 1400, "height": 900}); await pg.goto(p.as_uri()); await pg.wait_for_function("window.__fpa")
        detected, detail = await probe(pg); await pg.close()
    RES.append({"mutant": name, "defect_detected_by_check": detected, "detail": detail}); print("DETECTED" if detected else "MISSED", "|", name, "|", detail)


async def zero_bar_probe(pg):
    await pg.evaluate("()=>__fpa.setState(x=>{x.ent=[5]})")  # US01
    await pg.evaluate("()=>document.getElementById('tab-overview').click()")
    await pg.click("#oEntRev .bar[data-k='0']", force=True)  # AE01
    st = await pg.evaluate("()=>({xf:__fpa.S().xf,n:__fpa.nInc()})")
    return (st["xf"] is not None and st["n"] == 0), f"after US01 -> AE01 click: chart selection={st['xf']}, lines in scope={st['n']}"


async def scope_probe(pg):
    await pg.select_option("#sScale", "PARSED"); tx = await pg.inner_text("#scope")
    return ("AS REPORTED" not in tx), f"header after selecting 'As reported': {tx[:110]!r}"


async def status_probe(pg):
    r = await pg.evaluate("()=>{const a=__fpa.statusTotals('SEL').Pending.n;__fpa.setState(x=>{x.gl=[0]});return [a,__fpa.statusTotals('SEL').Pending.n]}")
    return (r[0] == r[1]), f"Pending lines before/after a GL filter: {r[0]} -> {r[1]} (unchanged = GL filter ignored)"


async def palette_probe(pg):
    c = await pg.evaluate("()=>{const s=getComputedStyle(document.documentElement);return [3,4,5].map(i=>s.getPropertyValue('--s'+i).trim())}")
    hexrgb = lambda h: f"rgb({int(h[1:3],16)}, {int(h[3:5],16)}, {int(h[5:7],16)})"
    low = [(h, round(cr(hexrgb(h), 'rgb(252, 252, 251)'), 2)) for h in c if cr(hexrgb(h), 'rgb(252, 252, 251)') < 3]
    return bool(low), f"series 3-5 contrast vs card: {[(h, round(cr(hexrgb(h), 'rgb(252, 252, 251)'), 2)) for h in c]}"


async def bridge_probe(pg):
    c = await pg.evaluate("()=>__fpa.chart('oBridge')"); v = {i["label"]: i["val"] for i in c["items"]}
    gap = v["Revenue"] + v["COGS"] + v["People"] + v["Opex"] - v["Result"]
    return abs(gap) > 1, f"Revenue + steps - Result = {gap:,.0f} (should be 0)"


async def print_probe(pg):
    await pg.evaluate("()=>{window.dispatchEvent(new Event('beforeprint'));window.dispatchEvent(new Event('afterprint'))}"); await pg.wait_for_timeout(400)
    await pg.evaluate("()=>resetAll()"); op = await pg.evaluate("()=>document.querySelector('#scope details.basis').open")
    return op, f"header basis open after a print cycle and re-render: {op}"


async def main():
    html = SRC.read_text(encoding="utf-8")
    async with async_playwright() as p:
        b = await p.chromium.launch()
        await run(b, "M1 cross-filter guard removed (xfOK always true, bars never disabled)", mutate(mutate(html, "const xfOK = (dim, key) => {", "const xfOK = (dim, key) => { return true;\n"), "!(o.selected != null && it.key === o.selected) && !xfOK(xdim, it.key)", "false", 2), zero_bar_probe)
        await run(b, "M2 static header subtitle (scope text never updated)", mutate(html, "$('#scope').innerHTML = scopeHtml();", "", 2), scope_probe)
        await run(b, "M3 status table ignores the GL filter (old cube behaviour)", mutate(html, "if (G && !G.has(XG[j])) continue;", ""), status_probe)
        await run(b, "M4 old light palette (#1baf7a, #eda100, #e87ba4)", html.replace("--s3:#18996b;--s4:#b57b00;--s5:#e15489;--s6:#008300;--s7:#6250d6;--s8:#e34948;\n--pos", "--s3:#1baf7a;--s4:#eda100;--s5:#e87ba4;--s6:#008300;--s7:#6250d6;--s8:#e34948;\n--pos"), palette_probe)
        await run(b, "M5 bridge sign error (COGS step added instead of deducted)", mutate(html, "{ label: 'COGS', key: 1, val: -a.sS[1] }", "{ label: 'COGS', key: 1, val: a.sS[1] }"), bridge_probe)
        await run(b, "M6 print leaves the header basis open (toggle during print not ignored)", mutate(html, "if (!printing) basisOpen = e.target.open;", "basisOpen = e.target.open;"), print_probe)
        await b.close()
    json.dump(RES, open(OUT, "w"), indent=1)
    miss = [r for r in RES if not r["defect_detected_by_check"]]
    print(f"\n{len(RES)-len(miss)}/{len(RES)} re-introduced defects detected")
    raise SystemExit(1 if miss else 0)


asyncio.run(main())
