/* ===== views, insights, detail table, reconciliation, app bootstrap ===== */
const UI = { trendMetric: 'rev', fcSec: 0, gpRowset: 'ALL', det: { q: '', sort: 'src', dir: 1, page: 0, size: 50 } };
const TABS = [['overview', 'Executive Overview'], ['trends', 'Trends & Performance'], ['variance', 'Budget & Variance'], ['forecast', 'Forecast & Prior-Year'], ['drivers', 'Drivers & Concentration'], ['gp', 'Gross Profit & Scenarios'], ['insights', 'Insights & Actions'], ['quality', 'Data Quality & Methodology'], ['detail', 'Detail Lines']];
const rt = name => { const t = P.ref[name]; return t.r.map(r => Object.fromEntries(t.c.map((c, i) => [c, r[i]]))); };

/* ---------- small helpers ---------- */
function tableOf(heads, rows, o = {}) {
  const num = new Set(o.num || []);
  return `<div class="tw"${o.maxH ? ` style="max-height:${o.maxH}px"` : ''}><table${o.cls ? ` class="${o.cls}"` : ''}><thead><tr>${heads.map((h, i) => `<th class="${num.has(i) ? 'r' : ''}">${h}</th>`).join('')}</tr></thead><tbody>${rows.map((r, k) => `<tr${o.rowAttr ? ' ' + o.rowAttr(k) : ''}>${r.map((c, i) => `<td class="${num.has(i) ? 'r' : ''}">${c}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`;
}
const popBadge = () => `<b>${esc(VARPOP_LBL[S.varPop])}</b>`;
function scopeText() {
  let lo = NM, hi = -1; for (let m = 0; m < NM; m++) { const a = agg(); let any = false; for (let s = 0; s < NS; s++) if (a.mN[m * NS + s]) { any = true; break; } if (any) { lo = Math.min(lo, m); hi = Math.max(hi, m); } }
  return hi < 0 ? 'no months in scope' : (lo === hi ? mLabel(lo) : mLabel(lo) + ' – ' + mLabel(hi));
}
const emptyHtml = () => `<div class="card empty"><h3>No lines match the current filters</h3><p>Widen the period, clear a selection, or reset.</p><button class="btn pri" onclick="resetAll()">Reset filters</button></div>`;
function sparse(arr, f) { return arr.map(f); }
const secsToShow = [0, 1, 2, 3, 4, 5, 6];
const metricDefs = { rev: ['Revenue', a => a.rev, (a, m) => a.mS[m * NS]], cogs: ['COGS', a => a.sS[1], (a, m) => a.mS[m * NS + 1]], ppl: ['People cost', a => a.sS[2], (a, m) => a.mS[m * NS + 2]], opx: ['Opex', a => a.sS[3], (a, m) => a.mS[m * NS + 3]], cost: ['Cost base (COGS + People + Opex)', a => a.cost, (a, m) => a.mS[m * NS + 1] + a.mS[m * NS + 2] + a.mS[m * NS + 3]], res: ['Result proxy (not EBITDA)', a => a.res, (a, m) => a.mS[m * NS] - a.mS[m * NS + 1] - a.mS[m * NS + 2] - a.mS[m * NS + 3]] };
function monthSeries(key) { const a = agg(), f = metricDefs[key][2]; return P.months.map((_, m) => f(a, m)); }
const xfEnt = it => setXf('ent', it.key, 'Entity = ' + P.ents[it.key].c);
const xfDiv = it => setXf('div', it.key, 'Division = ' + P.divs[it.key]);
const xfSec = it => setXf('sec', it.key, 'Section = ' + secName(P.secs[it.key]));
const xfGl = it => setXf('gl', it.key, 'GL = ' + P.gls[it.key].gl + ' ' + P.gls[it.key].name);
const xfM = k => setXf('m', k, 'Month = ' + mLabel(k));
xfEnt.xdim = 'ent'; xfDiv.xdim = 'div'; xfSec.xdim = 'sec'; xfGl.xdim = 'gl';
const selKey = dim => (S.xf && S.xf.dim === dim) ? S.xf.val : null;

/* ---------- scenario helpers (used by GP & Scenarios + reconciliation) ---------- */
function scenarioTotals(scale, dup, sign) {
  const e = eff(scale); let rev = 0, cost = 0, n = 0;
  for (let i = 0; i < N; i++) {
    if (!dimPass[i] || !scnPass(i, scale, dup, sign)) continue; n++;
    const s = SEC[i]; if (s === 0) rev += e.A[i]; else if (s === 1 || s === 2 || s === 3) cost += e.A[i];
  }
  return { n, rev, cost, res: rev - cost };
}
const STATUSES = ['Posted', 'Pending', 'Parked', 'Rejected', '(blank)'];
/* Non-Posted lines of the any-status population, embedded at LINE grain: statuses honour every filter and scenario. */
const XD = P.X, XN = XD.m.length;
const XSt = Int8Array.from(XD.st), XE = Int8Array.from(XD.e), XDv = Int8Array.from(XD.d), XG = Int16Array.from(XD.g), XC = Int16Array.from(XD.c), XM = Int8Array.from(XD.m);
const XRS = Int8Array.from(XD.rs), XDP = Int8Array.from(XD.dp), XSG = Int8Array.from(XD.sg), XA0 = Float64Array.from(XD.a), XSEC = Int8Array.from(XG, g => GSI[g]);
const XPAr = XA0.slice(); for (const k in P.xparsed) XPAr[+k] = P.xparsed[k];
function xEff(mode) { if (mode === 'PARSED') return XA0.map((v, i) => XRS[i] > 0 ? XPAr[i] : v); if (mode === 'HIGH') return XA0.map((v, i) => XRS[i] === 2 ? XPAr[i] : v); return XA0; }
const xEffCache = {}; const xEffC = mode => xEffCache[mode] || (xEffCache[mode] = xEff(mode));
function xScn(i, scale, dup, sign) {
  if (scale === 'EXCL_ALL' && XRS[i] > 0) return false; if (scale === 'EXCL_MED' && XRS[i] === 2) return false;
  if (dup === 'EXCL_SAME' && XDP[i] === 1) return false; if (dup === 'EXCL_ALL' && XDP[i] >= 1) return false;
  if (sign === 'NONNEG' && XSG[i] !== 0) return false; if (sign === 'EXCL_FLIP' && XSG[i] === 2) return false; return true;
}
/* Journal-status partition. mode 'SEL' = every slicer, the chart selection AND the selected scale/duplicate/sign scenarios;
   mode 'BASE' = every slicer and the chart selection but baseline scale/duplicate/sign (used by the one-at-a-time sensitivity table). */
function statusTotals(mode = 'SEL') {
  return memo('stat:' + mode, () => {
    const sc = mode === 'BASE' ? ['ADJ', 'KEEP', 'KEEP'] : [S.scale, S.dup, S.sign];
    const o = {}; STATUSES.forEach(k => o[k] = { n: 0, rev: 0, cost: 0 });
    const eA = eff(sc[0]).A, t0 = o.Posted;
    for (let i = 0; i < N; i++) {
      if (!dimPass[i] || !scnPass(i, sc[0], sc[1], sc[2])) continue;
      t0.n++; const s = SEC[i]; if (s === 0) t0.rev += eA[i]; else if (s >= 1 && s <= 3) t0.cost += eA[i];
    }
    const E = S.ent.length ? new Set(S.ent) : null, D = S.div.length ? new Set(S.div) : null, SE = S.sec.length ? new Set(S.sec) : null,
      G = S.gl.length ? new Set(S.gl) : null, C = S.cc.length ? new Set(S.cc) : null, xf = S.xf, xa = xEffC(sc[0]);
    for (let j = 0; j < XN; j++) {
      if (!MON[XM[j]]) continue;
      if (E && !E.has(XE[j])) continue; if (D && !D.has(XDv[j])) continue; if (SE && !SE.has(XSEC[j])) continue; if (G && !G.has(XG[j])) continue; if (C && !C.has(XC[j])) continue;
      if (xf) { const v = xf.val; if ((xf.dim === 'ent' && XE[j] !== v) || (xf.dim === 'div' && XDv[j] !== v) || (xf.dim === 'sec' && XSEC[j] !== v) || (xf.dim === 'gl' && XG[j] !== v) || (xf.dim === 'cc' && XC[j] !== v) || (xf.dim === 'm' && XM[j] !== v)) continue; }
      if (!xScn(j, sc[0], sc[1], sc[2])) continue;
      const t = o[STATUSES[XSt[j]]]; t.n++; const s = XSEC[j]; if (s === 0) t.rev += xa[j]; else if (s >= 1 && s <= 3) t.cost += xa[j];
    }
    return o;
  });
}
const SCOPE_STATUS = 'Honours: period, entity, division, section, GL, cost centre, chart selection and the selected scale / duplicate / sign scenarios. Not applicable: the variance-comparison population (it does not filter lines). Population: Posted lines are the dashboard population; Pending, Parked, Rejected and blank-status lines exist only in this separate all-status diagnostic (they are excluded everywhere else by provisional rule R6).';
function scenarioTable() {
  return memo('scn', () => {
    const rows = [], base = scenarioTotals('ADJ', 'KEEP', 'KEEP');
    const add = (factor, name, cls, t) => rows.push({ factor, name, cls, ...t });
    const st = statusTotals('BASE'); const sum = (...k) => k.reduce((a, s) => ({ n: a.n + st[s].n, rev: a.rev + st[s].rev, cost: a.cost + st[s].cost }), { n: 0, rev: 0, cost: 0 });
    const fin = t => ({ ...t, res: t.rev - t.cost });
    add('status', 'Posted only (baseline)', 'BASELINE', fin(sum('Posted')));
    add('status', 'All except Rejected', 'POLICY', fin(sum('Posted', 'Pending', 'Parked', '(blank)')));
    add('status', 'All statuses', 'POLICY', fin(sum(...STATUSES)));
    ['Pending', 'Parked', 'Rejected', '(blank)'].forEach(s => add('status', s + ' only', 'DIAGNOSTIC', fin(sum(s))));
    [['ADJ', 'Adjusted, all (baseline)', 'BASELINE'], ['PARSED', 'As reported (no restoration)', 'POLICY'], ['HIGH', 'Restore HIGH confidence only', 'POLICY'], ['EXCL_ALL', 'Exclude all restored rows', 'POLICY'], ['EXCL_MED', 'Exclude MEDIUM-confidence restored', 'POLICY']].forEach(([k, n, c]) => add('scale', n, c, scenarioTotals(k, 'KEEP', 'KEEP')));
    [['KEEP', 'Candidates retained (baseline)', 'BASELINE'], ['EXCL_SAME', 'Exclude same-sign candidates', 'POLICY'], ['EXCL_ALL', 'Exclude all copy candidates', 'POLICY']].forEach(([k, n, c]) => add('duplicates', n, c, scenarioTotals('ADJ', k, 'KEEP')));
    [['KEEP', 'Signs as recorded (baseline)', 'BASELINE'], ['NONNEG', 'All-non-negative rows only', 'POLICY'], ['EXCL_FLIP', 'Exclude single-column sign flips', 'POLICY']].forEach(([k, n, c]) => add('sign', n, c, scenarioTotals('ADJ', 'KEEP', k)));
    const ranges = ['status', 'scale', 'duplicates', 'sign'].map(f => {
      const r = rows.filter(x => x.factor === f && x.cls !== 'DIAGNOSTIC'), b = r.find(x => x.cls === 'BASELINE');
      const mn = k => Math.min(...r.map(x => x[k])), mx = k => Math.max(...r.map(x => x[k]));
      return { factor: f, n: r.length, revRange: b.rev ? (mx('rev') - mn('rev')) / Math.abs(b.rev) : null, resRange: b.res ? (mx('res') - mn('res')) / Math.abs(b.res) : null };
    });
    return { rows, ranges, base };
  });
}

/* ================= VIEWS ================= */
const fmtUsdS0 = v => v == null || v !== v ? 'n/a' : (v < 0 ? MINUS : '') + fmtUsd(Math.abs(v));
function monthVar(secs) { const vc = varCells(S.varPop), o = new Float64Array(NM), c = new Int32Array(NM); cellIter(vc, (e, g, m, a, b, n) => { if (secs.includes(GSI[g])) { o[m] += a - b; c[m] += n; } }); return { o, c }; }
function yoyOf(ser) { let cur = 0, pri = 0, ok = 0; for (let m = 12; m < NM; m++) if (MON[m] && MON[m - 12]) { cur += ser[m]; pri += ser[m - 12]; ok++; } return ok && pri ? { v: (cur - pri) / Math.abs(pri), ok } : null; }
const maskM = ser => ser.map((v, m) => MON[m] ? v : NaN);
const VIEWS = {};

/* ---- 1. Executive Overview ---- */
VIEWS.overview = {
  html() {
    const a = agg(), vs = varBySection(S.varPop), rv = vs[0], cv = tot(vs, COSTBASE);
    const yb = (k) => { const y = yoyOf(monthSeries(k)); return y ? `<div class="yoy" title="Change vs the same months one year earlier, over the ${y.ok} selected months that have a prior-year month in scope">${y.v >= 0 ? '&#9650;' : '&#9660;'} ${fmtPctS(y.v)} YoY &middot; ${y.ok} mo</div>` : '<div class="yoy" title="Needs the same calendar months of two consecutive years in the selected period">YoY n/a</div>'; };
    const kpi = (l, v, s1, s2, id, go, met, yy) => `<div class="kpi"><button class="kgo hide-print" data-go="${go}"${met ? ` data-m="${met}"` : ''} aria-label="${esc(l)}: open ${go === 'trends' ? 'monthly trend' : 'budget variance'} view">${go === 'trends' ? 'Trend' : 'Variance'} &rsaquo;</button><div class="kl">${l}</div><div class="kv">${v}</div>${yy || ''}<div class="ks">${s1}</div>${s2 ? `<div class="ks">${s2}</div>` : ''}<div class="spark" id="${id}"></div></div>`;
    const vsub = (t, w) => t.n ? `${fmtPctS(t.pct)} of |net budget| &middot; ${fmtInt(t.n)} lines with a budget` : 'no lines with a budget in scope';
    const ccNote = (S.cc.length || (S.xf && S.xf.dim === 'cc')) ? `<div class="note">Cost-centre filter keeps only lines carrying that code; revenue and COGS lines are partly without a cost centre, so totals for those sections shrink accordingly.</div>` : '';
    return `<div class="note info">Fixed SQL analysis findings (Insights tab) are <b>overall portfolio findings</b> and do not change with filters. Everything on this page recalculates for the current selection &mdash; scope: <b>${scopeText()}</b>, ${fmtInt(nInc)} Posted lines.</div>${ccNote}
<div class="kpis">
${kpi('Revenue', fmtUsd(a.rev), `${fmtInt(a.sN[0])} lines &middot; REVENUE section`, `Full: ${fmtUsd(a.rev, 1)}`, 'kSp0', 'trends', 'rev', yb('rev'))}
${kpi('Cost base', fmtUsd(a.cost), 'COGS + People + Opex', `COGS ${fmtUsd(a.sS[1])} &middot; People ${fmtUsd(a.sS[2])} &middot; Opex ${fmtUsd(a.sS[3])}`, 'kSp1', 'trends', 'cost', yb('cost'))}
${kpi('Result proxy', fmtUsd(a.res), 'Revenue &minus; cost base (not EBITDA)', `Proxy margin ${a.rev ? fmtPct(a.res / a.rev) : 'n/a'}`, 'kSp2', 'trends', 'res', yb('res'))}
${kpi('Revenue vs budget', fmtUsdS(rv.net), vsub(rv), `Actual ${fmtUsd(rv.act)} vs budget ${fmtUsd(rv.bud)}`, 'kSp3', 'variance')}
${kpi('Cost base vs budget', fmtUsdS(cv.net), vsub(cv), `Actual ${fmtUsd(cv.act)} vs budget ${fmtUsd(cv.bud)}`, 'kSp4', 'variance')}
</div>
<div class="note">Variance = Actual &minus; Budget, on lines that carry a budget; population: ${popBadge()}. Positive = actual above budget, negative = actual below budget &mdash; no favourable/unfavourable judgement is made (sign convention R9 unresolved).</div>
<div class="grid">
${cardHtml('oMonthly', 'Monthly revenue, cost base and result proxy', 'USD &middot; hover for values, click a point to filter to that month', 'c8')}
${cardHtml('oBridge', 'Result proxy bridge', 'Revenue less COGS, People and Opex &middot; click a step to filter to that section', 'c4')}
${cardHtml('oSec', 'Signed total by section', 'USD, signs as recorded &middot; click a bar to filter', 'c4')}
${cardHtml('oEntRev', 'Revenue by entity', 'USD &middot; click to filter', 'c4')}
${cardHtml('oEntRes', 'Result proxy by entity', 'Revenue &minus; cost base, USD', 'c4')}
${cardHtml('oDiv', 'Revenue by division', 'USD &middot; click to filter', 'c4')}
${cardHtml('oEntMgn', 'Proxy margin by entity', 'Result proxy &divide; revenue &middot; not EBITDA margin &middot; click to filter', 'c4')}
<section class="card c4"><h3>What stands out (this selection)</h3><div class="csub">Computed from the current filters &middot; observations, not conclusions</div><div id="oObs"></div></section>
<section class="card c12"><h3>Budget variance snapshot</h3><div class="csub">${popBadge()} &middot; net variance = actual &minus; budget on lines with a budget</div>${tableOf(['Section', 'Lines', 'Actual', 'Budget', 'Net variance', 'Var %', 'Gross cell var.'], [0, 1, 2, 3].map(s => { const t = vs[s]; return [secName(P.secs[s]), fmtInt(t.n), fmtUsd(t.act), fmtUsd(t.bud), fmtUsdS(t.net), t.pct == null ? '<span title="Net budget is below 50% of gross absolute budget, so a percentage is not published">n/a</span>' : fmtPctS(t.pct), fmtUsd(t.gross)]; }), { num: [1, 2, 3, 4, 5, 6] })}</section>
</div>`;
  },
  draw() {
    const a = agg(), rv = metricDefs.rev[2], labels = P.months.map((_, i) => mLabel(i));
    lineChart('oMonthly', { labels, xShort: P.months.map(m => m.slice(2)), fmt: v => fmtUsd(v), axisFmt: fmtAx, series: [{ name: 'Revenue', color: 'var(--s1)', vals: monthSeries('rev') }, { name: 'Cost base', color: 'var(--s2)', vals: monthSeries('cost') }, { name: 'Result proxy', color: 'var(--s3)', vals: monthSeries('res') }], aria: 'Monthly revenue, cost base and result proxy', onPoint: xfM });
    barChart('oSec', { items: P.secs.map((s, i) => ({ label: secName(s), key: i, val: a.sS[i] })).filter(x => a.sN[x.key]), fmt: v => fmtUsd(v), axisFmt: fmtAx, onClick: xfSec, selected: selKey('sec'), aria: 'Signed total by section' });
    barChart('oEntRev', { items: P.ents.map((e, i) => ({ label: e.c, key: i, val: a.eS[i * NS] })), fmt: v => fmtUsd(v), axisFmt: fmtAx, onClick: xfEnt, selected: selKey('ent'), aria: 'Revenue by entity' });
    barChart('oEntRes', { items: P.ents.map((e, i) => ({ label: e.c, key: i, val: a.eS[i * NS] - a.eS[i * NS + 1] - a.eS[i * NS + 2] - a.eS[i * NS + 3] })), fmt: v => fmtUsd(v), axisFmt: fmtAx, onClick: xfEnt, selected: selKey('ent'), aria: 'Result proxy by entity', color: 'var(--s3)' });
    barChart('oDiv', { items: P.divs.map((d, i) => ({ label: d, key: i, val: a.dS[i * NS] })), fmt: v => fmtUsd(v), axisFmt: fmtAx, onClick: xfDiv, selected: selKey('div'), aria: 'Revenue by division' });
    const lab = labels, ms = k => maskM(monthSeries(k));
    const sp = (id, name, vals, color, zero, aria) => sparkChart(id, { labels: lab, name, vals, color, zero, fmt: v => fmtUsdS0(v), aria, onPoint: xfM });
    sp('kSp0', 'Revenue', ms('rev'), 'var(--s1)', false, 'Monthly revenue trend'); sp('kSp1', 'Cost base', ms('cost'), 'var(--s2)', false, 'Monthly cost base trend'); sp('kSp2', 'Result proxy', ms('res'), 'var(--s3)', true, 'Monthly result proxy trend');
    { const mv = monthVar([0]), mc = monthVar(COSTBASE); sp('kSp3', 'Revenue net variance', P.months.map((_, m) => MON[m] && mv.c[m] ? mv.o[m] : NaN), 'var(--s1)', true, 'Monthly revenue net variance vs budget'); sp('kSp4', 'Cost base net variance', P.months.map((_, m) => MON[m] && mc.c[m] ? mc.o[m] : NaN), 'var(--s2)', true, 'Monthly cost base net variance vs budget'); }
    $$('#p-overview .kgo').forEach(b => b.onclick = () => { if (b.dataset.m) UI.trendMetric = b.dataset.m; S.tab = b.dataset.go; renderActive(true); try { history.replaceState(null, '', '#' + S.tab); } catch (e) { } window.scrollTo({ top: 0 }); });
    bridgeChart('oBridge', { items: [{ label: 'Revenue', key: 0, val: a.sS[0], total: true, color: 'var(--s1)' }, { label: 'COGS', key: 1, val: -a.sS[1] }, { label: 'People', key: 2, val: -a.sS[2] }, { label: 'Opex', key: 3, val: -a.sS[3] }, { label: 'Result', key: -1, val: a.res, total: true, noSel: true, color: 'var(--s3)' }], fmt: v => fmtUsdS(v), onClick: xfSec, selected: selKey('sec'), aria: 'Result proxy bridge from revenue to result proxy', h: 250 });
    barChart('oEntMgn', { items: P.ents.map((e, i) => ({ label: e.c, key: i, val: a.eS[i * NS] ? (a.eS[i * NS] - a.eS[i * NS + 1] - a.eS[i * NS + 2] - a.eS[i * NS + 3]) / a.eS[i * NS] : null })), fmt: v => fmtPct(v), axisFmt: v => fmtPct(v, 0), onClick: xfEnt, selected: selKey('ent'), aria: 'Result proxy margin by entity', color: 'var(--s3)' });
    const obs = quickObs(); $('#oObs').innerHTML = '<ul style="margin:0;padding-left:18px">' + obs.map(o => `<li style="margin-bottom:6px">${o}</li>`).join('') + '</ul>';
  }
};
function topN(arr, f, n) { return arr.slice().sort((x, y) => f(y) - f(x)).slice(0, n); }
function quickObs() {
  const a = agg(), vs = varBySection(S.varPop), out = [];
  if (a.sN[0]) { const best = topN(P.ents.map((e, i) => ({ e: e.c, v: a.eS[i * NS] })), x => x.v, 1)[0]; out.push(`<b>${best.e}</b> carries the largest revenue share: ${fmtUsd(best.v)} (${fmtPct(a.rev ? best.v / a.rev : null)} of revenue in scope).`); }
  if (vs[0].n) out.push(`Revenue is <b>${fmtUsd(Math.abs(vs[0].net))} ${vs[0].net < 0 ? 'below' : 'above'} budget</b>${vs[0].pct == null ? '' : ' (' + fmtPct(Math.abs(vs[0].pct)) + ' of net budget)'} on ${fmtInt(vs[0].n)} lines.`);
  const cv = tot(vs, COSTBASE); if (cv.n) out.push(`Cost base is <b>${fmtUsd(Math.abs(cv.net))} ${cv.net < 0 ? 'below' : 'above'} budget</b>${cv.pct == null ? '' : ' (' + fmtPct(Math.abs(cv.pct)) + ')'} on ${fmtInt(cv.n)} lines.`);
  const o = statusTotals(), all = STATUSES.reduce((s, k) => s + o[k].n, 0);
  if (all) out.push(`Posted lines are ${fmtPct(o.Posted.n / all)} of all-status lines in this selection; the other statuses are excluded by provisional rule R6 &mdash; see <i>Gross Profit &amp; Scenarios</i>.`);
  const pr = persistence().filter(t => t.persistent); out.push(`${fmtInt(pr.length)} entity &times; GL cells show a persistent one-sided deviation from budget (same-sign lines, &ge;12 months, &ge;90% one side, &ge;3%).`);
  return out;
}

/* ---- 2. Trends ---- */
VIEWS.trends = {
  html() {
    const opts = Object.keys(metricDefs).map(k => `<option value="${k}"${UI.trendMetric === k ? ' selected' : ''}>${esc(metricDefs[k][0])}</option>`).join('');
    const a = agg(), ys = YEARS.map((y, yi) => { const g = k => a.yS[yi * NS + k]; const c = g(1) + g(2) + g(3); return { y, rev: g(0), cogs: g(1), ppl: g(2), opx: g(3), cost: c, res: g(0) - c, n: a.yN[yi * NS] + a.yN[yi * NS + 1] + a.yN[yi * NS + 2] + a.yN[yi * NS + 3] }; });
    const yoy = (k) => YEARS.map((y, yi) => { if (!yi) return null; let cur = 0, pri = 0, ok = 0; for (let m = 0; m < NM; m++) if (MY[m] === y && MON[m] && MON[m - 12]) { const f = metricDefs[k][2]; cur += f(a, m); pri += f(a, m - 12); ok++; } return ok && pri ? { v: (cur - pri) / Math.abs(pri), ok } : null; });
    const rows = [['rev', 'Revenue'], ['cogs', 'COGS'], ['ppl', 'People'], ['opx', 'Opex'], ['cost', 'Cost base'], ['res', 'Result proxy']];
    const yo = Object.fromEntries(rows.map(([k]) => [k, yoy(k)]));
    const tbody = rows.map(([k, n]) => [n, ...YEARS.map((y, yi) => fmtUsd(ys[yi][k]) + (yo[k][yi] ? ` <span style="color:var(--muted)">(${fmtPctS(yo[k][yi].v)})</span>` : ''))]);
    return `<div class="note info">Trends use the current filters. <b>True year-over-year</b> compares the same calendar months of consecutive years, only where both years are in the selected period; it is separate from the dataset's own &ldquo;prior-year&rdquo; column (see Forecast &amp; Prior-Year).</div>
<div class="grid">
<section class="card c12"><div class="ctl"><div><h3>Monthly trend &mdash; selected metric</h3><div class="csub">USD, solid = selected months, dashed = same month one year earlier (shown only where both months are in scope)</div></div><div class="fg"><label for="selMetric">Metric</label><select id="selMetric">${opts}</select></div></div><div id="tMonthly"></div></section>
${cardHtml('tMargin', 'Result proxy margin by month', 'Result proxy &divide; revenue (solid) and trailing 3-month margin = &Sigma;result &divide; &Sigma;revenue over the last 3 months in scope (dashed) &middot; not EBITDA margin', 'c12')}
${cardHtml('tQtr', 'Quarterly total', 'Selected metric, USD per quarter in scope', 'c6')}
${cardHtml('tSeason', 'Seasonality: month vs average month', 'Selected metric, (month average &divide; mean of month averages) &minus; 1, over the years in scope', 'c6')}
<section class="card c7"><h3>Year summary with true year-over-year</h3><div class="csub">USD; % in brackets = change vs the same months of the previous year (shown only where aligned)</div>${tableOf(['Metric', ...YEARS], tbody, { num: YEARS.map((_, i) => i + 1) })}</section>
${cardHtml('tEnt', 'Entity trend (selected metric)', 'Monthly USD by entity', 'c5')}
</div>`;
  },
  draw() {
    $('#selMetric').onchange = e => { UI.trendMetric = e.target.value; renderActive(true); };
    const k = UI.trendMetric, ser = monthSeries(k), a = agg(), labels = P.months.map((_, i) => mLabel(i));
    const py = ser.map((v, m) => m >= 12 && MON[m] && MON[m - 12] ? ser[m - 12] : NaN);
    lineChart('tMonthly', { labels, xShort: P.months.map(m => m.slice(2)), fmt: v => fmtUsd(v), axisFmt: fmtAx, series: [{ name: metricDefs[k][0], color: 'var(--s1)', vals: ser.map((v, m) => MON[m] ? v : NaN) }, { name: 'Same month, prior year', color: 'var(--s2)', dash: true, vals: py }], aria: 'Monthly trend', onPoint: xfM, h: 270 });
    { const rv = maskM(monthSeries('rev')), rs = maskM(monthSeries('res')), mg = rv.map((v, m) => v === v && v ? rs[m] / v : NaN), r3 = rv.map((v, m) => { if (m < 2) return NaN; const r = rv[m] + rv[m - 1] + rv[m - 2], q = rs[m] + rs[m - 1] + rs[m - 2]; return r === r && r ? q / r : NaN; });
      lineChart('tMargin', { labels, xShort: P.months.map(m => m.slice(2)), fmt: v => fmtPct(v), axisFmt: v => fmtPct(v, 0), series: [{ name: 'Monthly proxy margin', color: 'var(--s3)', vals: mg }, { name: 'Trailing 3-month', color: 'var(--s7)', dash: true, vals: r3 }], aria: 'Result proxy margin by month', onPoint: xfM, h: 240 }); }
    const qs = []; YEARS.forEach(y => [1, 2, 3, 4].forEach(q => { let s = 0, any = false; for (let m = 0; m < NM; m++) if (MY[m] === y && MQ[m] === q && MON[m]) { s += ser[m]; any = true; } if (any) qs.push({ label: `Q${q} ${y}`, short: `Q${q} ${String(y).slice(2)}`, key: y * 10 + q, val: s }); }));
    barChart('tQtr', { items: qs, horizontal: false, fmt: v => fmtUsd(v), axisFmt: fmtAx, aria: 'Quarterly total', h: 230 });
    const cm = Array.from({ length: 12 }, () => ({ s: 0, n: 0 })); for (let m = 0; m < NM; m++) if (MON[m]) { cm[m % 12].s += ser[m]; cm[m % 12].n++; }
    const av = cm.map(x => x.n ? x.s / x.n : null), have = av.filter(x => x != null), mean = have.length ? have.reduce((s, x) => s + x, 0) / have.length : 0;
    barChart('tSeason', { items: av.map((v, i) => ({ label: MN[i], key: i, val: v == null || !mean ? null : v / mean - 1 })).filter(x => x.val != null), horizontal: false, fmt: v => fmtPctS(v), signColors: false, aria: 'Seasonality index', h: 230 });
    /* entity x month needs its own pass */
    const em = P.ents.map(() => new Float64Array(NM)), ec = P.ents.map(() => new Int32Array(NM));
    for (let i = 0; i < N; i++) { if (!inc[i]) continue; const s = SEC[i]; const sign = k === 'res' ? (s === 0 ? 1 : (s >= 1 && s <= 3 ? -1 : 0)) : 1; let w = 0; if (k === 'rev') w = s === 0 ? 1 : 0; else if (k === 'cogs') w = s === 1 ? 1 : 0; else if (k === 'ppl') w = s === 2 ? 1 : 0; else if (k === 'opx') w = s === 3 ? 1 : 0; else if (k === 'cost') w = s >= 1 && s <= 3 ? 1 : 0; else w = sign; if (w) { em[Ei[i]][Mi[i]] += w * EA[i]; ec[Ei[i]][Mi[i]]++; } }
    lineChart('tEnt', { labels, xShort: P.months.map(m => m.slice(2)), fmt: v => fmtUsd(v), axisFmt: fmtAx, series: P.ents.map((e, ei) => ({ name: e.c, color: SERCOL(ei), vals: Array.from(em[ei], (v, m) => MON[m] ? v : NaN) })), aria: 'Entity trend', h: 250 });
  }
};

/* ---- 3. Budget & Variance ---- */
VIEWS.variance = {
  html() {
    const vs = varBySection(S.varPop);
    const secRows = [0, 1, 2, 3, 4, 5, 6].filter(s => vs[s].n).map(s => { const t = vs[s]; return [secName(P.secs[s]), fmtInt(t.n), fmtUsd(t.act), fmtUsd(t.bud), fmtUsdS(t.net), t.pct == null ? 'n/a' : fmtPctS(t.pct), fmtUsd(t.gross), t.grossPct == null ? 'n/a' : fmtPct(t.grossPct), t.netting == null ? 'n/a' : fmtPct(t.netting, 0)]; });
    const pops = ['ALL', 'SAME', 'OPP', 'ZERO'].map(p => { const v = varBySection(p), r = v[0], c = tot(v, COSTBASE); return [VARPOP_LBL[p], fmtInt(r.n), fmtUsdS(r.net), r.pct == null ? 'n/a' : fmtPctS(r.pct), fmtInt(c.n), fmtUsdS(c.net), c.pct == null ? 'n/a' : fmtPctS(c.pct)]; });
    const pers = persistence(), pp = pers.filter(t => t.persistent), ref5 = rt('f5_persistent_cells'), refP = ref5.filter(r => r.dominant_direction_share >= 0.9 && r.variance_pct != null && Math.abs(r.variance_pct) >= 0.03);
    const ppTop = topN(pp, t => Math.abs(t.v), 15);
    return `<div class="note info">Population: ${popBadge()} (change under &ldquo;Variance population&rdquo; in the filter bar). Variance = Actual &minus; Budget; percentage = variance &divide; |net budget|, <b>published only when |net budget| &ge; 50% of the gross absolute budget</b>, otherwise n/a. <b>Net</b> variance can hide offsetting cells, so <b>gross</b> cell variance (&Sigma;|entity &times; GL &times; month variance|) is shown beside it.</div>
<div class="grid">
<section class="card c12"><h3>Variance by section &mdash; net vs gross</h3><div class="csub">Gross % = gross cell variance &divide; &Sigma;|cell budget|; Netting = |net budget| &divide; &Sigma;|cell budget| (low = budget lines offset each other)</div>${tableOf(['Section', 'Lines', 'Actual', 'Budget', 'Net variance', 'Var %', 'Gross cell variance', 'Gross % of |budget|', 'Netting'], secRows, { num: [1, 2, 3, 4, 5, 6, 7, 8] })}</section>
${cardHtml('vRev', 'Revenue: monthly net variance', 'Actual &minus; budget, USD &middot; blue = actual above budget, orange = actual below budget', 'c6')}
${cardHtml('vCost', 'Cost base: monthly net variance', 'COGS + People + Opex, actual &minus; budget, USD', 'c6')}
${cardHtml('vCum', 'Cumulative net variance vs budget', 'Running total of monthly actual &minus; budget over the months in scope &middot; shows whether a gap is one-off or building up &middot; click a point to filter to that month', 'c12')}
<section class="card c7"><h3>Sensitivity to sign population</h3><div class="csub">Same filters, four sign populations of the budget-bearing lines &mdash; shows how much of the variance sits on lines whose actual and budget signs disagree</div>${tableOf(['Population', 'Rev. lines', 'Rev. net var.', 'Rev. %', 'Cost lines', 'Cost net var.', 'Cost %'], pops, { num: [1, 2, 3, 4, 5, 6] })}</section>
<section class="card c5"><h3>Entity &times; section: variance %</h3><div class="csub">Click a row to filter to that entity. n/a = percentage not publishable</div><div id="vHeat"></div></section>
<section class="card c12"><h3>Largest entity &times; GL variances</h3><div class="csub">Top 10 by |net variance| over the selected months &middot; click a row to filter to that GL account</div><div id="vTop"></div></section>
<section class="card c12"><h3>Persistent one-sided deviations <span class="pill dyn">filter-dependent</span></h3><div class="csub">Rule (SQL analysis F5): same-sign lines, entity &times; GL cells with &ge;12 months in scope, actual on the same side of budget in &ge;90% of those months and |variance %| &ge;3%. Persistence is a reason to investigate, not a cause.</div>
<div style="margin-bottom:8px"><b>${fmtInt(pp.length)}</b> of ${fmtInt(pers.length)} cells with &ge;12 months meet the rule in this selection. <span class="pill fixed">Overall portfolio (fixed, SQL analysis F5, all 36 months)</span> ${fmtInt(refP.length)} of ${fmtInt(ref5.length)} cells.</div>
${pp.length ? tableOf(['Entity', 'GL', 'Account', 'Months', 'Above / below', 'Dominant side %', 'Net variance', 'Var %'], ppTop.map(t => [P.ents[t.e].c, P.gls[t.g].gl, esc(P.gls[t.g].name), t.months, t.above + ' / ' + t.below, fmtPct(t.share, 0), fmtUsdS(t.v), fmtPctS(t.pct)]), { num: [3, 4, 5, 6, 7], maxH: 340 }) : '<div class="empty" style="padding:14px">No cell meets the rule in this selection (needs &ge;12 months in scope).</div>'}</section>
<section class="card c12"><h3>Sign-category profile (budget-bearing lines)</h3><div class="csub">Where actual and budget have opposite signs the variance is dominated by sign handling, not by performance &mdash; whether those lines are defects or legitimate entries is unresolved (R9)</div><div id="vSign"></div></section>
</div>`;
  },
  draw() {
    const vc = varCells(S.varPop), mv = monthVar;
    const mk = (id, secs) => { const { o, c } = mv(secs); barChart(id, { items: P.months.map((m, i) => ({ label: mLabel(i), short: m.slice(2), key: i, val: MON[i] && c[i] ? o[i] : null })).filter(x => x.val != null), horizontal: false, signColors: true, fmt: v => fmtUsdS(v), axisFmt: fmtAx, onClick: it => xfM(it.key), xdim: 'm', selected: selKey('m'), aria: 'Monthly net variance', h: 230 }); };
    mk('vRev', [0]); mk('vCost', COSTBASE);
    { const cum = secs => { const { o, c } = mv(secs); let run = 0; return P.months.map((_, m) => { if (!MON[m]) return NaN; if (c[m]) run += o[m]; return c[m] ? run : NaN; }); };
      lineChart('vCum', { labels: P.months.map((_, i) => mLabel(i)), xShort: P.months.map(m => m.slice(2)), fmt: v => fmtUsdS(v), axisFmt: fmtAx, series: [{ name: 'Revenue (cumulative net variance)', color: 'var(--s1)', vals: cum([0]) }, { name: 'Cost base (cumulative net variance)', color: 'var(--s2)', vals: cum(COSTBASE) }], aria: 'Cumulative net variance versus budget', onPoint: xfM, h: 250 }); }
    /* heat: entity x [rev,cogs,ppl,opx] */
    const cell = P.ents.map(() => [0, 1, 2, 3].map(() => ({ net: 0, bud: 0, absBud: 0, n: 0 })));
    cellIter(vc, (e, g, m, a, b, n) => { const s = GSI[g]; if (s > 3) return; const t = cell[e][s]; t.net += a - b; t.bud += b; t.absBud += Math.abs(b); t.n += n; });
    const col = p => { if (p == null) return ''; const v = Math.max(-0.1, Math.min(0.1, p)) / 0.1; const c = v < 0 ? 'var(--neg)' : 'var(--pos)'; return `background:color-mix(in srgb, ${c} ${Math.round(Math.abs(v) * 45)}%, transparent)`; };
    $('#vHeat').innerHTML = `<div class="tw"><table class="heat"><thead><tr><th>Entity</th>${[0, 1, 2, 3].map(s => `<th class="r">${secName(P.secs[s])}</th>`).join('')}</tr></thead><tbody>${P.ents.map((e, ei) => `<tr class="clk" data-e="${ei}"><td>${e.c}</td>${cell[ei].map(t => { const p = t.n ? safePct(t.net, t.bud, t.absBud) : null; return `<td style="${col(p)}" title="${t.n ? fmtInt(t.n) + ' lines, net ' + fmtUsdS(t.net) : 'no lines'}">${t.n ? (p == null ? 'n/a' : fmtPctS(p)) : '–'}</td>`; }).join('')}</tr>`).join('')}</tbody></table></div><div class="legend"><span><span class="sw" style="background:var(--pos)"></span>actual above budget</span><span><span class="sw" style="background:var(--neg)"></span>actual below budget</span><span>shade saturates at ±10%</span></div>`;
    $$('#vHeat tr.clk').forEach(r => r.onclick = () => xfEnt({ key: +r.dataset.e }));
    /* top cells */
    const cells = {}; cellIter(vc, (e, g, m, a, b, n) => { const k = e * NG + g; const t = cells[k] || (cells[k] = { e, g, a: 0, b: 0, abs: 0, n: 0, months: 0 }); t.a += a; t.b += b; t.abs += Math.abs(b); t.n += n; t.months++; });
    const top = topN(Object.values(cells), t => Math.abs(t.a - t.b), 10);
    $('#vTop').innerHTML = top.length ? tableOf(['Entity', 'GL', 'Account', 'Section', 'Months', 'Actual', 'Budget', 'Net variance', 'Var %'], top.map(t => [P.ents[t.e].c, P.gls[t.g].gl, esc(P.gls[t.g].name), secName(P.gls[t.g].sec), t.months, fmtUsd(t.a), fmtUsd(t.b), fmtUsdS(t.a - t.b), fmtPctS(safePct(t.a - t.b, t.b, t.abs))]), { num: [4, 5, 6, 7, 8], rowAttr: k => `class="clk" data-g="${top[k].g}"` }) : '<div class="empty">No budget-bearing lines in this selection.</div>';
    $$('#vTop tr.clk').forEach(r => r.onclick = () => xfGl({ key: +r.dataset.g }));
    /* sign categories */
    const cats = [['SAME', 'Same sign'], ['OPP', 'Opposite sign'], ['ZERO', 'Zero involved']], bySc = cats.map(() => ({ n: 0, net: 0, absNet: 0, absA: 0 }));
    let allN = 0; for (let i = 0; i < N; i++) { if (!inc[i] || EB[i] !== EB[i]) continue; const c = SAB[i]; if (c > 2) continue; const v = EA[i] - EB[i]; const t = bySc[c]; t.n++; t.net += v; t.absNet += Math.abs(v); t.absA += Math.abs(EA[i]); allN++; }
    const tAbs = bySc.reduce((s, t) => s + t.absNet, 0);
    $('#vSign').innerHTML = tableOf(['Sign category (actual vs budget)', 'Lines', '% of lines', 'Net variance', '|Variance| at line level', '% of line-level |variance|'], cats.map((c, i) => [c[1], fmtInt(bySc[i].n), allN ? fmtPct(bySc[i].n / allN) : 'n/a', fmtUsdS(bySc[i].net), fmtUsd(bySc[i].absNet), tAbs ? fmtPct(bySc[i].absNet / tAbs) : 'n/a']), { num: [1, 2, 3, 4, 5] });
  }
};

/* ---- 4. Forecast & Prior-Year ---- */
VIEWS.forecast = {
  html() {
    const f = fcPops(), pyA = pyAgg(S.varPop), secOpts = secsToShow.map(s => `<option value="${s}"${UI.fcSec === s ? ' selected' : ''}>${secName(P.secs[s])}</option>`).join('');
    const w = (t, k) => t.absA ? t[k] / t.absA : null;
    const rows = secsToShow.map(s => { const A = f.A[s], B = f.B[s], C = f.C[s]; return [secName(P.secs[s]), fmtInt(A.n), fmtPct(w(A, 'errF'), 2), fmtPct(w(A, 'errB'), 2), fmtInt(B.n), fmtPct(w(B, 'errF'), 2), fmtPct(w(B, 'errB'), 2), fmtInt(C.n), fmtPct(w(C, 'errF'), 2), fmtPctS(w(C, 'signedF'), 2)]; });
    const attr = secsToShow.map(s => { const c = f.cat[s], tn = c.reduce((a, x) => a + x.n, 0), te = c.reduce((a, x) => a + x.abs, 0); return [secName(P.secs[s]), fmtInt(tn), tn ? fmtPct(c[1].n / tn) : 'n/a', te ? fmtPct(c[1].abs / te) : 'n/a', tn ? fmtPct(c[2].n / tn) : 'n/a', te ? fmtPct(c[2].abs / te) : 'n/a']; });
    const pyRows = []; YEARS.forEach(y => secsToShow.slice(0, 4).forEach(s => { const t = pyA[y + '|' + s]; if (t) pyRows.push([y, secName(P.secs[s]), fmtInt(t.n), fmtUsd(t.act), fmtUsd(t.py), fmtUsdS(t.act - t.py), fmtPctS(safePct(t.act - t.py, t.py, t.absPy))]); }));
    return `<div class="note">The forecast column carries <b>no version or as-of date</b>, so it cannot be established that it was prepared before the actuals. These figures describe how close the forecast and budget columns are to actuals; <b>no forecast-skill claim is made</b>.</div>
<div class="note info">Three populations are shown separately and never mixed: <b>A &mdash; matched same-sign</b> (budget and forecast present, actual&ndash;budget and actual&ndash;forecast same sign); <b>B &mdash; comparable</b> (budget and forecast present, any sign; same lines for both measures); <b>C &mdash; all lines with a forecast</b> (no budget comparison). WAPE = &Sigma;|forecast&minus;actual| &divide; &Sigma;|actual|; bias = &Sigma;(forecast&minus;actual) &divide; &Sigma;|actual|.</div>
<div class="grid">
<section class="card c12"><h3>Forecast and budget accuracy by population</h3><div class="csub">Current filters. Sample sizes are lines; a lower WAPE means a closer column, nothing more.</div>${tableOf(['Section', 'A lines', 'A WAPE fcst', 'A WAPE budget', 'B lines', 'B WAPE fcst', 'B WAPE budget', 'C lines', 'C WAPE fcst', 'C bias fcst'], rows, { num: [1, 2, 3, 4, 5, 6, 7, 8, 9] })}</section>
<section class="card c7"><div class="ctl"><div><h3>WAPE by quarter &mdash; population B</h3><div class="csub">Forecast vs budget, same lines for both</div></div><div class="fg"><label for="selFc">Section</label><select id="selFc">${secOpts}</select></div></div><div id="fQtr"></div></section>
<section class="card c5"><h3>Where the forecast error sits (population C)</h3><div class="csub">Share of lines and of absolute forecast error on lines whose forecast and actual have opposite signs (or a zero). An association in this extract; no cause is established.</div>${tableOf(['Section', 'Lines', 'Opp. sign % lines', 'Opp. sign % |error|', 'Zero % lines', 'Zero % |error|'], attr, { num: [1, 2, 3, 4, 5] })}</section>
<section class="card c12"><h3>Actual vs the dataset's prior-year <i>column</i></h3><div class="csub">Population: ${popBadge()} (sign category of actual vs prior-year column). The column is not necessarily last year's actual &mdash; compare with true year-over-year on the Trends tab.</div>${pyRows.length ? tableOf(['Year', 'Section', 'Lines', 'Actual', 'Prior-year column', 'Change', 'Change %'], pyRows, { num: [2, 3, 4, 5, 6], maxH: 360 }) : '<div class="empty">No lines with a prior-year value in this selection.</div>'}</section>
</div>`;
  },
  draw() {
    $('#selFc').onchange = e => { UI.fcSec = +e.target.value; renderActive(true); };
    const f = fcPops(), keys = []; YEARS.forEach(y => [1, 2, 3, 4].forEach(q => keys.push(y + 'Q' + q)));
    const have = keys.filter(k => f.q[UI.fcSec + '|' + k]);
    lineChart('fQtr', { labels: have, fmt: v => fmtPct(v, 1), series: [{ name: 'Forecast WAPE', color: 'var(--s1)', vals: have.map(k => { const q = f.q[UI.fcSec + '|' + k]; return q.absA ? q.errF / q.absA : NaN; }) }, { name: 'Budget WAPE', color: 'var(--s2)', vals: have.map(k => { const q = f.q[UI.fcSec + '|' + k]; return q.absA ? q.errB / q.absA : NaN; }) }], aria: 'WAPE by quarter', h: 250 });
  }
};

/* ---- 5. Drivers & Concentration ---- */
function costAbs() {
  return memo('costAbs', () => {
    const o = { ent: new Float64Array(NE), div: new Float64Array(ND), gl: new Float64Array(NG), cc: new Float64Array(NC + 1), ccN: 0, tot: 0 };
    for (let i = 0; i < N; i++) { if (!inc[i]) continue; const s = SEC[i]; if (s < 1 || s > 4) continue; const a = Math.abs(EA[i]); o.ent[Ei[i]] += a; o.div[Di[i]] += a; o.gl[Gi[i]] += a; o.tot += a; if (s === 2 || s === 3) o.cc[Ci[i] + 1] += a; }
    return o;
  });
}
function concentration(vals, names) {
  const items = vals.map((v, i) => ({ name: names[i], v })).filter(x => x.v > 0).sort((a, b) => b.v - a.v || (a.name < b.name ? -1 : 1)), tot = items.reduce((s, x) => s + x.v, 0);
  if (!tot) return null; const sh = items.map(x => x.v / tot);
  return { members: items.length, top1: sh[0], top1m: items[0].name, top3: sh.slice(0, 3).reduce((s, x) => s + x, 0), hhi: sh.reduce((s, x) => s + x * x, 0), eq: 1 / items.length };
}
VIEWS.drivers = {
  html() {
    const c = costAbs(), a = agg();
    const conc = [['Legal entity (COGS+People+Opex+D&A)', concentration(Array.from(c.ent), P.ents.map(e => e.c))], ['Division (same population)', concentration(Array.from(c.div), P.divs)], ['GL account (same population)', concentration(Array.from(c.gl), P.gls.map(g => String(g.gl)))], ['Cost centre (People + Opex)', concentration(Array.from(c.cc), ['(blank)'].concat(P.ccs))]]
      .map(([n, x]) => x ? [n, x.members, x.top1m + ' · ' + fmtPct(x.top1), fmtPct(x.top3), x.hhi.toFixed(3), x.eq.toFixed(3), x.hhi > x.eq * 1.25 ? 'above equal-share benchmark' : 'near equal-share'] : [n, 0, 'n/a', 'n/a', 'n/a', 'n/a', 'n/a']);
    const gl = P.gls.map((g, i) => ({ i, g, v: c.gl[i] })).filter(x => x.v > 0 && GSI[x.i] >= 1 && GSI[x.i] <= 4).sort((x, y) => y.v - x.v);
    let cum = 0; const pareto = gl.map((x, k) => { cum += x.v; return [k + 1, x.g.gl, esc(x.g.name), secName(x.g.sec), fmtUsd(x.v), fmtPct(c.tot ? x.v / c.tot : null), fmtPct(c.tot ? cum / c.tot : null)]; });
    const mix = YEARS.map((y, yi) => { const t = [1, 2, 3, 4].map(s => a.yA[yi * NS + s]), s = t.reduce((p, q) => p + q, 0), r = a.yA[yi * NS]; return [y, ...t.map(v => s ? fmtPct(v / s) : 'n/a'), fmtUsd(s), r ? fmtPct(t[0] / r) : 'n/a', r ? fmtPct(t[1] / r) : 'n/a', r ? fmtPct(t[2] / r) : 'n/a']; });
    const dimRows = (dim, names, cnt, key) => names.map((nm, i) => { const rev = a[key][i * NS], cost = a[key][i * NS + 1] + a[key][i * NS + 2] + a[key][i * NS + 3]; return { nm, i, rev, cost, res: rev - cost }; });
    const er = dimRows('ent', P.ents.map(e => e.c), NE, 'eS'), dr = dimRows('div', P.divs, ND, 'dS');
    const fn = (r, attr) => tableOf(['Member', 'Revenue', 'Cost base', 'Result proxy', 'Proxy margin', '% of revenue'], r.map(x => [x.nm, fmtUsd(x.rev), fmtUsd(x.cost), fmtUsd(x.res), x.rev ? fmtPct(x.res / x.rev) : 'n/a', a.rev ? fmtPct(x.rev / a.rev) : 'n/a']), { num: [1, 2, 3, 4, 5], rowAttr: k => `class="clk" data-${attr}="${r[k].i}"` });
    return `<div class="note info">Cost population for the Pareto and concentration: COGS, People, Opex and D&amp;A on <b>absolute</b> amounts (SQL analysis convention), current filters. Concentration is read against the equal-share benchmark 1/N.</div>
<div class="grid">
${cardHtml('dPareto', 'Cost by GL account (Pareto)', 'Absolute USD &middot; click a bar to filter to that GL', 'c6')}
<section class="card c6"><h3>Ranked cost accounts</h3><div class="csub">Share and cumulative share of the cost population</div>${tableOf(['#', 'GL', 'Account', 'Section', 'Abs. USD', 'Share', 'Cumulative'], pareto, { num: [0, 4, 5, 6], maxH: 330 })}</section>
<section class="card c12"><h3>Concentration</h3><div class="csub">Top-1 / top-3 share and Herfindahl index (HHI)</div>${tableOf(['Dimension', 'Members', 'Top-1 member &middot; share', 'Top-3 share', 'HHI', '1/N benchmark', 'Reading'], conc, { num: [1, 3, 4, 5] })}</section>
<section class="card c12"><h3>Cost mix and cost-to-revenue by year</h3><div class="csub">Section share of the cost population; ratios use absolute amounts</div>${tableOf(['Year', 'COGS', 'People', 'Opex', 'D&A', 'Cost pop.', 'COGS/Rev', 'People/Rev', 'Opex/Rev'], mix, { num: [1, 2, 3, 4, 5, 6, 7, 8] })}</section>
<section class="card c6"><h3>Entity contribution</h3><div class="csub">Click a row to filter</div>${fn(er, 'e')}</section>
<section class="card c6"><h3>Division contribution</h3><div class="csub">Click a row to filter</div>${fn(dr, 'd')}</section>
${cardHtml('dCc', 'Cost centre (People + Opex), absolute USD', 'Lines without a cost centre are shown as (blank)', 'c6')}
<section class="card c6"><h3>Salary per FTE (GL 6100)</h3><div class="csub">Median |amount| &divide; headcount FTE by entity and year, and the share of lines within 0.5% of the entity median</div><div id="dSal"></div></section>
</div>`;
  },
  draw() {
    const c = costAbs();
    const gl = P.gls.map((g, i) => ({ label: g.gl + ' ' + g.name, key: i, val: c.gl[i] })).filter(x => x.val > 0 && GSI[x.key] >= 1 && GSI[x.key] <= 4).sort((a, b) => b.val - a.val);
    barChart('dPareto', { items: gl, fmt: v => fmtUsd(v), axisFmt: fmtAx, onClick: xfGl, selected: selKey('gl'), aria: 'Cost by GL', rowH: 24 });
    $$('#p-drivers tr.clk[data-e]').forEach(r => r.onclick = () => xfEnt({ key: +r.dataset.e }));
    $$('#p-drivers tr.clk[data-d]').forEach(r => r.onclick = () => xfDiv({ key: +r.dataset.d }));
    barChart('dCc', { items: Array.from(c.cc).map((v, i) => ({ label: i ? P.ccs[i - 1] : '(blank)', key: i - 1, val: v })).filter(x => x.val > 0).sort((a, b) => b.val - a.val), fmt: v => fmtUsd(v), axisFmt: fmtAx, xdim: 'cc', onClick: it => setXf('cc', it.key, 'Cost centre = ' + (it.key < 0 ? '(none)' : P.ccs[it.key])), selected: selKey('cc'), aria: 'Cost centre' });
    /* salary per FTE */
    const per = {}, byEnt = P.ents.map(() => []);
    for (const k in P.hc) { const i = +k; if (!inc[i]) continue; const v = Math.abs(EA[i]) / P.hc[k]; byEnt[Ei[i]].push(v); (per[Ei[i] + '|' + MY[Mi[i]]] || (per[Ei[i] + '|' + MY[Mi[i]]] = [])).push(v); }
    const med = a => { if (!a.length) return null; const s = a.slice().sort((x, y) => x - y), m = s.length >> 1; return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2; };
    const rows = []; let within = 0, totl = 0;
    P.ents.forEach((e, ei) => { const em = med(byEnt[ei]); YEARS.forEach(y => { const a = per[ei + '|' + y]; if (!a) return; const w = a.filter(v => Math.abs(v / em - 1) <= 0.005).length; within += w; totl += a.length; rows.push([e.c, y, a.length, '$' + med(a).toFixed(0), fmtPct(w / a.length)]); }); });
    $('#dSal').innerHTML = rows.length ? tableOf(['Entity', 'Year', 'Lines', 'Median $/FTE', 'Within 0.5% of entity median'], rows, { num: [2, 3, 4], maxH: 300 }) + `<p style="margin:8px 0 0">Overall: <b>${fmtPct(totl ? within / totl : null)}</b> of ${fmtInt(totl)} lines sit within 0.5% of their entity median rate. <i>Hypothesis, not a finding:</i> a near-constant rate looks like a standard or allocated rate rather than observed payroll; without a budgeted FTE plan the people-cost variance cannot be split into rate and volume.</p>` : '<div class="empty">No salary lines with headcount in this selection.</div>';
  }
};

/* ---- 6. Gross Profit & Scenarios ---- */
VIEWS.gp = {
  html() {
    const g = gpAgg(UI.gpRowset), sc = scenarioTable(), ref = UI.gpRowset;
    const gpRows = GP_T.map((t, k) => { const x = g[k], gp = x.rev - x.cogs; return [`<b>${t.name}</b><div style="color:var(--muted);font-size:11.5px;white-space:normal">${t.rule}</div>`, fmtUsd(x.rev), fmtUsd(x.cogs), fmtUsd(gp), x.rev ? fmtPct(gp / x.rev) : 'n/a']; });
    const vbRows = GP_T.map((t, k) => { const v = g[k].vb, aG = v.aRev - v.aCogs, bG = v.bRev - v.bCogs, rEff = v.aRev - v.bRev, cEff = -(v.aCogs - v.bCogs); return [t.name, fmtUsd(aG), fmtUsd(bG), fmtUsdS(aG - bG), v.aRev ? fmtPct(aG / v.aRev) : 'n/a', v.bRev ? fmtPct(bG / v.bRev) : 'n/a', fmtUsdS(rEff), fmtUsdS(cEff), fmtInt(v.n)]; });
    const stNote = '<div class="note info">Status rows apply period, entity, division, section, GL, cost-centre and chart filters at line level, with baseline scale / duplicate / sign settings (the scenario selectors are deliberately not applied here: every row changes <b>one</b> assumption from the baseline). Scale, duplicate and sign rows apply the same dimension filters.</div>';
    const label = { status: 'Journal status', scale: 'Reporting scale', duplicates: 'Duplicate candidates', sign: 'Sign handling' };
    const base = fac => sc.rows.find(x => x.factor === fac && x.cls === 'BASELINE');
    const srows = sc.rows.map(r => { const b = base(r.factor), dr = r.rev - b.rev, dres = r.res - b.res; return [label[r.factor], esc(r.name), `<span class="pill">${r.cls}</span>`, fmtInt(r.n), fmtUsd(r.rev), fmtUsd(r.cost), fmtUsd(r.res), r.cls === 'BASELINE' ? '–' : fmtUsdS(dr) + (b.rev ? ' (' + fmtPctS(dr / Math.abs(b.rev)) + ')' : ''), r.cls === 'BASELINE' ? '–' : fmtUsdS(dres)]; });
    const rg = sc.ranges.map(r => [label[r.factor], r.n, fmtPct(r.revRange), fmtPct(r.resRange)]);
    return `<div class="note">Three gross-profit treatments of the discount account (GL 4190) are shown <b>side by side. None is chosen as authoritative</b>; the choice of discount treatment is an open policy question. Gross profit = revenue &minus; COGS (signs as recorded, COGS as positive magnitude).</div>
<div class="grid">
<section class="card c12"><div class="ctl"><div><h3>Gross profit by treatment</h3><div class="csub">Row set: ${ref === 'ALL' ? 'all rows' : 'all-non-negative rows only'} &middot; current filters</div></div><div class="fg"><label for="selGp">Row set</label><select id="selGp"><option value="ALL"${ref === 'ALL' ? ' selected' : ''}>All rows</option><option value="NONNEG"${ref === 'NONNEG' ? ' selected' : ''}>All-non-negative rows only</option></select></div></div>${tableOf(['Treatment', 'Revenue', 'COGS', 'Gross profit', 'Gross margin'], gpRows, { num: [1, 2, 3, 4] })}</section>
${cardHtml('gGm', 'Gross margin by year', 'Gross profit &divide; revenue, per treatment', 'c6')}
${cardHtml('gGp', 'Gross profit by entity', 'USD per treatment (grouped as separate rows)', 'c6')}
<section class="card c12"><h3>Gross profit vs budget &mdash; same-sign lines</h3><div class="csub">SQL analysis E3 basis: revenue and COGS lines with a budget whose actual and budget share a sign; treatment applied to both actual and budget. Revenue effect = actual revenue &minus; budget revenue; COGS effect = &minus;(actual COGS &minus; budget COGS). (Not affected by the Variance-population selector.)</div>${tableOf(['Treatment', 'Actual GP', 'Budget GP', 'GP variance', 'Actual GM', 'Budget GM', 'Revenue effect', 'COGS effect', 'Lines'], vbRows, { num: [1, 2, 3, 4, 5, 6, 7, 8] })}</section>
<section class="card c12"><h3>Sensitivity of the headline to unresolved assumptions</h3><div class="csub">Revenue, cost base (COGS+People+Opex) and result proxy under each scenario, one assumption changed at a time; <b>baseline</b> = Posted only, scale-adjusted, duplicate candidates retained, signs as recorded. These are sensitivities, not alternative &ldquo;correct&rdquo; answers. Status-partition rows are diagnostics, not reporting policies.</div>${stNote}${tableOf(['Factor', 'Scenario', 'Class', 'Lines', 'Revenue', 'Cost base', 'Result proxy', '&Delta; revenue vs baseline', '&Delta; result vs baseline'], srows, { num: [3, 4, 5, 6, 7, 8], maxH: 520 })}</section>
<section class="card c6"><h3>Which assumption moves the headline most?</h3><div class="csub">Range across baseline + policy scenarios of each factor, as % of that factor's baseline (diagnostics excluded)</div>${tableOf(['Factor', 'Scenarios', 'Revenue range', 'Result range'], rg, { num: [1, 2, 3] })}</section>
</div>`;
  },
  draw() {
    $('#selGp').onchange = e => { UI.gpRowset = e.target.value; renderActive(true); };
    const g = gpAgg(UI.gpRowset);
    lineChart('gGm', { labels: YEARS.map(String), fmt: v => fmtPct(v, 1), series: GP_T.map((t, k) => ({ name: t.name, color: SERCOL(k), vals: g[k].yr.map(y => y.rev ? (y.rev - y.cogs) / y.rev : NaN) })), aria: 'Gross margin by year', h: 240 });
    const items = []; P.ents.forEach((e, ei) => GP_T.forEach((t, k) => items.push({ label: e.c + ' ' + t.k, key: ei, val: g[k].ent[ei].rev - g[k].ent[ei].cogs, color: SERCOL(k), pat: k })));
    barChart('gGp', { items, fmt: v => fmtUsd(v), axisFmt: fmtAx, onClick: xfEnt, selected: selKey('ent'), aria: 'Gross profit by entity', rowH: 17, legend: GP_T.map((t, k) => [t.name, SERCOL(k)]) });
  }
};

/* ---- 7. Insights ---- */
function dynInsights() {
  return memo('ins', () => {
    const a = agg(), out = [], sc = `${scopeText()}; ${fmtInt(nInc)} Posted lines`, fPop = VARPOP_LBL[S.varPop];
    const vs = varBySection(S.varPop), rv = vs[0], cv = tot(vs, COSTBASE), vcs = varCells(S.varPop);
    const common = { scenario: `Basis: ${SCALE_LBL[S.scale]}; ${DUP_LBL[S.dup]}; ${SIGN_LBL[S.sign]}.` };
    const dirw = x => x < 0 ? 'below' : 'above';
    const topFor = secs => { const m = {}; cellIter(vcs, (e, g, mo, ac, b) => { if (!secs.includes(GSI[g])) return; const k = e * NG + g; const t = m[k] || (m[k] = { e, g, v: 0 }); t.v += ac - b; }); const arr = topN(Object.values(m), t => Math.abs(t.v), 3); const sumAbs = Object.values(m).reduce((s, t) => s + Math.abs(t.v), 0); return { arr, sumAbs }; };
    const dec = (label, o) => out.push({ ...o, tag: label });
    if (rv.n) { const tp = topFor([0]); dec('Revenue vs budget', {
      obs: `Revenue is ${fmtUsd(Math.abs(rv.net))} ${dirw(rv.net)} budget on lines that carry a budget${rv.pct == null ? ' (percentage not publishable: net budget under 50% of gross absolute budget)' : ', ' + fmtPct(Math.abs(rv.pct)) + ' of |net budget|'}.`,
      scope: `${sc}; ${fmtInt(rv.n)} revenue lines with a budget; population: ${fPop}.`,
      calc: `Actual ${fmtUsd(rv.act, 1)} &minus; budget ${fmtUsd(rv.bud, 1)} = ${fmtUsdS(rv.net)}. Gross cell variance ${fmtUsd(rv.gross)} (${rv.grossPct == null ? 'n/a' : fmtPct(rv.grossPct)} of cell budget), so offsetting cells ${rv.gross > Math.abs(rv.net) * 1.5 ? 'hide a considerably larger underlying movement' : 'hide little'}.`,
      drivers: tp.arr.length ? 'Largest entity &times; GL cells: ' + tp.arr.map(t => `${P.ents[t.e].c} ${P.gls[t.g].gl} (${fmtUsdS(t.v)})`).join('; ') + (tp.sumAbs ? ` &mdash; together ${fmtPct(tp.arr.reduce((s, t) => s + Math.abs(t.v), 0) / tp.sumAbs, 0)} of the cells' absolute net variance.` : '.') : 'n/a',
      evidence: 'Row-level actual and budget amounts (Detail Lines tab); SQL analysis tables B1, B2, B6.',
      conf: 'Medium. Arithmetic reconciles; meaning depends on unresolved rules: Posted-only status (R6), scale restoration (R7), sign convention (R9) and the budget version (unknown).',
      hyp: 'Hypothesis (not tested): budget phasing or price/volume assumptions differ from actual trading; part may reflect sign handling on opposite-sign lines.',
      action: 'Obtain the budget version/date and the revenue sign convention, then re-cut this variance by price vs volume where quantity data allow.',
      need: 'Budget methodology note; written definition of the revenue sign convention; confirmation of the status rule.',
      mon: 'Track net variance % by section each close; alert when the direction or the gross/net ratio changes.' }); }
    if (cv.n) { const tp = topFor(COSTBASE); dec('Cost base vs budget', {
      obs: `Cost base (COGS + People + Opex) is ${fmtUsd(Math.abs(cv.net))} ${dirw(cv.net)} budget${cv.pct == null ? ' (percentage not publishable)' : ', ' + fmtPct(Math.abs(cv.pct)) + ' of |net budget|'}.`,
      scope: `${sc}; ${fmtInt(cv.n)} cost lines with a budget; population: ${fPop}.`,
      calc: `COGS ${fmtUsdS(vs[1].net)} + People ${fmtUsdS(vs[2].net)} + Opex ${fmtUsdS(vs[3].net)} = ${fmtUsdS(cv.net)} (actual ${fmtUsd(cv.act, 1)} vs budget ${fmtUsd(cv.bud, 1)}).`,
      drivers: tp.arr.length ? 'Largest cells: ' + tp.arr.map(t => `${P.ents[t.e].c} ${P.gls[t.g].gl} ${esc(P.gls[t.g].name)} (${fmtUsdS(t.v)})`).join('; ') : 'n/a',
      evidence: 'SQL analysis tables B1, B2, F1; Detail Lines.',
      conf: 'Medium: same open rules as revenue; costs are positive magnitudes so a positive variance means actual above budget, not a judgement.',
      hyp: 'Hypothesis: a similar-sized percentage gap across COGS, People and Opex can point to a common budget-setting method (e.g. a uniform uplift) rather than line-specific causes &mdash; test by checking whether the ratio is uniform across accounts.',
      action: 'Ask the budget owner how the budget was built (top-down factor vs bottom-up) before attributing the gap to operations.',
      need: 'Budget build documentation; accrual/cut-off policy for Pending and Parked entries.',
      mon: 'Monitor the cost-to-budget ratio by account; flag accounts whose ratio departs from the group ratio.' }); }
    const pers = persistence(), pp = pers.filter(t => t.persistent);
    if (pers.length) dec('Persistence', {
      obs: `${fmtInt(pp.length)} of ${fmtInt(pers.length)} entity &times; GL cells (with &ge;12 months) sit on the same side of budget in at least 90% of months with a variance of at least 3%.`,
      scope: `${sc}; same-sign lines only (SQL analysis F5 rule); cells need &ge;12 months inside the selected period.`,
      calc: `Dominant-side share = max(months above, months below) &divide; months with data; |variance %| &ge; 3% of |net budget|.`,
      drivers: pp.length ? 'Largest by |variance|: ' + topN(pp, t => Math.abs(t.v), 3).map(t => `${P.ents[t.e].c} ${P.gls[t.g].gl} (${fmtUsdS(t.v)}, ${t.dir === 'above' ? 'above' : 'below'} budget ${Math.max(t.above, t.below)}/${t.months} months)`).join('; ') : 'No cell meets the rule in this selection.',
      evidence: 'SQL analysis F5/B6 tables; Budget &amp; Variance tab.',
      conf: 'Low to medium: persistence is consistent with a budget-level bias but is also what a systematic data or sign artefact would produce.',
      hyp: 'Hypothesis: a one-sided pattern in nearly every cell suggests a budget or data-generation convention rather than 36 independent operating shortfalls.',
      action: 'Review the persistent cells with the budget owner before any operational follow-up; start with the largest cells.',
      need: 'Budget version and basis; sign convention (R9).',
      mon: 'Re-run the persistence rule each quarter; track the count and total variance of persistent cells.' });
    const vAll = varBySection('ALL'), vSame = varBySection('SAME'), vOpp = varBySection('OPP');
    if (vAll[0].n) dec('Sign sensitivity', {
      obs: `Revenue net variance is ${fmtUsdS(vAll[0].net)} on all lines but ${fmtUsdS(vSame[0].net)} on same-sign lines; opposite-sign lines contribute ${fmtUsdS(vOpp[0].net)}.`,
      scope: `${sc}; revenue lines with a budget (all / same-sign / opposite-sign populations).`,
      calc: `All-lines net variance &minus; same-sign &minus; opposite-sign &minus; zero-involved = bridge (SQL analysis B8 reconciles to 0.00).`,
      drivers: `${fmtInt(vOpp[0].n)} opposite-sign revenue lines out of ${fmtInt(vAll[0].n)} (${vAll[0].n ? fmtPct(vOpp[0].n / vAll[0].n) : 'n/a'}).`,
      evidence: 'SQL analysis B7/B8; Budget &amp; Variance sign table.',
      conf: 'Medium: arithmetic exact; whether opposite-sign lines are defects or legitimate (credit notes, reversals) is unresolved.',
      hyp: 'Hypothesis: some opposite-sign lines are sign-convention artefacts; others may be genuine reversals.',
      action: 'Classify a sample of opposite-sign lines with the ledger owner and decide a documented treatment.',
      need: 'Sign-convention definition (R9); reversal/credit-note flags.',
      mon: 'Track the share of opposite-sign lines per close.' });
    const f = fcPops(), wA = f.A[0].absA ? f.A[0].errF / f.A[0].absA : null, wAb = f.A[0].absA ? f.A[0].errB / f.A[0].absA : null, wB = f.B[0].absA ? f.B[0].errF / f.B[0].absA : null, wBb = f.B[0].absA ? f.B[0].errB / f.B[0].absA : null, wC = f.C[0].absA ? f.C[0].errF / f.C[0].absA : null;
    if (f.C[0].n) dec('Forecast vs budget', {
      obs: `Revenue forecast WAPE is ${fmtPct(wA, 2)} vs budget ${fmtPct(wAb, 2)} on the matched same-sign subset (A, ${fmtInt(f.A[0].n)} lines), but ${fmtPct(wB, 1)} vs ${fmtPct(wBb, 1)} on all comparable lines (B, ${fmtInt(f.B[0].n)}); all forecast lines (C, ${fmtInt(f.C[0].n)}): ${fmtPct(wC, 1)}.`,
      scope: `${sc}; revenue; three populations kept separate.`,
      calc: 'WAPE = &Sigma;|forecast &minus; actual| &divide; &Sigma;|actual| (budget column the same way on the same lines).',
      drivers: `Lines with opposite-sign forecast carry ${f.cat[0][1].abs + f.cat[0][0].abs + f.cat[0][2].abs ? fmtPct(f.cat[0][1].abs / (f.cat[0][0].abs + f.cat[0][1].abs + f.cat[0][2].abs)) : 'n/a'} of absolute revenue forecast error in this selection.`,
      evidence: 'SQL analysis C1, C6, C2; Forecast tab.',
      conf: 'Low for any general claim: the forecast has no version or as-of date, and the matched subset excludes the lines that drive most of the error.',
      hyp: 'Hypothesis: the forecast column may be derived from or revised after actuals; not testable from the extract.',
      action: 'Do not use forecast accuracy as evidence of skill until the forecast version/timing is documented.',
      need: 'Forecast version and as-of date per row.',
      mon: 'Once versioned, track WAPE and bias by quarter on a fixed comparable population.' });
    const c = costAbs(), cg = concentration(Array.from(c.gl), P.gls.map(g => g.gl + ' ' + g.name));
    if (cg) dec('Cost concentration', {
      obs: `${cg.top1m} is the largest cost account at ${fmtPct(cg.top1)} of the cost population; the top three accounts hold ${fmtPct(cg.top3)} (HHI ${cg.hhi.toFixed(3)} vs equal-share ${cg.eq.toFixed(3)}).`,
      scope: `${sc}; COGS, People, Opex and D&amp;A on absolute amounts.`,
      calc: 'Share = |GL amount| &divide; &Sigma;|cost amounts|; HHI = &Sigma;share&sup2;.',
      drivers: 'See Drivers &amp; Concentration for the ranked list and entity/division/cost-centre concentration.',
      evidence: 'SQL analysis F1, F2.', conf: 'High on the arithmetic; low on any cost-driver interpretation.',
      hyp: 'Hypothesis: concentration points to where a cost review would have the most leverage; no saving is implied.',
      action: 'Prioritise any cost-review effort on the highest-share accounts after confirming the data basis; observed variance is not a saving.',
      need: 'Account-level cost owners and contract/volume data.', mon: 'Track top-3 share and HHI by quarter.' });
    const o = statusTotals(), all = STATUSES.reduce((s, k) => s + o[k].n, 0), allRev = STATUSES.reduce((s, k) => s + o[k].rev, 0);
    if (all) dec('Journal status', {
      obs: `Posted lines are ${fmtPct(o.Posted.n / all)} of all-status lines and ${allRev ? fmtPct(o.Posted.rev / allRev) : 'n/a'} of all-status revenue in this selection; other statuses: ${STATUSES.slice(1).map(k => k + ' ' + fmtPct(o[k].n / all)).join(', ')} of lines.`,
      scope: `${sc}; all-status line-level population (separate from the Posted-only dashboard population) with every filter and the selected scale/duplicate/sign scenarios applied.`,
      calc: `Posted revenue ${fmtUsd(o.Posted.rev)} vs all-status revenue ${fmtUsd(allRev)}.`,
      drivers: 'Pending, Parked, Rejected and blank statuses are excluded by provisional rule R6.',
      evidence: 'SQL analysis I1/I2, INS-01.', conf: 'High that the dependency exists; low on which status rule is right.',
      hyp: 'Hypothesis: status may be assigned independently of line size or section; not testable from the extract.',
      action: 'Present headline figures as a range until the status definitions are documented.',
      need: 'Written definitions of Posted/Pending/Parked/Rejected/blank and the extract cut-off.', mon: 'Track the Posted share of lines each close.' });
    return out;
  });
}
VIEWS.insights = {
  html() {
    const dyn = nInc ? dynInsights() : [];
    const field = (n, h) => `<div class="f"><div class="fn">${n}</div><div>${h}</div></div>`;
    const dynHtml = dyn.map((d, i) => `<details class="ins"${i < 2 ? ' open' : ''}><summary>${esc(d.tag)} <span class="pill dyn">Current selection</span><div style="font-weight:400;color:var(--ink-2);margin-top:2px">${d.obs}</div></summary><div class="body">
${field('<span class="tag-obs">OBSERVED</span> Observation', d.obs)}${field('Period &amp; population', d.scope)}${field('Magnitude &amp; calculation', d.calc)}${field('Drivers', d.drivers)}${field('Evidence', d.evidence)}${field('Confidence &amp; assumptions', d.conf + '<br>' + esc(d.scenario))}${field('<span class="tag-hyp">HYPOTHESIS</span>', d.hyp)}${field('<span class="tag-act">ACTION</span> Recommendation', d.action + ' <i>(No saving is implied by an observed variance.)</i>')}${field('Evidence needed', d.need)}${field('Monitoring', d.mon)}</div></details>`).join('');
    const fx = P.ins.map(x => `<details class="ins"><summary>${esc(x.id)} &middot; ${esc(x.title)} <span class="pill fixed">Overall portfolio finding &mdash; fixed</span></summary><div class="body">${x.fields.map(f => field(esc(f.name), f.html)).join('')}</div></details>`).join('');
    const rk = tableOf(['Rank', 'ID', 'Insight', 'Mat.', 'Pers.', 'Conf.', 'Act.', 'Total'], P.rank.map(r => [r.rank, r.id, esc(r.title), r.mat, r.per, r.conf, r.act, r.total]), { num: [0, 3, 4, 5, 6, 7], cls: 'mini' });
    return `<div class="note info">Two kinds of insight appear here and are labelled: <b>Current selection</b> insights are recalculated from the filters (and change with them); <b>Overall portfolio</b> insights are the fixed SQL analysis register entries (all 36 months, all entities, baseline rules) and do <b>not</b> change with filters. Observed facts, hypotheses and recommendations are kept apart; none implies a saving.</div>
<h3 style="margin:14px 0 8px">A &middot; Insights for the current selection <span class="pill dyn">filter-dependent</span></h3>${nInc ? dynHtml : emptyHtml()}
<h3 style="margin:18px 0 8px">B &middot; SQL analysis insight register <span class="pill fixed">fixed &middot; overall portfolio</span></h3><div class="card" style="margin-bottom:10px"><div class="csub">Score 1&ndash;3 per axis (convention of this project, not a standard)</div>${rk}</div>${fx}`;
  }
};

/* ---- 8. Data Quality & Methodology ---- */
VIEWS.quality = {
  html() {
    const m = P.meta, rec = RECON.list, okN = rec.filter(r => r.ok).length;
    const wf = rt('i9_exclusion_waterfall'), fl = rt('i8_flag_exposure'), st = statusTotals();
    const stat = STATUSES.map(k => [k, fmtInt(st[k].n), fmtUsd(st[k].rev), fmtUsd(st[k].cost)]);
    const dict = [['Revenue', 'Σ actual_usd_adj, section REVENUE, Posted lines', 'USD (scale-adjusted, provisional)', 'Signs as recorded'], ['Cost base', 'Σ actual_usd_adj, sections COGS + PEOPLE + OPEX', 'USD', 'Positive magnitudes'], ['Result proxy', 'Revenue − cost base', 'USD', 'Not EBITDA; excludes D&A, below-EBITDA, tax'], ['Variance', 'Actual − Budget on lines with a budget', 'USD', 'Positive = actual above budget; no favourable/unfavourable label'], ['Variance %', 'Variance ÷ |net budget|, published only if |net budget| ≥ 50% of Σ|cell budget|', '%', 'SQL analysis safe_pct'], ['Gross cell variance', 'Σ |actual − budget| over entity × GL × month cells', 'USD', 'Shows what net variance nets away'], ['WAPE', 'Σ|forecast − actual| ÷ Σ|actual|', '%', 'Populations A/B/C kept separate; no skill claim'], ['Bias', 'Σ(forecast − actual) ÷ Σ|actual|', '%', ''], ['Gross profit', 'Revenue − COGS under treatments S1/S2/S3 (GL 4190 discount)', 'USD', 'No treatment chosen'], ['Persistent deviation', 'Same-sign lines; entity × GL; ≥12 months; ≥90% one side; |var %| ≥ 3%', 'cells', 'SQL analysis F5'], ['True YoY', 'Same calendar months, consecutive years, both in scope', '%', 'Not the dataset prior-year column'], ['HHI', 'Σ share² of absolute cost by member', '0–1', 'Read against 1/N']];
    const rules = [['R6', 'Journal status: Posted only', 'Provisional'], ['R7', 'Reporting scale: restore rows at 1E3/1E5 where evidence supports', 'Provisional'], ['R8', 'FX direction (local ÷ rate vs ×)', 'Provisional'], ['R9', 'Sign convention (is a positive cost an expense?)', 'Unresolved'], ['R10', 'Variance % denominator rule', 'Provisional'], ['R11', 'Duplicate candidates retained (not confirmed duplicates)', 'Unresolved'], ['R12', 'Consolidation / intercompany elimination', 'Unresolved']];
    const unavailable = ['DSO, DPO, working capital (balance-sheet measurement basis unresolved)', 'Month-end close duration / close-timeliness KPIs (no timestamps for close steps)', 'Unit economics, forecast skill (no forecast version/as-of date)', 'EBITDA (only a proxy is shown)'];
    return `<div class="grid">
<section class="card c12"><h3>Data readiness gate: <span class="ok">PASS with caveats</span></h3><div class="csub">Source: cleaned extract of ${fmtInt(m.rows_total_source)} rows &rarr; SQL analysis DuckDB; dashboard uses the ${fmtInt(m.rows_pl_eligible)} eligible P&amp;L actual lines (Posted, valid entity/GL/period, scale decision made). Nothing was cleaned, deduplicated, imputed, dropped, re-signed or re-scaled by this dashboard.</div>
<ul style="margin:0 0 6px 18px"><li>Row accounting from ${fmtInt(m.rows_total_source)} source rows to ${fmtInt(m.rows_pl_eligible)} eligible lines is shown below (one primary exclusion reason per row).</li><li>${fmtInt(m.rows_budget)} eligible lines carry a budget; ${fmtInt(m.rows_any_status)} lines pass every gate except the status gate.</li><li>All ${fmtInt(m.rows_pl_eligible)} eligible lines are embedded; none is truncated or sampled.</li><li>Material caveats: R6&ndash;R12 below are unresolved or provisional; source provenance and licence are unverified; the data is synthetic.</li></ul></section>
<section class="card c12"><h3>Baseline reconciliation to SQL analysis tables <span class="badge ${okN === rec.length ? 'ok' : 'bad'}">${okN} / ${rec.length} checks passed</span></h3><div class="csub">At <b>default filters</b> the dashboard recomputes these values from the embedded lines and compares them with the SQL analysis output tables embedded alongside; this is a baseline check and <b>not an independent reconciliation of any filtered view</b> (the header &ldquo;Selection checks&rdquo; badge is an internal consistency check of the current selection; the offline QA report holds the independent comparison). Tolerance: counts exact; USD within $0.01; ratios within 1e-9.</div><button class="btn hide-print" id="btnRerun">Re-run reconciliation</button>
${tableOf(['Group', 'Check', 'Dashboard', 'SQL analysis table', 'Result'], rec.filter(r => !r.ok).concat(rec.filter(r => r.ok).slice(0, 12)).map(r => [r.group, esc(r.desc), r.dash, r.ref, r.ok ? '<span class="ok">PASS</span>' : '<span class="bad">FAIL</span>']), { num: [2, 3], maxH: 300 })}<div class="csub" style="margin-top:6px">Showing all failures first, then the first 12 passes. Full list: ${rec.length} checks across groups ${[...new Set(rec.map(r => r.group))].join(', ')}.</div></section>
<section class="card c6"><h3>Row accounting (all source rows)</h3><div class="csub">Primary exclusion reason per row (SQL analysis I9)</div>${tableOf(['Reason', 'Rows', '% of rows'], wf.map(r => [esc(r.primary_reason), fmtInt(r.rows_n), fmtPct(r.share_of_all_rows, 2)]), { num: [1, 2] })}</section>
<section class="card c6"><h3>Journal status &mdash; all-status population, current selection</h3><div class="csub">Line-level; Posted = the dashboard baseline (R6)</div><div class="note info" id="statScope">${SCOPE_STATUS}</div>${tableOf(['Status', 'Lines', 'Revenue', 'Cost base'], stat, { num: [1, 2, 3] })}</section>
<section class="card c12"><h3>Flag exposure on the eligible lines (overall)</h3><div class="csub">SQL analysis I8; flags overlap; fixed portfolio figures</div>${tableOf(['Flag', 'Lines', 'Abs. USD flagged', '% of lines', '% of abs. USD'], fl.map(r => [esc(r.flag), fmtInt(r.rows_flagged), fmtUsd(r.abs_actual_usd_flagged), fmtPct(r.share_of_eligible_rows, 2), fmtPct(r.share_of_eligible_abs, 2)]), { num: [1, 2, 3, 4], maxH: 360 })}</section>
<section class="card c7"><h3>Metric dictionary</h3><div class="csub">Headline KPIs: Revenue, Cost base, Result proxy, Revenue vs budget, Cost base vs budget</div>${tableOf(['Measure', 'Formula', 'Unit', 'Notes'], dict.map(r => r.map(esc)), { cls: 'mini' })}</section>
<section class="card c5"><h3>Open assumptions</h3><div class="csub">Not resolved by this dashboard</div>${tableOf(['ID', 'Rule', 'Status'], rules.map(r => r.map(esc)), { cls: 'mini' })}<h3 style="margin-top:12px">Not shown (unsupported by the data)</h3><ul style="margin:4px 0 0 18px">${unavailable.map(u => `<li>${esc(u)}</li>`).join('')}</ul></section>
<section class="card c12"><h3>Provenance &amp; file</h3><div class="csub">Hashes recorded when this file was built</div>${tableOf(['Item', 'SHA-256 / value'], [['Cleaned CSV', `<code>${m.csv_sha256}</code>`], ['Raw CSV', `<code>${m.raw_sha256}</code>`], ['SQL analysis database', `<code>${m.db_sha256}</code>`], ['Excel workbook workbook', `<code>${m.xlsx_sha256}</code>`], ['Embedded lines', fmtInt(N)]], { cls: 'mini' })}<p style="margin:8px 0 0">Reconciliation to the Excel workbook workbook is performed by the offline QA script and reported in <code>DASHBOARD_QA_REPORT.md</code>.</p></section>
</div>`;
  },
  draw() { const b = $('#btnRerun'); if (b) b.onclick = () => { runRecon(); built.quality = -1; renderActive(true); }; }
};

/* ---- 9. Detail ---- */
const DCOLS = [['src', 'Source row', 0], ['doc', 'Document', 0], ['m', 'Period', 0], ['e', 'Entity', 0], ['d', 'Division', 0], ['g', 'GL', 0], ['name', 'Account', 0], ['sec', 'Section', 0], ['c', 'Cost ctr', 0], ['a', 'Actual', 1], ['b', 'Budget', 1], ['f', 'Forecast', 1], ['p', 'Prior-yr col.', 1], ['var', 'Var (A&minus;B)', 1], ['sab', 'Sign A/B', 0], ['rs', 'Scale', 0], ['dp', 'Dup. tier', 0]];
const SIGNLBL = ['same', 'opposite', 'zero', 'n/a'], RSL = ['–', 'restored HIGH', 'restored MEDIUM'], DPL = ['unique/anchor', 'candidate same-sign', 'candidate sign-conflict', 'partial'];
function detKey(k, i) {
  switch (k) { case 'src': return R.src[i]; case 'doc': return R.doc[i] || ''; case 'm': return Mi[i]; case 'e': return P.ents[Ei[i]].c; case 'd': return P.divs[Di[i]]; case 'g': return P.gls[Gi[i]].gl; case 'name': return P.gls[Gi[i]].name; case 'sec': return P.gls[Gi[i]].sec; case 'c': return Ci[i] < 0 ? '' : P.ccs[Ci[i]]; case 'a': return EA[i]; case 'b': return EB[i]; case 'f': return EF[i]; case 'p': return EP[i]; case 'var': return EA[i] - EB[i]; case 'sab': return SAB[i]; case 'rs': return RS[i]; case 'dp': return DP[i]; }
}
function detRows(noSearch) {
  const q = noSearch ? '' : UI.det.q.trim().toLowerCase(), out = [];
  for (let i = 0; i < N; i++) { if (!inc[i]) continue; if (q) { const hay = ((R.doc[i] || '') + ' ' + P.gls[Gi[i]].gl + ' ' + P.gls[Gi[i]].name + ' ' + P.ents[Ei[i]].c + ' ' + P.divs[Di[i]] + ' ' + P.months[Mi[i]] + ' ' + (Ci[i] < 0 ? '' : P.ccs[Ci[i]]) + ' ' + R.src[i]).toLowerCase(); if (!hay.includes(q)) continue; } out.push(i); }
  const k = UI.det.sort, dir = UI.det.dir;
  out.sort((x, y) => { let a = detKey(k, x), b = detKey(k, y); const an = typeof a === 'number' && a !== a, bn = typeof b === 'number' && b !== b; if (an || bn) return an && bn ? 0 : an ? 1 : -1; return (a < b ? -1 : a > b ? 1 : 0) * dir || (R.src[x] - R.src[y]); });
  return out;
}
const nz = v => v === v ? v : null;
function detCell(k, i) {
  switch (k) {
    case 'src': return R.src[i]; case 'doc': return esc(R.doc[i] || ''); case 'm': return P.months[Mi[i]]; case 'e': return P.ents[Ei[i]].c; case 'd': return esc(P.divs[Di[i]]); case 'g': return P.gls[Gi[i]].gl; case 'name': return esc(P.gls[Gi[i]].name); case 'sec': return secName(P.gls[Gi[i]].sec); case 'c': return Ci[i] < 0 ? '' : P.ccs[Ci[i]];
    case 'a': case 'b': case 'f': case 'p': { const v = detKey(k, i); return v === v ? v.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 }).replace('-', MINUS) : '<span style="color:var(--muted)">–</span>'; }
    case 'var': { const v = EA[i] - EB[i]; return v === v ? v.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 }).replace('-', MINUS) : '–'; }
    case 'sab': return SIGNLBL[SAB[i]]; case 'rs': return RSL[RS[i]]; case 'dp': return DPL[DP[i]];
  }
}
let detCache = null;
VIEWS.detail = {
  html() {
    return `<div class="note info">Every line in the current selection, under the current scale basis. Click a column header to sort; search matches document, account, entity, division, period, cost centre or source row. &ldquo;Export all filtered lines (CSV)&rdquo; (top right) saves <b>all</b> rows matching the filters and search, in the current sort order. <b>Print / PDF prints the dashboard report; on this tab it prints only the rows of the current page</b> &mdash; it is not an export of all matching lines.</div>
<section class="card"><div class="frow" style="margin-bottom:8px"><div class="fg"><label for="detQ">Search</label><input id="detQ" type="search" style="border:1px solid var(--border);border-radius:7px;padding:5px 8px;background:var(--surface);min-width:260px" placeholder="e.g. 4100, US01, doc number&hellip;" value="${esc(UI.det.q)}"></div><div class="fg"><label for="detSize">Rows per page</label><select id="detSize">${[25, 50, 100, 250].map(s => `<option${UI.det.size === s ? ' selected' : ''}>${s}</option>`).join('')}</select></div><div id="detCount" style="align-self:center;color:var(--ink-2)" class="num"></div></div><div id="detTable"></div><div class="pager"><div id="detInfo" class="num"></div><div><button class="btn" id="detPrev">&larr; Prev</button> <button class="btn" id="detNext">Next &rarr;</button></div></div></section>`;
  },
  draw() {
    const q = $('#detQ'); q.oninput = () => { UI.det.q = q.value; UI.det.page = 0; this.table(); };
    $('#detSize').onchange = e => { UI.det.size = +e.target.value; UI.det.page = 0; this.table(); };
    $('#detPrev').onclick = () => { UI.det.page = Math.max(0, UI.det.page - 1); this.table(); };
    $('#detNext').onclick = () => { UI.det.page++; this.table(); };
    this.table();
  },
  table() {
    const rows = detCache = detRows(), sz = UI.det.size, pages = Math.max(1, Math.ceil(rows.length / sz)); UI.det.page = Math.min(UI.det.page, pages - 1);
    const from = UI.det.page * sz, slice = rows.slice(from, from + sz);
    $('#detCount').textContent = fmtInt(rows.length) + ' lines match';
    $('#detTable').innerHTML = rows.length ? `<div class="tw" style="max-height:620px"><table><thead><tr>${DCOLS.map(([k, n, r]) => `<th class="sort ${r ? 'r' : ''}" data-k="${k}" tabindex="0" role="columnheader" aria-sort="${UI.det.sort === k ? (UI.det.dir > 0 ? 'ascending' : 'descending') : 'none'}">${n}${UI.det.sort === k ? (UI.det.dir > 0 ? ' ▲' : ' ▼') : ''}</th>`).join('')}</tr></thead><tbody>${slice.map(i => `<tr>${DCOLS.map(([k, n, r]) => `<td class="${r ? 'r' : ''}">${detCell(k, i)}</td>`).join('')}</tr>`).join('')}</tbody></table></div>` : '<div class="empty">No lines match the current filters and search.</div>';
    $$('#detTable th.sort').forEach(th => { const go = () => { const k = th.dataset.k; if (UI.det.sort === k) UI.det.dir *= -1; else { UI.det.sort = k; UI.det.dir = 1; } UI.det.page = 0; this.table(); }; th.onclick = go; th.onkeydown = e => { if (e.key === 'Enter') go(); }; });
    $('#detInfo').textContent = rows.length ? `Rows ${fmtInt(from + 1)}–${fmtInt(Math.min(from + sz, rows.length))} of ${fmtInt(rows.length)} · page ${UI.det.page + 1} of ${pages}` : '';
    $('#detPrev').disabled = UI.det.page === 0; $('#detNext').disabled = UI.det.page >= pages - 1;
  }
};

/* ---------- CSV export ---------- */
function csvCell(v) {
  if (v == null || v !== v) return '';
  if (typeof v === 'number') return String(v);
  let s = String(v); if (/^[=+\-@\t\r]/.test(s)) s = "'" + s;
  return /[",\n\r]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s;
}
function buildCsv() {
  const rows = S.tab === 'detail' ? detRows() : detRows(true);
  const head = ['source_row_number', 'document_no', 'period_ym', 'entity_code', 'division', 'gl_account', 'account_name', 'section', 'cost_center_code', 'actual_usd', 'budget_usd', 'forecast_usd', 'prior_year_col_usd', 'actual_minus_budget', 'sign_cat_actual_vs_budget', 'scale_restoration', 'duplicate_tier', 'scale_basis', 'duplicate_scenario', 'sign_scenario'];
  const lines = [head.join(',')];
  for (const i of rows) lines.push([R.src[i], R.doc[i], P.months[Mi[i]], P.ents[Ei[i]].c, P.divs[Di[i]], P.gls[Gi[i]].gl, P.gls[Gi[i]].name, P.gls[Gi[i]].sec, Ci[i] < 0 ? '' : P.ccs[Ci[i]], EA[i], EB[i], EF[i], EP[i], EA[i] - EB[i], SIGNLBL[SAB[i]], RSL[RS[i]], DPL[DP[i]], S.scale, S.dup, S.sign].map(csvCell).join(','));
  return { text: '﻿' + lines.join('\r\n') + '\r\n', n: rows.length };
}
function exportCsv() {
  if (!nInc) { alert('No lines in the current selection to export.'); return; }
  const { text } = buildCsv(), blob = new Blob([text], { type: 'text/csv;charset=utf-8' }), a = document.createElement('a');
  a.href = URL.createObjectURL(blob); a.download = 'fpa_filtered_detail_lines.csv'; document.body.appendChild(a); a.click(); setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 500);
}

/* ---------- live reconciliation to SQL analysis tables ---------- */
const RECON = { list: [] };
function runRecon() {
  const saveS = S, saveH = hist.length; S = DEF(); recompute();
  const L = []; const add = (group, desc, dash, ref, kind) => { let ok; if (kind === 'n') ok = dash === ref; else if (kind === 'r') ok = Math.abs(dash - ref) <= 1e-9 * Math.max(1, Math.abs(ref)); else ok = Math.abs(dash - ref) <= Math.max(0.01, 1e-9 * Math.abs(ref)); const f = kind === 'n' ? fmtInt : kind === 'r' ? (v => (v * 100).toFixed(4) + '%') : (v => fmtUsd(v, 1)); L.push({ group, desc, dash: f(dash), ref: f(ref), ok }); };
  add('Rows', 'Eligible P&L lines embedded', N, P.meta.rows_pl_eligible, 'n'); add('Rows', 'Lines in scope at default filters', nInc, P.meta.rows_pl_eligible, 'n');
  let nb = 0; for (let i = 0; i < N; i++) if (EB[i] === EB[i]) nb++; add('Rows', 'Lines carrying a budget', nb, P.meta.rows_budget, 'n');
  /* I1 */
  const i1 = rt('i1_scenarios'), st = statusTotals(); const stMap = { 'POSTED_ONLY (baseline)': ['Posted'], PENDING_ONLY: ['Pending'], PARKED_ONLY: ['Parked'], REJECTED_ONLY: ['Rejected'], BLANK_ONLY: ['(blank)'], ALL_EXCEPT_REJECTED: ['Posted', 'Pending', 'Parked', '(blank)'], ALL_STATUSES: STATUSES };
  const scMap = { 'ADJUSTED_ALL (baseline)': ['ADJ', 'KEEP', 'KEEP'], 'AS_REPORTED_PARSED (no restoration)': ['PARSED', 'KEEP', 'KEEP'], RESTORE_HIGH_CONFIDENCE_ONLY: ['HIGH', 'KEEP', 'KEEP'], EXCLUDE_ALL_RESTORED_ROWS: ['EXCL_ALL', 'KEEP', 'KEEP'], EXCLUDE_MEDIUM_CONFIDENCE_RESTORED: ['EXCL_MED', 'KEEP', 'KEEP'], 'CANDIDATES_RETAINED (baseline)': ['ADJ', 'KEEP', 'KEEP'], EXCLUDE_SAME_SIGN_CANDIDATES: ['ADJ', 'EXCL_SAME', 'KEEP'], EXCLUDE_ALL_COPY_CANDIDATES: ['ADJ', 'EXCL_ALL', 'KEEP'], 'ALL_ROWS_SIGNS_AS_RECORDED (baseline)': ['ADJ', 'KEEP', 'KEEP'], ALL_NON_NEGATIVE_ROWS_ONLY: ['ADJ', 'KEEP', 'NONNEG'], EXCLUDE_SINGLE_COLUMN_SIGN_FLIPS: ['ADJ', 'KEEP', 'EXCL_FLIP'] };
  i1.forEach(r => {
    let t; if (r.factor === 'status') { const ks = stMap[r.scenario]; t = ks.reduce((a, k) => ({ n: a.n + st[k].n, rev: a.rev + st[k].rev, cost: a.cost + st[k].cost }), { n: 0, rev: 0, cost: 0 }); }
    else { const p = scMap[r.scenario]; t = scenarioTotals(p[0], p[1], p[2]); }
    const nm = r.factor + ' / ' + r.scenario; add('I1 scenarios', nm + ' - lines', t.n, r.rows_in_scope, 'n'); add('I1 scenarios', nm + ' - revenue', t.rev, r.revenue_usd, 'u'); add('I1 scenarios', nm + ' - cost', t.cost, r.cost_usd, 'u'); add('I1 scenarios', nm + ' - result proxy', t.rev - t.cost, r.result_proxy_usd, 'u');
  });
  /* B1 */
  rt('b1_variance_section').forEach(r => { const pop = r.scenario === 'ALL_LINES' ? 'ALL' : r.scenario === 'SAME_SIGN_ONLY' ? 'SAME' : r.scenario === 'OPPOSITE_SIGN_ONLY' ? 'OPP' : 'ZERO', t = varBySection(pop)[SECI[r.section]], nm = r.scenario + ' / ' + r.section; add('B1 variance', nm + ' - lines', t.n, r.rows_in_scope, 'n'); add('B1 variance', nm + ' - actual', t.act, r.actual_usd, 'u'); add('B1 variance', nm + ' - budget', t.bud, r.budget_usd, 'u'); add('B1 variance', nm + ' - net variance', t.net, r.net_variance_usd, 'u'); add('B1 variance', nm + ' - gross cell variance', t.gross, r.gross_cell_variance_usd, 'u'); if (r.variance_pct_of_abs_budget != null) { if (t.pct == null) L.push({ group: 'B1 variance', desc: nm + ' - variance %', dash: 'n/a', ref: fmtPct(r.variance_pct_of_abs_budget), ok: false }); else add('B1 variance', nm + ' - variance %', t.pct, r.variance_pct_of_abs_budget, 'r'); } else L.push({ group: 'B1 variance', desc: nm + ' - variance % (unpublished in SQL analysis)', dash: t.pct == null ? 'n/a' : fmtPct(t.pct), ref: 'n/a', ok: t.pct == null }); });
  /* C1 ALL_LINES, C6 */
  const f = fcPops();
  rt('c1_forecast_section').filter(r => r.scenario === 'ALL_LINES').forEach(r => { const t = f.C[SECI[r.section]]; add('C1 forecast', r.section + ' - lines', t.n, r.rows_in_scope, 'n'); add('C1 forecast', r.section + ' - abs error', t.errF, r.abs_error_usd, 'u'); add('C1 forecast', r.section + ' - WAPE', t.errF / t.absA, r.wape, 'r'); add('C1 forecast', r.section + ' - bias', t.signedF / t.absA, r.bias, 'r'); });
  rt('c6_forecast_vs_budget').forEach(r => { const t = f.A[SECI[r.section]]; add('C6 matched', r.section + ' - lines', t.n, r.rows_compared, 'n'); add('C6 matched', r.section + ' - WAPE forecast', t.errF / t.absA, r.wape_forecast, 'r'); add('C6 matched', r.section + ' - WAPE budget', t.errB / t.absA, r.wape_budget, 'r'); add('C6 matched', r.section + ' - bias forecast', t.signedF / t.absA, r.bias_forecast, 'r'); add('C6 matched', r.section + ' - bias budget', t.signedB / t.absA, r.bias_budget, 'r'); });
  add('Populations', 'Revenue population A (matched same-sign) lines = 24,372', f.A[0].n, 24372, 'n'); add('Populations', 'Revenue population B (comparable) lines = 29,131', f.B[0].n, 29131, 'n'); add('Populations', 'Revenue population C (all forecast) lines = 30,879', f.C[0].n, 30879, 'n');
  /* E1 / E3 */
  ['ALL', 'NONNEG'].forEach(rs => { const g = gpAgg(rs); rt('e1_gross_profit').filter(r => r.rowset === (rs === 'ALL' ? 'ROWS_ALL' : 'ROWS_ALL_NON_NEGATIVE')).forEach(r => { const k = r.treatment.startsWith('GP_S1') ? 0 : r.treatment.startsWith('GP_S2') ? 1 : 2; const yi = YEARS.indexOf(+r.period); if (yi < 0) return; const y = g[k].yr[yi]; add('E1 gross profit', rs + ' ' + r.treatment + ' ' + r.period + ' - revenue', y.rev, r.revenue_usd, 'u'); add('E1 gross profit', rs + ' ' + r.treatment + ' ' + r.period + ' - COGS', y.cogs, r.cogs_usd, 'u'); add('E1 gross profit', rs + ' ' + r.treatment + ' ' + r.period + ' - lines', y.n, r.rows_in_scope, 'n'); }); });
  const g0 = gpAgg('ALL'); rt('e3_gross_profit_vs_budget').forEach(r => { const k = r.treatment.startsWith('GP_S1') ? 0 : r.treatment.startsWith('GP_S2') ? 1 : 2, v = g0[k].vb; add('E3 GP vs budget', r.treatment + ' - actual GP', v.aRev - v.aCogs, r.actual_gp_usd, 'u'); add('E3 GP vs budget', r.treatment + ' - budget GP', v.bRev - v.bCogs, r.budget_gp_usd, 'u'); add('E3 GP vs budget', r.treatment + ' - GP variance', (v.aRev - v.aCogs) - (v.bRev - v.bCogs), r.gp_variance_usd, 'u'); });
  /* D1 */
  const py = pyAgg('ALL'); rt('d1_vs_py_column').filter(r => r.scenario === 'ALL_LINES').forEach(r => { const t = py[r.period_year + '|' + SECI[r.section]] || { n: 0, act: 0, py: 0 }; add('D1 prior-year', r.period_year + ' ' + r.section + ' - lines', t.n, r.rows_in_scope, 'n'); add('D1 prior-year', r.period_year + ' ' + r.section + ' - actual', t.act, r.actual_usd, 'u'); add('D1 prior-year', r.period_year + ' ' + r.section + ' - PY column', t.py, r.prior_year_usd, 'u'); });
  /* F1 / F2 / F5 */
  const c = costAbs(); rt('f1_cost_by_gl').forEach(r => { const gi = P.gls.findIndex(g => g.gl === r.gl_account); add('F1 cost by GL', r.gl_account + ' - abs USD', c.gl[gi], r.actual_abs_usd, 'u'); });
  const cc = { 'legal_entity': concentration(Array.from(c.ent), P.ents.map(e => e.c)), division: concentration(Array.from(c.div), P.divs), gl_account: concentration(Array.from(c.gl), P.gls.map(g => String(g.gl))), 'cost_center (opex+people)': concentration(Array.from(c.cc), ['(blank)'].concat(P.ccs)) };
  rt('f2_concentration').forEach(r => { const x = cc[r.dimension]; add('F2 concentration', r.dimension + ' - members', x.members, r.members, 'n'); add('F2 concentration', r.dimension + ' - top-1 share', x.top1, r.top1_share, 'r'); add('F2 concentration', r.dimension + ' - top-3 share', x.top3, r.top3_share, 'r'); add('F2 concentration', r.dimension + ' - HHI', x.hhi, r.hhi, 'r'); });
  const pers = persistence(), f5 = rt('f5_persistent_cells'); add('F5 persistence', 'Cells with >=12 months', pers.length, f5.length, 'n');
  const pm = {}; pers.forEach(t => pm[P.ents[t.e].c + '|' + P.gls[t.g].gl] = t); let bad = 0; f5.forEach(r => { const t = pm[r.entity_code + '|' + r.gl_account]; if (!t || t.months !== r.months_with_data || t.above !== r.months_above || t.below !== r.months_below || Math.abs(t.v - r.variance_usd) > 0.01) bad++; });
  add('F5 persistence', 'Cells whose months/above/below/variance all match', f5.length - bad, f5.length, 'n');
  add('F5 persistence', 'Persistent cells (>=90% and >=3%)', pers.filter(t => t.persistent).length, f5.filter(r => r.dominant_direction_share >= 0.9 && r.variance_pct != null && Math.abs(r.variance_pct) >= 0.03).length, 'n');
  S = saveS; recompute(); RECON.list = L; return L;
}
function updateRecBadge() { const L = RECON.list, ok = L.filter(r => r.ok).length, b = $('#recBadge'); b.className = 'badge ' + (ok === L.length ? 'ok' : 'bad'); b.innerHTML = (ok === L.length ? '✓ ' : '⚠ ') + 'Baseline checks: ' + ok + '/' + L.length; b.title = 'Baseline checks: at DEFAULT filters the dashboard recomputes ' + L.length + ' values from the embedded lines and compares them with the embedded SQL analysis reference tables. This is NOT an automatic independent reconciliation of the filtered view you are looking at - see "Selection checks" for that.'; }
/* Selection checks: recompute the current selection a second, deliberately plain way from the raw payload (not through agg()/memoised
   engine paths) and compare. This detects internal inconsistency; it is not an independent external reference (that is the offline QA). */
function runSelChecks() {
  const L = []; const add = (d, a, b, tol) => L.push({ desc: d, a, b, ok: Math.abs(a - b) <= (tol == null ? 0.01 : tol) });
  let n = 0, rev = 0, cost = 0, nb = 0, vsum = 0; const secN = new Array(NS).fill(0);
  const E = S.ent.length ? S.ent : null, D = S.div.length ? S.div : null, SE = S.sec.length ? S.sec : null, G = S.gl.length ? S.gl : null, C = S.cc.length ? S.cc : null, xf = S.xf;
  for (let i = 0; i < N; i++) {
    const m = R.m[i], ok0 = S.years.includes(MY[m]) && S.qtrs.includes(MQ[m]) && m >= S.from && m <= S.to; if (!ok0) continue;
    const g = R.g[i], sec = GSI[g]; if (E && !E.includes(R.e[i])) continue; if (D && !D.includes(R.d[i])) continue; if (SE && !SE.includes(sec)) continue; if (G && !G.includes(g)) continue; if (C && !C.includes(R.c[i])) continue;
    if (xf && !((xf.dim === 'ent' && R.e[i] === xf.val) || (xf.dim === 'div' && R.d[i] === xf.val) || (xf.dim === 'sec' && sec === xf.val) || (xf.dim === 'gl' && g === xf.val) || (xf.dim === 'cc' && R.c[i] === xf.val) || (xf.dim === 'm' && m === xf.val))) continue;
    if (!scnPass(i, S.scale, S.dup, S.sign)) continue;
    const a = (S.scale === 'PARSED' && R.rs[i] > 0) || (S.scale === 'HIGH' && R.rs[i] === 2) ? PAr[i] : A0[i];
    n++; secN[sec]++; if (sec === 0) rev += a; else if (sec <= 3) cost += a;
    const bb = (S.scale === 'PARSED' && R.rs[i] > 0) || (S.scale === 'HIGH' && R.rs[i] === 2) ? PBr[i] : B0[i]; if (bb === bb) { nb++; vsum += a - bb; }
  }
  const a = agg(), st = statusTotals();
  add('Lines in scope', nInc, n, 0); add('Revenue', a.rev, rev); add('Cost base', a.cost, cost); add('Result proxy', a.res, rev - cost);
  add('Section line counts sum to lines in scope', a.sN.reduce((x, y) => x + y, 0), n, 0); add('Entity line counts sum to lines in scope', Array.from(a.eN).reduce((x, y) => x + y, 0), n, 0);
  add('Posted line count in the status table equals lines in scope', st.Posted.n, n, 0); add('Status-table Posted revenue equals revenue KPI', st.Posted.rev, rev);
  let mSum = 0; for (let m = 0; m < NM; m++) mSum += a.mS[m * NS]; add('Monthly revenue series sums to revenue', mSum, rev);
  const vbA = varBySection('ALL'); add('Net variance (all sections) equals sum of actual minus budget on budget-carrying lines', vbA.reduce((x, t) => x + t.net, 0), vsum, 0.05);
  const vc = varPopCounts(); add('Budget-comparison count (ALL) equals lines with a budget in scope', vc.ALL[0], nb, 0);
  return L;
}
function updateSelBadge() { const L = runSelChecks(), ok = L.filter(r => r.ok).length, b = $('#selBadge'); b.className = 'badge ' + (ok === L.length ? 'ok' : 'bad'); b.innerHTML = (ok === L.length ? '✓ ' : '⚠ ') + 'Selection checks: ' + ok + '/' + L.length; b.title = 'Internal consistency of the CURRENT selection: ' + L.length + ' totals recomputed a second way from the embedded lines. Not an independent external reconciliation - the offline QA suite (DASHBOARD_QA_REPORT.md) is the independent reference.'; window.__selChecks = L; }

/* ---------- render + bootstrap ---------- */
const built = {};
/* keep keyboard focus across a panel rebuild (a bar click re-renders the view) */
function captureFocus() {
  const a = document.activeElement; if (!a || a === document.body) return null;
  const ch = a.closest && a.closest('.chart');
  if (ch && a.classList.contains('bar')) return { sel: '#' + ch.id + ' .bar[data-k="' + a.dataset.k + '"]' };
  if (ch && a.classList.contains('ov')) return { sel: '#' + ch.id + ' .ov' };
  if (a.id) return { sel: '#' + a.id, ss: a.selectionStart, se: a.selectionEnd };
  if (a.dataset && a.dataset.tbl) return { sel: '[data-tbl="' + a.dataset.tbl + '"]' };
  if (a.matches && a.matches('tr.clk')) { const k = Object.keys(a.dataset)[0]; return k ? { sel: 'tr.clk[data-' + k + '="' + a.dataset[k] + '"]' } : null; }
  return null;
}
function restoreFocus(f) { if (!f) return; const e = $(f.sel); if (e && e.tabIndex >= 0 && !e.disabled) { e.focus({ preventScroll: true }); if (f.ss != null && e.setSelectionRange) try { e.setSelectionRange(f.ss, f.se); } catch (x) { } } }
function buildPanel(id) {
  const fo = captureFocus(); const p = $("#p-" + id), v = VIEWS[id];
  p.innerHTML = (nInc === 0 && !['quality', 'insights'].includes(id)) ? emptyHtml() : v.html();
  if (nInc !== 0 || ['quality', 'insights'].includes(id)) { if (v.draw) v.draw(); }
  bindTblButtons(p); built[id] = version;
  $$('tr.clk', p).forEach(r => { r.tabIndex = 0; r.setAttribute('role', 'button'); r.onkeydown = e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); r.click(); } }; });
  restoreFocus(fo);
}
function renderActive(force) {
  TABS.forEach(([id]) => { $('#p-' + id).classList.toggle('on', id === S.tab); const t = $('#tab-' + id); t.setAttribute('aria-selected', id === S.tab); t.tabIndex = id === S.tab ? 0 : -1; });
  if (built[S.tab] !== version || force) buildPanel(S.tab);
}
function initTabs() {
  $('#tabs').innerHTML = TABS.map(([id, n]) => `<button class="tab" role="tab" id="tab-${id}" aria-controls="p-${id}" aria-selected="false">${esc(n)}</button>`).join('');
  TABS.forEach(([id]) => { $('#tab-' + id).onclick = () => { S.tab = id; renderActive(); const u = new URL(location.href); try { history.replaceState(null, '', '#' + id); } catch (e) { } }; });
  $('#tabs').onkeydown = e => { if (e.key !== 'ArrowRight' && e.key !== 'ArrowLeft') return; const ids = TABS.map(t => t[0]); let k = ids.indexOf(S.tab) + (e.key === 'ArrowRight' ? 1 : -1); k = (k + ids.length) % ids.length; S.tab = ids[k]; renderActive(); $('#tab-' + ids[k]).focus(); };
}
function themeNow() { const a = document.documentElement.getAttribute('data-theme'); return a || (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'); }
function syncTheme() { $('#themeLbl').textContent = themeNow() === 'dark' ? 'Light mode' : 'Dark mode'; }
function toggleTheme() { const t = themeNow() === 'dark' ? 'light' : 'dark'; document.documentElement.setAttribute('data-theme', t); try { localStorage.setItem('fpa-theme', t); } catch (e) { } syncTheme(); }
let printPrev = null;
function beforePrint() { printing = true; printPrev = document.documentElement.getAttribute('data-theme'); document.documentElement.setAttribute('data-theme', 'light'); TABS.forEach(([id]) => { if (id !== S.tab || built[id] !== version) buildPanel(id); }); $$('details.ins, details.basis').forEach(d => d.open = true); }
function afterPrint() { if (printPrev) document.documentElement.setAttribute('data-theme', printPrev); else document.documentElement.removeAttribute('data-theme'); printPrev = null; syncTheme(); Object.keys(built).forEach(k => built[k] = -1); $('#scope').innerHTML = scopeHtml(); bindBasis(); renderActive(true); setTimeout(() => { printing = false; }, 200); }

(function boot() {
  const t0 = performance.now();
  initFilters(); initTabs();
  const h = location.hash.slice(1); if (TABS.some(t => t[0] === h)) S.tab = h;
  recompute(); runRecon(); updateRecBadge(); syncFilters(); updateSelBadge(); syncTheme(); renderActive(true);
  $('#btnTheme').onclick = toggleTheme; $('#btnCsv').onclick = exportCsv; $('#btnPrint').onclick = () => { beforePrint(); setTimeout(() => { window.print(); }, 50); };
  addEventListener('beforeprint', () => { if (printPrev === null) beforePrint(); }); addEventListener('afterprint', afterPrint);
  matchMedia('(prefers-color-scheme: dark)').addEventListener('change', syncTheme);
  let rs; addEventListener('resize', () => { clearTimeout(rs); rs = setTimeout(() => { Object.keys(built).forEach(k => { if (k !== S.tab) built[k] = -1; }); renderActive(true); }, 200); });
  window.__fpa = { chart: id => { const w = wiring[id]; if (!w) return null; const nn = v => (v == null || v !== v) ? null : v; return w.type === 'line' ? { type: 'line', labels: w.labels, series: w.series.map(x => ({ name: x.name, vals: Array.from(x.vals, nn) })) } : { type: 'bar', items: w.items.map(it => ({ key: it.key, label: it.label, val: nn(it.val), dis: !!it.dis, noSel: !!it.noSel })) }; }, chartsInfo, costAbs, concentration, pyAgg, varCells, statusTotals, xfOK, elig, selChecks: () => window.__selChecks, scopeHtml, varPopCounts, S: () => S, N, nInc: () => nInc, recon: () => RECON.list, loadMs: performance.now() - t0, setState: (fn) => mutate(fn), exportCsv: buildCsv, scenarioTable, varBySection, fcPops, agg, persistence, gpAgg, runRecon, VIEWS, UI, render: () => renderActive(true), version: () => version };
})();
