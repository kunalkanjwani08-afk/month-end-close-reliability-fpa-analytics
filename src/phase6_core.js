'use strict';
/* ===== NovaBridge FP&A dashboard - core: data, state, engine, charts, filters ===== */
const P = DATA, R = P.R, N = R.a.length;
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));
const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const MINUS = '−';
const NaNs = x => x == null ? NaN : x;

/* ---------- formatting ---------- */
function fmtUsd(v, full) {
  if (v == null || !isFinite(v)) return 'n/a';
  const a = Math.abs(v), s = v < 0 ? MINUS : '';
  if (full) return s + '$' + Math.round(a).toLocaleString('en-US');
  if (a >= 1e9) return s + '$' + (a / 1e9).toFixed(2) + 'B';
  if (a >= 1e6) return s + '$' + (a / 1e6).toFixed(2) + 'M';
  if (a >= 1e3) return s + '$' + (a / 1e3).toFixed(1) + 'K';
  return s + '$' + a.toFixed(0);
}
function fmtAx(v){ if(v==null||!isFinite(v))return ''; const a=Math.abs(v),s=v<0?MINUS:''; if(a>=1e9)return s+'$'+(a/1e9).toFixed(a%1e9?1:0)+'B'; if(a>=1e6)return s+'$'+(+(a/1e6).toFixed(2))+'M'; if(a>=1e3)return s+'$'+(+(a/1e3).toFixed(1))+'K'; return s+'$'+a.toFixed(0); }
function fmtUsdS(v) { if (v == null || !isFinite(v)) return 'n/a'; return (v > 0 ? '+' : '') + fmtUsd(v); }
function fmtPct(v, d = 1) { if (v == null || !isFinite(v)) return 'n/a'; return (v < 0 ? MINUS : '') + Math.abs(v * 100).toFixed(d) + '%'; }
function fmtPctS(v, d = 1) { if (v == null || !isFinite(v)) return 'n/a'; return (v > 0 ? '+' : '') + fmtPct(v, d); }
function fmtInt(v) { return v == null || !isFinite(v) ? 'n/a' : (v < 0 ? MINUS : '') + Math.abs(Math.round(v)).toLocaleString('en-US'); }
function fmtPp(v) { return v == null || !isFinite(v) ? 'n/a' : (v > 0 ? '+' : v < 0 ? MINUS : '') + Math.abs(v * 100).toFixed(1) + ' pp'; }
/* variance % published only if |net budget| >= 50% of gross absolute budget (Phase 4 safe_pct) */
function safePct(num, den, denAbs) { return denAbs > 0 && Math.abs(den) >= 0.5 * denAbs ? num / Math.abs(den) : null; }
const MN = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
const mLabel = m => MN[(+P.months[m].slice(5)) - 1] + ' ' + P.months[m].slice(2, 4);

/* ---------- typed data ---------- */
const mk = a => Float64Array.from(a, NaNs);
const A0 = mk(R.a), B0 = mk(R.b), F0 = mk(R.f), P0 = mk(R.p);
const PAr = A0.slice(), PBr = B0.slice(), PFr = F0.slice(), PPr = P0.slice();
for (const k in P.parsed) { const v = P.parsed[k], i = +k; PAr[i] = NaNs(v[0]); PBr[i] = NaNs(v[1]); PFr[i] = NaNs(v[2]); PPr[i] = NaNs(v[3]); }
const Ei = Int8Array.from(R.e), Di = Int8Array.from(R.d), Gi = Int16Array.from(R.g), Ci = Int16Array.from(R.c), Mi = Int8Array.from(R.m);
const SAB = Int8Array.from(R.sab), SAF = Int8Array.from(R.saf), SAP = Int8Array.from(R.sap), RS = Int8Array.from(R.rs), DP = Int8Array.from(R.dp), SG = Int8Array.from(R.sg);
const NS = P.secs.length, NG = P.gls.length, NE = P.ents.length, ND = P.divs.length, NC = P.ccs.length, NM = P.months.length;
const SECI = {}; P.secs.forEach((s, i) => SECI[s] = i);
const GSI = P.gls.map(g => SECI[g.sec]);
const SEC = Int8Array.from(Gi, g => GSI[g]);
const MY = P.months.map(m => +m.slice(0, 4)), MQ = P.months.map(m => Math.ceil(+m.slice(5) / 3));
const YEARS = [...new Set(MY)];
const GL4190 = P.gls.findIndex(g => g.gl === 4190);
const SECN = { 'REVENUE': 'Revenue', 'COGS': 'COGS', 'PEOPLE': 'People', 'OPEX': 'Opex', 'D&A': 'D&A', 'BELOW_EBITDA': 'Below EBITDA', 'TAX': 'Tax' };
const secName = s => SECN[s] || s;
const SC = { rev: 0, cogs: 1, ppl: 2, opx: 3, da: 4 };
const COSTBASE = [1, 2, 3];       /* COGS + People + Opex -> result proxy */
const COSTSET = [1, 2, 3, 4];     /* + D&A -> Pareto / concentration population */
const SERCOL = i => `var(--s${(i % 8) + 1})`;

/* ---------- state (single source of truth) ---------- */
const DEF = () => ({ years: YEARS.slice(), qtrs: [1, 2, 3, 4], from: 0, to: NM - 1, ent: [], div: [], sec: [], gl: [], cc: [], xf: null, varPop: 'ALL', scale: 'ADJ', dup: 'KEEP', sign: 'KEEP', tab: 'overview' });
let S = DEF(); const hist = []; let version = 0;
const VARPOP = { ALL: -1, SAME: 0, OPP: 1, ZERO: 2 };
const VARPOP_LBL = { ALL: 'All comparable lines', SAME: 'Same-sign lines only', OPP: 'Opposite-sign lines only', ZERO: 'Zero-involved lines only' };
const SCALE_LBL = { ADJ: 'Adjusted, all (baseline)', PARSED: 'As reported (no restoration)', HIGH: 'Restore HIGH confidence only', EXCL_MED: 'Exclude MEDIUM-confidence restored', EXCL_ALL: 'Exclude all restored rows' };
const DUP_LBL = { KEEP: 'Candidates retained (baseline)', EXCL_SAME: 'Exclude same-sign candidates', EXCL_ALL: 'Exclude all copy candidates' };
const SIGN_LBL = { KEEP: 'Signs as recorded (baseline)', NONNEG: 'All-non-negative rows only', EXCL_FLIP: 'Exclude single-column sign flips' };

/* ---------- engine ---------- */
let MON = new Uint8Array(NM);
let inc = new Uint8Array(N), dimPass = new Uint8Array(N), nInc = 0;
const effCache = {};
function eff(mode) {
  if (effCache[mode]) return effCache[mode];
  let r;
  if (mode === 'PARSED' || mode === 'HIGH') {
    const pick = mode === 'PARSED' ? (i => RS[i] > 0) : (i => RS[i] === 2);
    const mkE = (adj, par) => { const o = adj.slice(); for (let i = 0; i < N; i++) if (pick(i)) o[i] = par[i]; return o; };
    r = { A: mkE(A0, PAr), B: mkE(B0, PBr), F: mkE(F0, PFr), P: mkE(P0, PPr) };
  } else r = { A: A0, B: B0, F: F0, P: P0 };
  return effCache[mode] = r;
}
let EA = A0, EB = B0, EF = F0, EP = P0;
function scnPass(i, scale, dup, sign) {
  if (scale === 'EXCL_ALL' && RS[i] > 0) return false;
  if (scale === 'EXCL_MED' && RS[i] === 2) return false;
  if (dup === 'EXCL_SAME' && DP[i] === 1) return false;
  if (dup === 'EXCL_ALL' && DP[i] >= 1) return false;
  if (sign === 'NONNEG' && SG[i] !== 0) return false;
  if (sign === 'EXCL_FLIP' && SG[i] === 2) return false;
  return true;
}
/* BASE = every filter + scenario EXCEPT the chart selection; XFM = chart-selection match; inc = BASE && XFM */
let BASE = new Uint8Array(N), XFM = new Uint8Array(N);
function recompute() {
  const mm = new Uint8Array(NM);
  for (let m = 0; m < NM; m++) mm[m] = S.years.includes(MY[m]) && S.qtrs.includes(MQ[m]) && m >= S.from && m <= S.to ? 1 : 0;
  const E = S.ent.length ? new Set(S.ent) : null, D = S.div.length ? new Set(S.div) : null, SE = S.sec.length ? new Set(S.sec) : null,
    G = S.gl.length ? new Set(S.gl) : null, C = S.cc.length ? new Set(S.cc) : null, xf = S.xf;
  MON = mm; nInc = 0;
  for (let i = 0; i < N; i++) {
    let ok = mm[Mi[i]] === 1;
    if (ok && E && !E.has(Ei[i])) ok = false;
    if (ok && D && !D.has(Di[i])) ok = false;
    if (ok && SE && !SE.has(SEC[i])) ok = false;
    if (ok && G && !G.has(Gi[i])) ok = false;
    if (ok && C && !C.has(Ci[i])) ok = false;
    let xm = 1;
    if (xf) {
      const v = xf.val;
      if (xf.dim === 'ent') xm = Ei[i] === v ? 1 : 0;
      else if (xf.dim === 'div') xm = Di[i] === v ? 1 : 0;
      else if (xf.dim === 'sec') xm = SEC[i] === v ? 1 : 0;
      else if (xf.dim === 'gl') xm = Gi[i] === v ? 1 : 0;
      else if (xf.dim === 'cc') xm = Ci[i] === v ? 1 : 0;
      else if (xf.dim === 'm') xm = Mi[i] === v ? 1 : 0;
    }
    const sp = ok && scnPass(i, S.scale, S.dup, S.sign);
    BASE[i] = sp ? 1 : 0; XFM[i] = xm;
    dimPass[i] = ok && xm ? 1 : 0;
    const f = sp && xm === 1;
    inc[i] = f ? 1 : 0;
    if (f) nInc++;
  }
  const e = eff(S.scale); EA = e.A; EB = e.B; EF = e.F; EP = e.P;
  cache = {};
}
let cache = {};
const memo = (k, fn) => (k in cache) ? cache[k] : (cache[k] = fn());
/* ---------- chart cross-filter eligibility ----------
   A category is selectable only if at least one line would remain. Counts use every slicer and scenario, and the
   current chart selection on OTHER dimensions; the chart selection on the same dimension is ignored so the active
   bar can be switched off and sibling bars stay comparable. */
const XDIM = { ent: [Ei, NE, 0], div: [Di, ND, 0], sec: [SEC, NS, 0], gl: [Gi, NG, 0], cc: [Ci, NC + 1, 1], m: [Mi, NM, 0] };
const XDIM_NAME = { ent: 'Entity', div: 'Division', sec: 'Section', gl: 'GL account', cc: 'Cost centre', m: 'Month' };
function elig(dim) {
  return memo('elig:' + dim, () => {
    const [arr, size, off] = XDIM[dim], o = new Int32Array(size), xf = S.xf, same = xf && xf.dim === dim;
    for (let i = 0; i < N; i++) if (BASE[i] && (!xf || same || XFM[i])) o[arr[i] + off]++;
    return o;
  });
}
const xfOK = (dim, key) => { const d = XDIM[dim]; return !!d && key + d[2] >= 0 && key + d[2] < d[1] && elig(dim)[key + d[2]] > 0; };
function xfWhyNot(dim, key) {
  const f = dim === 'm' ? null : S[dim];
  if (f && f.length && !f.includes(key)) return 'it is excluded by the ' + XDIM_NAME[dim] + ' filter (remove or change that filter first)';
  if (dim === 'm') return 'that month is outside the selected period';
  return 'no lines remain under the other active filters and scenarios';
}
let noticeMsg = '', noticeTimer = null;
function notify(msg) {
  noticeMsg = msg; const n = $('#notice'); if (!n) return;
  n.textContent = msg; n.hidden = !msg; clearTimeout(noticeTimer);
  if (msg) noticeTimer = setTimeout(() => { if (noticeMsg === msg) { noticeMsg = ''; n.hidden = true; n.textContent = ''; } }, 12000);
}

/* base aggregates for the current filter */
function agg() {
  return memo('agg', () => {
    const o = {
      sN: new Int32Array(NS), sS: new Float64Array(NS), sA: new Float64Array(NS),
      mS: new Float64Array(NM * NS), mN: new Int32Array(NM * NS), eS: new Float64Array(NE * NS), dS: new Float64Array(ND * NS),
      gS: new Float64Array(NG), gA: new Float64Array(NG), gN: new Int32Array(NG),
      cS: new Float64Array((NC + 1) * NS), cA: new Float64Array((NC + 1) * NS),
      yS: new Float64Array(YEARS.length * NS), yA: new Float64Array(YEARS.length * NS), yN: new Int32Array(YEARS.length * NS),
      eN: new Int32Array(NE), dN: new Int32Array(ND)
    };
    for (let i = 0; i < N; i++) {
      if (!inc[i]) continue;
      const s = SEC[i], a = EA[i], aa = Math.abs(a), m = Mi[i], y = (MY[m] - YEARS[0]);
      o.sN[s]++; o.sS[s] += a; o.sA[s] += aa;
      o.mS[m * NS + s] += a; o.mN[m * NS + s]++;
      o.eS[Ei[i] * NS + s] += a; o.dS[Di[i] * NS + s] += a; o.eN[Ei[i]]++; o.dN[Di[i]]++;
      const g = Gi[i]; o.gS[g] += a; o.gA[g] += aa; o.gN[g]++;
      const c = (Ci[i] + 1) * NS + s; o.cS[c] += a; o.cA[c] += aa;
      o.yS[y * NS + s] += a; o.yA[y * NS + s] += aa; o.yN[y * NS + s]++;
    }
    o.rev = o.sS[0]; o.cost = o.sS[1] + o.sS[2] + o.sS[3]; o.res = o.rev - o.cost;
    return o;
  });
}

/* variance cells (entity x GL x month) for a sign population */
function varCells(pop) {
  return memo('vc' + pop, () => {
    const NCELL = NE * NG * NM, act = new Float64Array(NCELL), bud = new Float64Array(NCELL), cnt = new Int32Array(NCELL);
    const want = VARPOP[pop];
    for (let i = 0; i < N; i++) {
      if (!inc[i]) continue;
      const b = EB[i]; if (b !== b) continue;
      if (want >= 0 && SAB[i] !== want) continue;
      const id = (Ei[i] * NG + Gi[i]) * NM + Mi[i];
      act[id] += EA[i]; bud[id] += b; cnt[id]++;
    }
    return { act, bud, cnt };
  });
}
function cellIter(vc, fn) {
  for (let e = 0; e < NE; e++) for (let g = 0; g < NG; g++) for (let m = 0; m < NM; m++) {
    const id = (e * NG + g) * NM + m; if (vc.cnt[id]) fn(e, g, m, vc.act[id], vc.bud[id], vc.cnt[id]);
  }
}
/* variance summary per section: rows, actual, budget, net variance, gross cell variance, abs budget, pct */
function varBySection(pop) {
  return memo('vs' + pop, () => {
    const vc = varCells(pop), o = Array.from({ length: NS }, () => ({ n: 0, act: 0, bud: 0, net: 0, gross: 0, absBud: 0 }));
    cellIter(vc, (e, g, m, a, b, n) => { const t = o[GSI[g]]; t.n += n; t.act += a; t.bud += b; t.net += a - b; t.gross += Math.abs(a - b); t.absBud += Math.abs(b); });
    o.forEach(t => { t.pct = safePct(t.net, t.bud, t.absBud); t.grossPct = t.absBud > 0 ? t.gross / t.absBud : null; t.netting = t.absBud > 0 ? Math.abs(t.bud) / t.absBud : null; });
    return o;
  });
}
function tot(o, idx) { const t = { n: 0, act: 0, bud: 0, net: 0, gross: 0, absBud: 0 }; idx.forEach(s => { const x = o[s]; t.n += x.n; t.act += x.act; t.bud += x.bud; t.net += x.net; t.gross += x.gross; t.absBud += x.absBud; }); t.pct = safePct(t.net, t.bud, t.absBud); return t; }

/* forecast populations: A matched same-sign, B comparable (budget+forecast, any sign), C all forecast lines */
function fcPops() {
  return memo('fc', () => {
    const z = () => ({ n: 0, errF: 0, errB: 0, signedF: 0, signedB: 0, absA: 0 });
    const o = { A: Array.from({ length: NS }, z), B: Array.from({ length: NS }, z), C: Array.from({ length: NS }, z), cat: Array.from({ length: NS }, () => Array.from({ length: 4 }, () => ({ n: 0, abs: 0 }))), q: {} };
    for (let i = 0; i < N; i++) {
      if (!inc[i]) continue;
      const f = EF[i]; if (f !== f) continue;
      const s = SEC[i], a = EA[i], b = EB[i], aa = Math.abs(a), ef = f - a;
      let t = o.C[s]; t.n++; t.errF += Math.abs(ef); t.signedF += ef; t.absA += aa;
      const k = o.cat[s][SAF[i]]; k.n++; k.abs += Math.abs(ef);
      if (b === b) {
        const eb = b - a;
        t = o.B[s]; t.n++; t.errF += Math.abs(ef); t.errB += Math.abs(eb); t.signedF += ef; t.signedB += eb; t.absA += aa;
        if (SAB[i] === 0 && SAF[i] === 0) { t = o.A[s]; t.n++; t.errF += Math.abs(ef); t.errB += Math.abs(eb); t.signedF += ef; t.signedB += eb; t.absA += aa; }
        const qk = s + '|' + MY[Mi[i]] + 'Q' + MQ[Mi[i]]; const qq = o.q[qk] || (o.q[qk] = { n: 0, errF: 0, errB: 0, absA: 0 }); qq.n++; qq.errF += Math.abs(ef); qq.errB += Math.abs(eb); qq.absA += aa;
      }
    }
    return o;
  });
}
/* prior-year column comparison by year x section for a sign population */
function pyAgg(pop) {
  return memo('py' + pop, () => {
    const want = pop === 'ALL' ? -1 : VARPOP[pop], o = {};
    for (let i = 0; i < N; i++) {
      if (!inc[i]) continue; const p = EP[i]; if (p !== p) continue;
      if (want >= 0 && SAP[i] !== want) continue;
      const k = MY[Mi[i]] + '|' + SEC[i]; const t = o[k] || (o[k] = { n: 0, act: 0, py: 0, absPy: 0 });
      t.n++; t.act += EA[i]; t.py += p; t.absPy += Math.abs(p);
    }
    return o;
  });
}
/* persistent deviators (Phase 4 F5): entity x GL, same-sign lines, >=12 months, dominant side >=90%, |variance %| >=3% */
function persistence() {
  return memo('pers', () => {
    const vc = varCells('SAME'), cells = {};
    cellIter(vc, (e, g, m, a, b) => { const k = e * NG + g; const t = cells[k] || (cells[k] = { e, g, v: 0, bud: 0, absBud: 0, months: 0, above: 0, below: 0 }); const v = a - b; t.v += v; t.bud += b; t.absBud += Math.abs(b); t.months++; if (v > 0) t.above++; else if (v < 0) t.below++; });
    const all = Object.values(cells).filter(t => t.months >= 12);
    all.forEach(t => { t.share = Math.max(t.above, t.below) / t.months; t.pct = safePct(t.v, t.bud, t.absBud); t.dir = t.above >= t.below ? 'above' : 'below'; t.persistent = t.share >= 0.9 && t.pct != null && Math.abs(t.pct) >= 0.03; });
    return all;
  });
}
/* gross profit (Phase 4 section E): treatments S1/S2/S3 over ROWS_ALL or ROWS_ALL_NON_NEGATIVE */
const GP_T = [{ k: 'S1', name: 'S1 - signed as recorded', rule: 'Revenue as recorded, including discount GL 4190 with its recorded sign.' },
{ k: 'S2', name: 'S2 - discount at -abs', rule: 'Discount GL 4190 forced to a negative magnitude (-|amount|) before summing.' },
{ k: 'S3', name: 'S3 - excluding discount', rule: 'Discount GL 4190 left out of revenue.' }];
function gpRev(t, i, v) { if (Gi[i] !== GL4190) return v; return t === 0 ? v : t === 1 ? -Math.abs(v) : 0; }
function gpAgg(rowset) {
  return memo('gp' + rowset, () => {
    const o = GP_T.map(() => ({ rev: 0, cogs: 0, n: 0, yr: YEARS.map(() => ({ rev: 0, cogs: 0, n: 0 })), ent: P.ents.map(() => ({ rev: 0, cogs: 0 })), vb: { aRev: 0, bRev: 0, aCogs: 0, bCogs: 0, n: 0 } }));
    for (let i = 0; i < N; i++) {
      if (!inc[i]) continue; const s = SEC[i]; if (s !== 0 && s !== 1) continue;
      const nn = rowset === 'NONNEG' ? SG[i] === 0 : true; const y = MY[Mi[i]] - YEARS[0];
      const sm = SAB[i] === 0 && EB[i] === EB[i];
      for (let t = 0; t < 3; t++) {
        const T = o[t];
        if (nn) {
          if (s === 0) { const v = gpRev(t, i, EA[i]); T.rev += v; T.yr[y].rev += v; T.ent[Ei[i]].rev += v; } else { T.cogs += EA[i]; T.yr[y].cogs += EA[i]; T.ent[Ei[i]].cogs += EA[i]; }
          T.n++; T.yr[y].n++;
        }
        if (sm) { if (s === 0) { T.vb.aRev += gpRev(t, i, EA[i]); T.vb.bRev += gpRev(t, i, EB[i]); } else { T.vb.aCogs += EA[i]; T.vb.bCogs += EB[i]; } T.vb.n++; }
      }
    }
    return o;
  });
}

/* ---------- state mutation + undo ---------- */
function mutate(fn) { notify(''); hist.push(JSON.stringify(S)); if (hist.length > 60) hist.shift(); fn(S); changed(); }
function undo() { if (!hist.length) return; notify(''); const tab = S.tab; S = JSON.parse(hist.pop()); S.tab = tab; changed(true); }
function resetAll() { mutate(s => { const t = s.tab; Object.assign(s, DEF()); s.tab = t; }); }
/* Chart / table-row selection. One code path for mouse, keyboard and table rows. Returns true if the state changed. */
function setXf(dim, val, label) {
  const cur = S.xf;
  if (cur && cur.dim === dim && cur.val === val) { mutate(s => { s.xf = null; }); return true; }
  if (!xfOK(dim, val)) { notify('Not selectable: ' + label.replace(/^[^=]+= /, '') + ' has no lines because ' + xfWhyNot(dim, val) + '.'); return false; }
  mutate(s => { s.xf = { dim, val, label }; }); return true;
}
function changed(fromUndo) {
  recompute();
  /* a chart selection that no longer has any lines (e.g. a slicer moved away from it) is cleared with a notice, never left as an empty result */
  if (S.xf && !xfOK(S.xf.dim, S.xf.val)) { const l = S.xf.label; S.xf = null; recompute(); notify('Chart selection removed (' + l + '): ' + 'no lines remain for it under the current filters.'); }
  version++; syncFilters(); if (typeof updateSelBadge === 'function') updateSelBadge(); renderActive();
}

/* ---------- tooltip ---------- */
const TT = $('#tt');
function showTT(html, ev) {
  TT.innerHTML = html; TT.style.display = 'block';
  const w = TT.offsetWidth, h = TT.offsetHeight; let x = ev.clientX + 14, y = ev.clientY + 14;
  if (x + w > innerWidth - 8) x = ev.clientX - w - 14; if (y + h > innerHeight - 8) y = ev.clientY - h - 14;
  TT.style.left = Math.max(4, x) + 'px'; TT.style.top = Math.max(4, y) + 'px';
}
const hideTT = () => TT.style.display = 'none';

/* ---------- charts (inline SVG) ---------- */
function niceTicks(lo, hi, n = 5) {
  if (lo === hi) { hi = lo + 1; }
  const span = hi - lo, raw = span / n, mag = Math.pow(10, Math.floor(Math.log10(raw))), f = raw / mag;
  const step = (f < 1.5 ? 1 : f < 3 ? 2 : f < 7 ? 5 : 10) * mag, a = Math.floor(lo / step) * step, b = Math.ceil(hi / step) * step, t = [];
  for (let v = a; v <= b + step / 2; v += step) t.push(Math.abs(v) < step * 1e-9 ? 0 : v);
  return t;
}
const chartReg = {}, tblMode = {};
function tableHtml(t) {
  return `<div class="tw" style="max-height:320px"><table><thead><tr>${t.cols.map((c, i) => `<th class="${i ? 'r' : ''}">${esc(c)}</th>`).join('')}</tr></thead><tbody>${t.rows.map(r => `<tr>${r.map((c, i) => `<td class="${i ? 'r' : ''}">${esc(c)}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`;
}
function mountChart(id, svgOrHtml, table) {
  const h = $('#' + id); if (!h) return;
  chartReg[id] = { svg: svgOrHtml, table };
  h.innerHTML = tblMode[id] ? tableHtml(table) : svgOrHtml;
  const b = $(`[data-tbl="${id}"]`); if (b) b.textContent = tblMode[id] ? 'Chart' : 'Table';
}
function bindTblButtons(root) {
  $$('[data-tbl]', root).forEach(b => b.onclick = () => { const id = b.dataset.tbl; tblMode[id] = !tblMode[id]; const r = chartReg[id]; if (r) { $('#' + id).innerHTML = tblMode[id] ? tableHtml(r.table) : r.svg; b.textContent = tblMode[id] ? 'Chart' : 'Table'; if (!tblMode[id]) wireCharts(); } });
}
let wiring = {};   /* id -> {type, ...} for event wiring after SVG insertion */
function wireCharts() {
  Object.keys(wiring).forEach(id => {
    const h = $('#' + id); if (!h) return; const w = wiring[id];
    if (w.type === 'line') {
      const ov = h.querySelector('.ov'); if (!ov) return; const cross = h.querySelector('.cross'); const dots = $$('.dot', h);
      const showAt = (k, ev) => {
        const px = w.l + (w.n === 1 ? 0 : k * (w.W - w.l - w.r) / (w.n - 1));
        cross.setAttribute('x1', px); cross.setAttribute('x2', px); cross.style.display = ''; dots.forEach(d => { const s = +d.dataset.s; const v = w.series[s].vals[k]; if (v == null || v !== v) { d.style.display = 'none'; return; } d.style.display = ''; d.setAttribute('cx', px); d.setAttribute('cy', w.y(v)); });
        showTT(`<b>${esc(w.labels[k])}</b>` + w.series.map((s, si) => `<div>${legendSwatch('line', si, s.color, s.dash)} ${esc(s.name)}: <b style="display:inline">${esc(w.fmt(s.vals[k]))}</b></div>`).join(''), ev);
      };
      const idxAt = ev => { const r = ov.getBoundingClientRect(); const x = (ev.clientX - r.left) / r.width * w.W; let k = Math.round((x - w.l) / (w.W - w.l - w.r) * (w.n - 1)); return Math.max(0, Math.min(w.n - 1, k)); };
      ov.onmousemove = ev => { w.k = idxAt(ev); showAt(w.k, ev); };
      ov.onmouseleave = () => { cross.style.display = 'none'; dots.forEach(d => d.style.display = 'none'); hideTT(); };
      if (w.onPoint) ov.onclick = ev => { hideTT(); w.onPoint(idxAt(ev)); };
      /* keyboard parity: arrows step through periods, Enter/Space selects (same guarded path as a click) */
      const kev = k => { const r = ov.getBoundingClientRect(); return { clientX: r.left + r.width * (w.l + (w.n === 1 ? 0 : k * (w.W - w.l - w.r) / (w.n - 1)) - w.l) / (w.W - w.l - w.r), clientY: r.top + 10 }; };
      ov.onfocus = () => { if (w.k == null) w.k = w.n - 1; showAt(w.k, kev(w.k)); };
      ov.onblur = () => ov.onmouseleave();
      ov.onkeydown = ev => {
        if (ev.key === 'ArrowLeft' || ev.key === 'ArrowRight' || ev.key === 'Home' || ev.key === 'End') { ev.preventDefault(); w.k = ev.key === 'Home' ? 0 : ev.key === 'End' ? w.n - 1 : Math.max(0, Math.min(w.n - 1, (w.k == null ? w.n - 1 : w.k) + (ev.key === 'ArrowRight' ? 1 : -1))); showAt(w.k, kev(w.k)); }
        else if ((ev.key === 'Enter' || ev.key === ' ') && w.onPoint) { ev.preventDefault(); hideTT(); w.onPoint(w.k == null ? w.n - 1 : w.k); }
      };
    } else if (w.type === 'bar') {
      $$('.bar', h).forEach(el => {
        const k = +el.dataset.k, it = w.items[k];
        el.onmousemove = ev => showTT((it.tip || `<b>${esc(it.label)}</b>${esc(w.fmt(it.val))}`) + (it.dis ? '<div style="color:var(--muted)">Not selectable &mdash; no lines in the current selection</div>' : ''), ev);
        el.onmouseleave = hideTT;
        if (w.onClick && !it.noSel) { el.onclick = () => { hideTT(); w.onClick(it); }; el.onkeydown = ev => { if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); w.onClick(it); } }; }
      });
    }
  });
}
/* secondary encodings so identity never relies on colour alone: dash pattern + marker shape per series slot */
const DASHES = ['', '7 4', '2 3', '9 3 2 3', '', '7 4', '2 3', '9 3 2 3'];
const MARKERS = ['c', 's', 't', 'd'];
function markerSvg(shape, x, y, r, col, extra = '') {
  const st = `fill="${col}" stroke="var(--surface)" stroke-width="2"${extra}`;
  if (shape === 's') return `<rect x="${x - r}" y="${y - r}" width="${2 * r}" height="${2 * r}" ${st}/>`;
  if (shape === 't') return `<path d="M${x} ${y - r - 1}L${x + r + 1} ${y + r}L${x - r - 1} ${y + r}Z" ${st}/>`;
  if (shape === 'd') return `<path d="M${x} ${y - r - 1}L${x + r + 1} ${y}L${x} ${y + r + 1}L${x - r - 1} ${y}Z" ${st}/>`;
  return `<circle cx="${x}" cy="${y}" r="${r}" ${st}/>`;
}
function legendSwatch(kind, si, col, dashOverride) {
  if (kind === 'line') {
    const da = dashOverride ? '5 4' : DASHES[si % 8];
    return `<svg class="swl" width="26" height="12" viewBox="0 0 26 12" aria-hidden="true"><line x1="1" x2="25" y1="6" y2="6" stroke="${col}" stroke-width="2.2" stroke-linecap="round"${da ? ` stroke-dasharray="${da}"` : ''}/>${markerSvg(MARKERS[si % 4], 13, 6, 3, col)}</svg>`;
  }
  if (kind === 'pat') return `<svg class="swl" width="14" height="12" viewBox="0 0 14 12" aria-hidden="true">${patFill(si, col, 'lg' + si)}<rect x="0" y="1" width="14" height="10" rx="2" fill="url(#pt-lg${si})"/></svg>`;
  return `<span class="sw" style="background:${col}"></span>`;
}
/* hatch/dot textures for bar series 2..n (series 1 stays solid) */
function patFill(k, col, id) {
  const bg = `<rect width="8" height="8" fill="${col}"/>`;
  const f = k % 4 === 1 ? '<path d="M-1 1L1 -1M0 8L8 0M7 9L9 7" stroke="var(--surface)" stroke-width="1.6"/>' : k % 4 === 2 ? '<circle cx="4" cy="4" r="1.4" fill="var(--surface)"/>' : k % 4 === 3 ? '<path d="M0 4H8" stroke="var(--surface)" stroke-width="1.6"/>' : '';
  return `<defs><pattern id="pt-${id}" width="8" height="8" patternUnits="userSpaceOnUse">${bg}${f}</pattern></defs>`;
}
function lineChart(id, o) {
  const h = $('#' + id); if (!h) return;
  const W = Math.max(320, h.clientWidth || 600), H = o.h || 250, l = 58, r = 14, t = 12, b = 26, n = o.labels.length;
  let lo = Infinity, hi = -Infinity; o.series.forEach(s => s.vals.forEach(v => { if (v != null && v === v) { lo = Math.min(lo, v); hi = Math.max(hi, v); } }));
  if (!isFinite(lo)) { lo = 0; hi = 1; } lo = Math.min(lo, 0); hi = Math.max(hi, 0);
  const ticks = niceTicks(lo, hi, 5); lo = ticks[0]; hi = ticks[ticks.length - 1];
  const y = v => t + (H - t - b) * (1 - (v - lo) / (hi - lo)), x = i => l + (n === 1 ? 0 : i * (W - l - r) / (n - 1));
  let s = `<svg viewBox="0 0 ${W} ${H}" width="100%" height="${H}" role="img" aria-label="${esc(o.aria || 'Line chart')}">`;
  ticks.forEach(v => { s += `<line class="${v === 0 ? 'ax' : 'gl'}" x1="${l}" x2="${W - r}" y1="${y(v)}" y2="${y(v)}"/><text x="${l - 6}" y="${y(v) + 4}" text-anchor="end">${esc(o.axisFmt ? o.axisFmt(v) : o.fmt(v))}</text>`; });
  const step = Math.ceil(n / Math.max(2, Math.floor((W - l - r) / 62)));
  o.labels.forEach((lb, i) => { if (i % step === 0) s += `<text x="${x(i)}" y="${H - 8}" text-anchor="middle">${esc(o.xShort ? o.xShort[i] : lb)}</text>`; });
  o.series.forEach((se, si) => {
    let d = '', pen = false;
    se.vals.forEach((v, i) => { if (v == null || v !== v) { pen = false; return; } d += (pen ? 'L' : 'M') + x(i).toFixed(1) + ' ' + y(v).toFixed(1); pen = true; });
    s += `<path d="${d}" fill="none" stroke="${se.color}" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"${(se.dash || DASHES[si % 8]) ? ` stroke-dasharray="${se.dash ? '5 4' : DASHES[si % 8]}"` : ''}/>`;
    if (n <= 14) se.vals.forEach((v, i) => { if (v != null && v === v) s += markerSvg(MARKERS[si % 4], x(i), y(v), 3.2, se.color); });
  });
  s += `<line class="cross" x1="0" x2="0" y1="${t}" y2="${H - b}" stroke="var(--axis)" stroke-dasharray="3 3" style="display:none"/>`;
  o.series.forEach((se, si) => { s += `<circle class="dot" data-s="${si}" r="4.5" fill="${se.color}" stroke="var(--surface)" stroke-width="2" style="display:none"/>`; });
  s += `<rect class="ov" x="${l}" y="${t}" width="${W - l - r}" height="${H - t - b}" fill="transparent" tabindex="0" role="application" aria-label="${esc((o.aria || 'Line chart') + '. Left and right arrow keys move between periods' + (o.onPoint ? '; Enter selects the month.' : '.'))}" style="cursor:${o.onPoint ? 'pointer' : 'crosshair'}"/></svg>`;
  if (o.series.length > 1 || o.legend) s += `<div class="legend">${o.series.map((se, si) => `<span>${legendSwatch('line', si, se.color, se.dash)}${esc(se.name)}</span>`).join('')}</div>`;
  wiring[id] = { type: 'line', W, l, r, n, y, labels: o.labels, series: o.series, fmt: o.fmt, onPoint: o.onPoint };
  mountChart(id, s, { cols: ['Period', ...o.series.map(x => x.name)], rows: o.labels.map((lb, i) => [lb, ...o.series.map(x => o.fmt(x.vals[i]))]) });
  if (!tblMode[id]) wireCharts();
}
function barChart(id, o) {
  const h = $('#' + id); if (!h) return;
  const items = o.items, n = items.length, W = Math.max(320, h.clientWidth || 600);
  const xdim = o.xdim || (o.onClick && o.onClick.xdim);
  items.forEach(it => { it.dis = !!(o.onClick && xdim && !(o.selected != null && it.key === o.selected) && !xfOK(xdim, it.key)); });
  if (!n) { delete wiring[id]; mountChart(id, '<div class="empty">No data in the current selection.</div>', { cols: ['Item', 'Value'], rows: [] }); return; }
  let lo = 0, hi = 0; items.forEach(it => { if (it.val != null && it.val === it.val) { lo = Math.min(lo, it.val); hi = Math.max(hi, it.val); } });
  const sel = o.selected;
  const col = it => it.pat != null && it.pat % 4 ? `url(#pt-bp${it.pat})` : it.color || (o.signColors ? (it.val < 0 ? 'var(--neg)' : 'var(--pos)') : (o.color || 'var(--s1)'));
  const barAttr = (it, isSel, v) => `class="bar${it.dis ? ' dis' : ''}"${isSel ? ' stroke="var(--ink)" stroke-width="2"' : ''} tabindex="${o.onClick && !it.dis ? 0 : -1}" role="${o.onClick && !it.dis ? 'button' : 'img'}"${it.dis ? ' aria-disabled="true"' : ''}${isSel ? ' aria-pressed="true"' : o.onClick && !it.dis ? ' aria-pressed="false"' : ''} aria-label="${esc(it.label + ': ' + o.fmt(v) + (it.dis ? ' (not selectable: no lines in the current selection)' : ''))}"`;
  const pats = [...new Set(items.filter(it => it.pat != null && it.pat % 4).map(it => it.pat))].map(k => patFill(k, SERCOL(k), 'bp' + k)).join('');
  let s;
  if (o.horizontal !== false) {
    const rowH = o.rowH || 26, lm = Math.min(190, Math.max(60, Math.max(...items.map(i => i.label.length)) * 6.3 + 10)), rm = 74, H = n * rowH + 22;
    const ticks = niceTicks(lo, hi, 4); const a = ticks[0], bz = ticks[ticks.length - 1]; const x = v => lm + (W - lm - rm) * ((v - a) / (bz - a));
    s = `<svg viewBox="0 0 ${W} ${H}" width="100%" height="${H}" role="group" aria-label="${esc(o.aria || 'Bar chart')}">${pats}`;
    ticks.forEach(v => { s += `<line class="${v === 0 ? 'ax' : 'gl'}" x1="${x(v)}" x2="${x(v)}" y1="0" y2="${H - 18}"/><text x="${x(v)}" y="${H - 5}" text-anchor="middle">${esc(o.axisFmt ? o.axisFmt(v) : o.fmt(v))}</text>`; });
    items.forEach((it, k) => {
      const yy = k * rowH + 3, v = it.val, x0 = x(0), x1 = v == null || v !== v ? x0 : x(v), bx = Math.min(x0, x1), bw = Math.max(1, Math.abs(x1 - x0));
      const isSel = sel != null && it.key === sel;
      s += `<text x="${lm - 6}" y="${yy + rowH / 2 + 1}" text-anchor="end"${isSel ? ' style="font-weight:700;fill:var(--ink)"' : ''}>${esc(it.label)}</text>`;
      s += `<rect ${barAttr(it, isSel, v)} data-k="${k}" x="${bx}" y="${yy}" width="${bw}" height="${rowH - 8}" rx="3" fill="${col(it)}"/>`;
      const lx = v < 0 ? bx - 4 : bx + bw + 4; s += `<text x="${lx}" y="${yy + rowH / 2 - 2}" text-anchor="${v < 0 ? 'end' : 'start'}">${esc(o.fmt(v))}</text>`;
    });
    s += '</svg>';
  } else {
    const H = o.h || 240, l = 58, r = 10, t = 12, b = 28; const ticks = niceTicks(lo, hi, 5); const a = ticks[0], bz = ticks[ticks.length - 1];
    const y = v => t + (H - t - b) * (1 - (v - a) / (bz - a)), bw = (W - l - r) / n;
    s = `<svg viewBox="0 0 ${W} ${H}" width="100%" height="${H}" role="group" aria-label="${esc(o.aria || 'Column chart')}">${pats}`;
    ticks.forEach(v => { s += `<line class="${v === 0 ? 'ax' : 'gl'}" x1="${l}" x2="${W - r}" y1="${y(v)}" y2="${y(v)}"/><text x="${l - 6}" y="${y(v) + 4}" text-anchor="end">${esc(o.axisFmt ? o.axisFmt(v) : o.fmt(v))}</text>`; });
    const step = Math.ceil(n / Math.max(2, Math.floor((W - l - r) / 50)));
    items.forEach((it, k) => {
      const v = it.val; const y0 = y(0), y1 = v == null || v !== v ? y0 : y(v); const by = Math.min(y0, y1), bh = Math.max(1, Math.abs(y1 - y0)); const w = Math.max(2, bw * 0.7), bx = l + k * bw + (bw - w) / 2; const isSel = sel != null && it.key === sel;
      s += `<rect ${barAttr(it, isSel, v)} data-k="${k}" x="${bx}" y="${by}" width="${w}" height="${bh}" rx="2" fill="${col(it)}"/>`;
      if (k % step === 0) s += `<text x="${l + k * bw + bw / 2}" y="${H - 9}" text-anchor="middle">${esc(it.short || it.label)}</text>`;
    });
    s += '</svg>';
  }
  if (o.legend) s += `<div class="legend">${o.legend.map((l, li) => `<span>${legendSwatch('pat', li, l[1])}${esc(l[0])}</span>`).join('')}</div>`;
  wiring[id] = { type: 'bar', items, fmt: o.fmt, onClick: o.onClick, dim: xdim, sel: o.selected };
  mountChart(id, s, { cols: ['Item', 'Value'], rows: items.map(it => [it.label, o.fmt(it.val)]) });
  if (!tblMode[id]) wireCharts();
}
/* compact trend line for KPI cards: same hover / keyboard / click-to-filter wiring as the full line charts */
function sparkChart(id, o) {
  const h = $('#' + id); if (!h) return;
  const W = Math.max(120, h.clientWidth || 200), H = o.h || 46, l = 4, r = 4, t = 5, b = 5, n = o.labels.length, vals = o.vals;
  let lo = Infinity, hi = -Infinity; vals.forEach(v => { if (v != null && v === v) { lo = Math.min(lo, v); hi = Math.max(hi, v); } });
  if (!isFinite(lo)) { delete wiring[id]; mountChart(id, '<div class="spark-empty">No months in scope</div>', { cols: ['Period', o.name], rows: [] }); return; }
  if (o.zero) { lo = Math.min(lo, 0); hi = Math.max(hi, 0); } if (lo === hi) { lo -= 1; hi += 1; }
  const y = v => t + (H - t - b) * (1 - (v - lo) / (hi - lo)), x = i => l + (n === 1 ? 0 : i * (W - l - r) / (n - 1)), col = o.color || 'var(--s1)';
  let d = '', area = '', pen = false, run = [];
  const flush = () => { if (run.length > 1) area += 'M' + x(run[0]).toFixed(1) + ' ' + (H - b) + run.map(i => 'L' + x(i).toFixed(1) + ' ' + y(vals[i]).toFixed(1)).join('') + 'L' + x(run[run.length - 1]).toFixed(1) + ' ' + (H - b) + 'Z'; run = []; };
  vals.forEach((v, i) => { if (v == null || v !== v) { pen = false; flush(); return; } d += (pen ? 'L' : 'M') + x(i).toFixed(1) + ' ' + y(v).toFixed(1); pen = true; run.push(i); }); flush();
  let last = -1; vals.forEach((v, i) => { if (v != null && v === v) last = i; });
  let s = `<svg viewBox="0 0 ${W} ${H}" width="100%" height="${H}" role="img" aria-label="${esc(o.aria)}">`;
  if (lo < 0 && hi > 0) s += `<line class="ax" x1="${l}" x2="${W - r}" y1="${y(0)}" y2="${y(0)}" stroke-dasharray="2 3"/>`;
  s += `<path d="${area}" fill="${col}" fill-opacity=".14"/><path d="${d}" fill="none" stroke="${col}" stroke-width="1.8" stroke-linejoin="round" stroke-linecap="round"/>`;
  if (last >= 0) s += markerSvg('c', x(last), y(vals[last]), 3, col);
  s += `<line class="cross" x1="0" x2="0" y1="${t}" y2="${H - b}" stroke="var(--axis)" stroke-dasharray="3 3" style="display:none"/><circle class="dot" data-s="0" r="4" fill="${col}" stroke="var(--surface)" stroke-width="2" style="display:none"/>`;
  s += `<rect class="ov" x="${l}" y="${t}" width="${W - l - r}" height="${H - t - b}" fill="transparent" tabindex="0" role="application" aria-label="${esc(o.aria + '. Left and right arrow keys move between months' + (o.onPoint ? '; Enter filters to the month.' : '.'))}" style="cursor:${o.onPoint ? 'pointer' : 'crosshair'}"/></svg>`;
  wiring[id] = { type: 'line', W, l, r, n, y, labels: o.labels, series: [{ name: o.name, color: col, vals }], fmt: o.fmt, onPoint: o.onPoint };
  mountChart(id, s, { cols: ['Period', o.name], rows: o.labels.map((lb, i) => [lb, o.fmt(vals[i])]) });
  wireCharts();
}
/* profit bridge (waterfall): totals are solid, steps are hatched so identity never relies on colour alone.
   o.items: {label, key, val (signed step or total), total:true, noSel:true for non-selectable totals} */
function bridgeChart(id, o) {
  const h = $('#' + id); if (!h) return;
  const items = o.items, n = items.length, W = Math.max(320, h.clientWidth || 600), H = o.h || 250, l = 58, r = 10, t = 22, b = 28;
  const xdim = o.xdim || (o.onClick && o.onClick.xdim);
  let run = 0; const geo = items.map(it => { const v = it.val == null || it.val !== it.val ? 0 : it.val; let from, to; if (it.total) { from = 0; to = v; run = v; } else { from = run; to = run + v; run = to; } return { from, to }; });
  items.forEach(it => { it.dis = !!(o.onClick && !it.noSel && xdim && !(o.selected != null && it.key === o.selected) && !xfOK(xdim, it.key)); });
  let lo = 0, hi = 0; geo.forEach(g => { lo = Math.min(lo, g.from, g.to); hi = Math.max(hi, g.from, g.to); });
  const ticks = niceTicks(lo, hi, 5), a = ticks[0], bz = ticks[ticks.length - 1], y = v => t + (H - t - b) * (1 - (v - a) / (bz - a)), bw = (W - l - r) / n, w = Math.max(6, bw * 0.62);
  const sel = o.selected;
  let s = `<svg viewBox="0 0 ${W} ${H}" width="100%" height="${H}" role="group" aria-label="${esc(o.aria)}">${patFill(1, 'var(--s2)', 'brg1')}`;
  ticks.forEach(v => { s += `<line class="${v === 0 ? 'ax' : 'gl'}" x1="${l}" x2="${W - r}" y1="${y(v)}" y2="${y(v)}"/><text x="${l - 6}" y="${y(v) + 4}" text-anchor="end">${esc(fmtAx(v))}</text>`; });
  items.forEach((it, k) => {
    const g = geo[k], bx = l + k * bw + (bw - w) / 2, top = Math.min(y(g.from), y(g.to)), bh = Math.max(2, Math.abs(y(g.from) - y(g.to))), isSel = sel != null && !it.noSel && it.key === sel;
    const fill = it.total ? (it.color || 'var(--s1)') : 'url(#pt-brg1)';
    const interactive = o.onClick && !it.noSel;
    s += `<rect class="bar${it.dis ? ' dis' : ''}" data-k="${k}"${isSel ? ' stroke="var(--ink)" stroke-width="2"' : ''} tabindex="${interactive && !it.dis ? 0 : -1}" role="${interactive && !it.dis ? 'button' : 'img'}"${it.dis ? ' aria-disabled="true"' : ''}${isSel ? ' aria-pressed="true"' : interactive && !it.dis ? ' aria-pressed="false"' : ''} aria-label="${esc(it.label + ': ' + o.fmt(it.val) + (it.dis ? ' (not selectable: no lines in the current selection)' : ''))}" x="${bx}" y="${top}" width="${w}" height="${bh}" rx="3" fill="${fill}"/>`;
    if (k < n - 1) { const lv = geo[k].to; s += `<line x1="${bx + w}" x2="${l + (k + 1) * bw + (bw - w) / 2}" y1="${y(lv)}" y2="${y(lv)}" stroke="var(--axis)" stroke-dasharray="3 3"/>`; }
    s += `<text x="${bx + w / 2}" y="${top - 5}" text-anchor="middle"${isSel ? ' style="font-weight:700;fill:var(--ink)"' : ''}>${esc(o.fmt(it.val))}</text><text x="${l + k * bw + bw / 2}" y="${H - 9}" text-anchor="middle"${isSel ? ' style="font-weight:700;fill:var(--ink)"' : ''}>${esc(it.label)}</text>`;
  });
  s += '</svg>';
  s += `<div class="legend"><span>${legendSwatch('pat', 0, 'var(--s1)')}Total</span><span>${legendSwatch('pat', 1, 'var(--s2)')}Step (deduction)</span></div>`;
  wiring[id] = { type: 'bar', items, fmt: o.fmt, onClick: o.onClick, dim: xdim, sel: o.selected };
  mountChart(id, s, { cols: ['Item', 'Value'], rows: items.map(it => [it.label, o.fmt(it.val)]) });
  if (!tblMode[id]) wireCharts();
}
const cardHtml = (id, title, sub, cls = 'c6', extra = '') => `<section class="card ${cls}"><div class="ctl"><div><h3>${esc(title)}</h3><div class="csub">${sub}</div></div><button class="mini-btn hide-print" data-tbl="${id}" aria-label="Toggle chart or table for ${esc(title)}">Table</button></div>${extra}<div id="${id}" class="chart"></div></section>`;

/* ---------- filter UI ---------- */
const MS = {};
function makeMulti(host, key, label, options) {
  const el = $(host); el.classList.add('ms');
  el.innerHTML = `<span class="lab">${esc(label)}</span><button type="button" class="msb" aria-haspopup="listbox" aria-expanded="false"><span class="mt">All</span><span class="cnt" hidden></span></button><div class="pop" role="listbox" aria-label="${esc(label)}"><input type="search" placeholder="Search ${esc(label.toLowerCase())}&hellip;" aria-label="Search ${esc(label)}"><div class="pa"><button type="button" data-a="all">Select all</button><button type="button" data-a="none">Clear (= all)</button></div><div class="plist"></div></div>`;
  const list = $('.plist', el), inp = $('input', el), btn = $('.msb', el);
  list.innerHTML = options.map(o => `<label data-t="${esc(o.label.toLowerCase())}"><input type="checkbox" value="${o.v}"> ${esc(o.label)}</label>`).join('');
  btn.onclick = ev => { ev.stopPropagation(); const open = !el.classList.contains('open'); closeAllMulti(); if (open) { el.classList.add('open'); btn.setAttribute('aria-expanded', 'true'); inp.focus(); } };
  inp.oninput = () => { const q = inp.value.toLowerCase().trim(); $$('label', list).forEach(l => l.style.display = !q || l.dataset.t.includes(q) ? '' : 'none'); };
  el.onclick = ev => ev.stopPropagation();
  list.onchange = ev => { const was = S[key].length === 0; const v = was ? [+ev.target.value] : $$('input:checked', list).map(i => +i.value); mutate(s => { s[key] = v.length === options.length ? [] : v; }); };
  $('[data-a=all]', el).onclick = () => { const vis = $$('label', list).filter(l => l.style.display !== 'none').map(l => +$('input', l).value); mutate(s => { s[key] = vis.length === options.length ? [] : vis; }); };
  $('[data-a=none]', el).onclick = () => mutate(s => { s[key] = []; });
  MS[key] = { el, options, list, btn, label };
}
function closeAllMulti() { $$('.ms.open').forEach(m => { m.classList.remove('open'); $('.msb', m).setAttribute('aria-expanded', 'false'); }); }
document.addEventListener('click', closeAllMulti);
document.addEventListener('keydown', e => { if (e.key === 'Escape') closeAllMulti(); });
function syncMulti() {
  Object.keys(MS).forEach(key => {
    const m = MS[key], sel = new Set(S[key]), all = sel.size === 0;
    $$('input', m.list).forEach(i => i.checked = all || sel.has(+i.value));
    const c = $('.cnt', m.btn); c.hidden = all; c.textContent = sel.size; $('.mt', m.btn).textContent = all ? 'All' : (sel.size === 1 ? m.options.find(o => o.v === S[key][0]).label : sel.size + ' selected');
    m.btn.title = all ? 'All ' + m.label : m.options.filter(o => sel.has(o.v)).map(o => o.label).join(', ');
  });
}
function chipSummary(key) { const m = MS[key]; const names = m.options.filter(o => S[key].includes(o.v)).map(o => o.label.split(' · ')[0]); return names.length > 3 ? names.slice(0, 3).join(', ') + ' +' + (names.length - 3) : names.join(', '); }

/* ---------- header scope: always describes the CURRENT state ---------- */
const SCALE_DESC = { ADJ: 'amounts scale-adjusted (provisional restoration)', PARSED: 'amounts AS REPORTED &mdash; scale restoration not applied', HIGH: 'scale restored for HIGH-confidence rows only (MEDIUM-confidence rows as reported)', EXCL_MED: 'scale-adjusted, MEDIUM-confidence restored rows excluded', EXCL_ALL: 'scale-adjusted, all restored rows excluded' };
const DUP_DESC = { KEEP: 'duplicate candidates retained', EXCL_SAME: 'same-sign duplicate candidates excluded', EXCL_ALL: 'all duplicate candidates excluded' };
const SIGN_DESC = { KEEP: 'signs as recorded', NONNEG: 'only all-non-negative rows kept', EXCL_FLIP: 'single-column sign flips excluded' };
let basisOpen = false, printing = false;
function bindBasis() { const d = $('#scope details.basis'); if (d) d.ontoggle = e => { if (!printing) basisOpen = e.target.open; }; }
function scopeHtml() {
  const scn = S.scale !== 'ADJ' || S.dup !== 'KEEP' || S.sign !== 'KEEP';
  const dims = []; if (S.xf) dims.push('chart selection'); ['ent', 'div', 'sec', 'gl', 'cc'].forEach(k => { if (S[k].length) dims.push(XDIM_NAME[k].toLowerCase() + ' filter'); });
  const line = 'USD &middot; <b class="num">' + fmtInt(nInc) + '</b> of ' + fmtInt(N) + ' Posted-eligible P&amp;L lines in scope' + (dims.length ? ' (' + dims.join(', ') + ' applied)' : '') + ' &middot; ' + scopeText();
  const changed = []; if (S.scale !== 'ADJ') changed.push(SCALE_DESC[S.scale]); if (S.dup !== 'KEEP') changed.push(DUP_DESC[S.dup]); if (S.sign !== 'KEEP') changed.push(SIGN_DESC[S.sign]);
  const full = SCALE_DESC[S.scale] + ' &middot; ' + DUP_DESC[S.dup] + ' &middot; ' + SIGN_DESC[S.sign] + '. Main population: Posted-eligible P&amp;L lines (provisional rule R6). ' +
    'Not every page uses this population: Journal-status diagnostics use a separate all-status population; variance, forecast and prior-year views use only lines that carry the budget, forecast or prior-year comparator.';
  return '<span class="sc1">' + line + '</span><span class="sc2">' + (scn ? '<b class="scn-flag">SCENARIO ACTIVE</b> ' + changed.join(' &middot; ') + ' ' : '') +
    '<details class="basis"' + (basisOpen ? ' open' : '') + '><summary>' + (scn ? 'Full basis' : 'Baseline basis') + '</summary><span class="bd">' + full + '</span></details></span>';
}
function varPopCounts() {
  return memo('vpc', () => {
    const o = { ALL: [0, 0], SAME: [0, 0], OPP: [0, 0], ZERO: [0, 0] };
    for (let i = 0; i < N; i++) {
      if (!inc[i]) continue;
      if (EB[i] === EB[i]) { o.ALL[0]++; const c = SAB[i]; if (c <= 2) o[['SAME', 'OPP', 'ZERO'][c]][0]++; }
      if (EP[i] === EP[i]) { o.ALL[1]++; const c = SAP[i]; if (c <= 2) o[['SAME', 'OPP', 'ZERO'][c]][1]++; }
    }
    return o;
  });
}
let varNoteOpen = false;
function syncFilters() {
  $('#scope').innerHTML = scopeHtml(); bindBasis();
  { const v = varPopCounts()[S.varPop], vn = $('#varNote'); vn.innerHTML = '<details' + (varNoteOpen ? ' open' : '') + '><summary><b>Variance-comparison population:</b> <span class="num">' + fmtInt(v[0]) + ' budget-comparison lines &middot; ' + fmtInt(v[1]) + ' prior-year-comparison lines (of ' + fmtInt(nInc) + ' in scope)</span> &mdash; what does this selector change?</summary><div>It changes only: Budget &amp; Variance, the Executive variance KPI, the prior-year comparison table and variance insights. It does <b>not</b> change line counts, revenue/cost KPIs, forecast accuracy, gross profit or data-quality tables. Sign category = actual vs budget (prior-year table: actual vs prior-year column): same-sign / opposite-sign / zero-involved.</div></details>'; $('details', vn).ontoggle = e => { varNoteOpen = e.target.open; }; }
  $$('#fYears .chip').forEach(b => b.setAttribute('aria-pressed', S.years.includes(+b.dataset.v)));
  $$('#fQtrs .chip').forEach(b => b.setAttribute('aria-pressed', S.qtrs.includes(+b.dataset.v)));
  $('#fFrom').value = S.from; $('#fTo').value = S.to;
  $('#sVar').value = S.varPop; $('#sScale').value = S.scale; $('#sDup').value = S.dup; $('#sSign').value = S.sign;
  syncMulti();
  const tags = [];
  const tag = (txt, fn, cls = '') => tags.push({ txt, fn, cls });
  if (S.years.length !== YEARS.length) tag('Year: ' + (S.years.length ? S.years.slice().sort().join(', ') : 'none'), s => s.years = YEARS.slice());
  if (S.qtrs.length !== 4) tag('Quarter: ' + (S.qtrs.length ? S.qtrs.slice().sort().map(q => 'Q' + q).join(', ') : 'none'), s => s.qtrs = [1, 2, 3, 4]);
  if (S.from !== 0 || S.to !== NM - 1) tag('Months: ' + mLabel(S.from) + ' → ' + mLabel(S.to), s => { s.from = 0; s.to = NM - 1; });
  [['ent', 'Entity'], ['div', 'Division'], ['sec', 'Section'], ['gl', 'GL'], ['cc', 'Cost centre']].forEach(([k, n]) => { if (S[k].length) tag(n + ': ' + chipSummary(k), s => s[k] = []); });
  if (S.xf) tag('Chart selection: ' + S.xf.label, s => s.xf = null, 'xf');
  if (S.varPop !== 'ALL') tag('Variance-comparison population: ' + VARPOP_LBL[S.varPop], s => s.varPop = 'ALL', 'scn');
  if (S.scale !== 'ADJ') tag('Scale: ' + SCALE_LBL[S.scale], s => s.scale = 'ADJ', 'scn');
  if (S.dup !== 'KEEP') tag('Duplicates: ' + DUP_LBL[S.dup], s => s.dup = 'KEEP', 'scn');
  if (S.sign !== 'KEEP') tag('Signs: ' + SIGN_LBL[S.sign], s => s.sign = 'KEEP', 'scn');
  const row = $('#activeRow');
  row.innerHTML = (tags.length ? '<span class="lab" style="font-size:11px;color:var(--muted)">ACTIVE:</span>' : '<span style="color:var(--muted);font-size:12px">No filters active &mdash; full dataset (Posted lines, baseline rules)</span>') +
    tags.map((t, i) => `<span class="tag ${t.cls}">${esc(t.txt)}<button type="button" data-i="${i}" aria-label="Remove filter: ${esc(t.txt)}">&times;</button></span>`).join('') +
    `<span style="margin-left:auto;color:var(--ink-2);font-size:12px" class="num" id="inScope">${fmtInt(nInc)} of ${fmtInt(N)} lines in scope</span>`;
  $$('button[data-i]', row).forEach(b => b.onclick = () => mutate(s => tags[+b.dataset.i].fn(s)));
  $('#btnUndo').disabled = hist.length === 0;
  const isDef = JSON.stringify(Object.assign({}, S, { tab: 0 })) === JSON.stringify(Object.assign(DEF(), { tab: 0 }));
  $('#btnReset').disabled = isDef;
}
function initFilters() {
  $('#fYears').innerHTML = YEARS.map(y => `<button type="button" class="chip" data-v="${y}" aria-pressed="true">${y}</button>`).join('');
  $('#fQtrs').innerHTML = [1, 2, 3, 4].map(q => `<button type="button" class="chip" data-v="${q}" aria-pressed="true">Q${q}</button>`).join('');
  $$('#fYears .chip').forEach(b => b.onclick = () => mutate(s => { const v = +b.dataset.v; s.years = s.years.includes(v) ? s.years.filter(x => x !== v) : s.years.concat(v); }));
  $$('#fQtrs .chip').forEach(b => b.onclick = () => mutate(s => { const v = +b.dataset.v; s.qtrs = s.qtrs.includes(v) ? s.qtrs.filter(x => x !== v) : s.qtrs.concat(v); }));
  const mo = P.months.map((m, i) => `<option value="${i}">${mLabel(i)}</option>`).join('');
  $('#fFrom').innerHTML = mo; $('#fTo').innerHTML = mo;
  $('#fFrom').onchange = e => mutate(s => { s.from = +e.target.value; if (s.to < s.from) s.to = s.from; });
  $('#fTo').onchange = e => mutate(s => { s.to = +e.target.value; if (s.from > s.to) s.from = s.to; });
  makeMulti('#gEnt', 'ent', 'Entity', P.ents.map((e, i) => ({ v: i, label: e.c + ' · ' + e.n })));
  makeMulti('#gDiv', 'div', 'Division', P.divs.map((d, i) => ({ v: i, label: d })));
  makeMulti('#gSec', 'sec', 'Section / account group', P.secs.map((s, i) => ({ v: i, label: secName(s) })));
  makeMulti('#gGl', 'gl', 'GL account', P.gls.map((g, i) => ({ v: i, label: g.gl + ' · ' + g.name })));
  makeMulti('#gCc', 'cc', 'Cost centre', [{ v: -1, label: '(no cost centre)' }].concat(P.ccs.map((c, i) => ({ v: i, label: c }))));
  const sel = (id, key) => $(id).onchange = e => mutate(s => { s[key] = e.target.value; });
  sel('#sVar', 'varPop'); sel('#sScale', 'scale'); sel('#sDup', 'dup'); sel('#sSign', 'sign');
  $('#btnReset').onclick = resetAll; $('#btnUndo').onclick = undo;
}

/* test hook helper: bar charts currently mounted (id, cross-filter dimension, items with disabled flag) */
function chartsInfo() { return Object.entries(wiring).filter(([id, w]) => w.type === 'bar' && w.onClick && w.dim && $('#' + id) && $('#' + id).offsetParent !== null).map(([id, w]) => ({ id, dim: w.dim, items: w.items.filter(it => !it.noSel).map(it => ({ key: it.key, label: it.label, dis: !!it.dis, val: it.val })) })); }
