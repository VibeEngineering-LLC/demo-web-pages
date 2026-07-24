// Связка интерфейса, расчёта и 3D-сцены. Страница двуязычная: русский и английский.
import { doseRate, doseAt, beadResponse, layout, fmtPM, REF, A_U238_PER_KG_U } from './physics.js?v=2';
import { Scene3D } from './view3d.js?v=2';

const $ = id => document.getElementById(id);
const REL_U = 0.10;                      // относительная неопределённость результата
const K_SHAPE = 63.96 / (4.10 * 4.10 * 2.20 * 2.50);   // коэффициент формы рокайля (объём)
const MAX_BEADS = 4000;

let area = 1.0, scene = null, needReframe = true, LANG = 'ru';

// ------------------------------------------------------------------------ словарь
const T = {
  ru: {
    uSv_h: 'мкЗв/ч', uSv: 'мкЗв', mSv: 'мЗв', mSv_y: 'мЗв/год', Bq: 'Бк', kBq: 'кБк',
    mm: 'мм', g: 'г', mg: 'мг', kBq_kg: 'кБк/кг',
    area1: '1 см²', area01: '0,1 см²', area001: '0,01 см²',
    single: 'одиночная бусина',
    pitchWord: 'шаг', wt: '% масс.',
    noPitch: 'Для одиночной бусины шаг не используется.',
    densePitch: d => `Плотная укладка — шаг равен диаметру (${d} мм). Больший шаг — разрежённая раскладка.`,
    specAct: v => `Удельная активность стекла по U-238: ${v} кБк/кг (эталон статьи — 1,85 % масс., 227 кБк/кг).`,
    beadInfo: (h, m, s) => `Высота рокайля ${h} мм, масса бусины ${m} мг; насыщение по толщине ${s} %.`,
    scene: (a) => `сцена ${a} × ${a} мм`,
    beads: n => `${n} ${plural(n, 'бусина', 'бусины', 'бусин')}`,
    axisUnit: 'мкЗв/ч, локально',
    wLimit: n => `Раскладка ограничена ${n} бусинами — уменьшите размер или увеличьте шаг.`,
    wDiam: d => `Диаметр ${d} мм вне области калибровки (2…8 мм): результат — экстраполяция.`,
    wU: w => `Содержание урана ${w} % масс. заметно выше типичного для уранового стекла (0,5…3 %).`,
    wRho: r => `Плотность ${r} г/см³ нетипична для натрий-кальциевого стекла.`,
    wYear: 'Расчётная годовая доза превышает предел для кожи персонала. Проверьте режим контакта независимо.',
    vRows: ['Одиночная бусина', 'Одиночная бусина', 'Одиночная бусина',
      'Цепочка 11 бусин', 'Раскладка 5×5', 'Раскладка 7×7', 'Раскладка 9×9'],
    vAreas: ['1 см²', '0,1 см²', '0,01 см²', '1 см²', '1 см²', '1 см²', '1 см²'],
    vTotal: 'Среднеквадратичное отклонение модели от Geant4',
    noWebGL: 'Трёхмерная визуализация недоступна: браузер не поддерживает WebGL. '
      + 'Расчётная часть работает без неё.',
  },
  en: {
    uSv_h: 'µSv/h', uSv: 'µSv', mSv: 'mSv', mSv_y: 'mSv/y', Bq: 'Bq', kBq: 'kBq',
    mm: 'mm', g: 'g', mg: 'mg', kBq_kg: 'kBq/kg',
    area1: '1 cm²', area01: '0.1 cm²', area001: '0.01 cm²',
    single: 'single bead',
    pitchWord: 'pitch', wt: 'wt %',
    noPitch: 'Pitch is not used for a single bead.',
    densePitch: d => `Dense packing — pitch equals the diameter (${d} mm). A larger pitch means a sparse array.`,
    specAct: v => `U-238 specific activity of the glass: ${v} kBq/kg (paper baseline — 1.85 wt %, 227 kBq/kg).`,
    beadInfo: (h, m, s) => `Bead height ${h} mm, bead mass ${m} mg; thickness saturation ${s} %.`,
    scene: (a) => `scene ${a} × ${a} mm`,
    beads: n => `${n} ${n === 1 ? 'bead' : 'beads'}`,
    axisUnit: 'µSv/h, local',
    wLimit: n => `The array is capped at ${n} beads — reduce its size or increase the pitch.`,
    wDiam: d => `A diameter of ${d} mm is outside the calibration range (2…8 mm): the result is an extrapolation.`,
    wU: w => `A uranium content of ${w} wt % is well above what is typical for uranium glass (0.5…3 %).`,
    wRho: r => `A density of ${r} g/cm³ is atypical for soda-lime glass.`,
    wYear: 'The calculated annual dose exceeds the skin limit for workers. Verify the contact regime independently.',
    vRows: ['Single bead', 'Single bead', 'Single bead',
      'Chain of 11 beads', 'Array 5×5', 'Array 7×7', 'Array 9×9'],
    vAreas: ['1 cm²', '0.1 cm²', '0.01 cm²', '1 cm²', '1 cm²', '1 cm²', '1 cm²'],
    vTotal: 'R.m.s. deviation of the model from Geant4',
    noWebGL: 'The 3D visualisation is unavailable: this browser does not support WebGL. '
      + 'The calculation itself works without it.',
  },
};
const t = () => T[LANG];

// Склонение существительного при числительном: 1 бусина, 2 бусины, 5 бусин.
function plural(n, one, few, many) {
  const a = Math.abs(n) % 100, b = a % 10;
  if (a > 10 && a < 20) return many;
  if (b > 1 && b < 5) return few;
  return b === 1 ? one : many;
}

const areaName = () => area === 1 ? t().area1 : area === 0.1 ? t().area01 : t().area001;

// ------------------------------------------------------------------ конфигурация
function cfg() {
  const d = +$('d').value, shape = $('shape').value;
  return {
    shape, d, rho: +$('rho').value, wU: +$('wU').value,
    pitch: $('dense').checked ? d : Math.max(+$('pitch').value, d),
    nx: Math.max(1, Math.round(+$('nx').value)),
    ny: Math.max(1, Math.round(+$('ny').value)),
    radius: +$('radius').value,
  };
}

function fmt(x, n = 3) {
  if (!isFinite(x)) return '—';
  const s = Math.abs(x) >= 1000 ? x.toFixed(0)
    : Math.abs(x) >= 100 ? x.toFixed(1)
      : Math.abs(x) >= 1 ? x.toPrecision(n) : x.toPrecision(2);
  return (+s).toLocaleString(LANG === 'ru' ? 'ru-RU' : 'en-US', { maximumFractionDigits: 6 });
}
const dec = x => LANG === 'ru' ? x.replace('.', ',') : x;

// ------------------------------------------------------------------- пересчёт
function recalc(reframe = false) {
  const c = cfg();
  // связанные поля
  if ($('dense').checked || +$('pitch').value < c.d) $('pitch').value = c.pitch.toFixed(2);
  $('pitch').disabled = $('dense').checked; $('pitchR').disabled = $('dense').checked;
  $('pitchR').value = $('pitch').value; $('dR').value = $('d').value; $('wUR').value = $('wU').value;
  $('r-nx').style.display = (c.shape === 'chain' || c.shape === 'grid') ? '' : 'none';
  $('r-ny').style.display = (c.shape === 'grid') ? '' : 'none';
  $('r-rad').style.display = (c.shape === 'disk') ? '' : 'none';
  $('lbNx').textContent = c.shape === 'chain'
    ? (LANG === 'ru' ? 'Число бусин в ряду' : 'Beads in the row')
    : (LANG === 'ru' ? 'Бусин по оси X' : 'Beads along X');

  let centers = layout(c);
  const warns = [];
  if (centers.length > MAX_BEADS) {
    centers = centers.slice(0, MAX_BEADS);
    warns.push(t().wLimit(MAX_BEADS));
  }
  const tab = beadResponse(c.d / 2);

  // основной результат
  const H = doseRate(c, area, 0, 0, tab, centers);
  const r = fmtPM(H, REL_U, LANG);
  $('oVal').textContent = `${r.v} ± ${r.u}`;
  $('oArea').textContent = areaName();
  $('oUnit').textContent = t().uSv_h;

  // производные величины
  const tS = +$('tses').value, nS = +$('nses').value;
  const perSes = H * tS / 1000, perYear = perSes * nS;   // мЗв
  $('oSes').textContent = perSes >= 1 ? `${fmt(perSes)} ${t().mSv}` : `${fmt(perSes * 1000)} ${t().uSv}`;
  $('oYear').textContent = `${fmt(perYear)} ${t().mSv_y}`;
  $('oLimA').textContent = `${fmt(100 * perYear / 500)} %`;
  $('oLimB').textContent = `${fmt(100 * perYear / 50)} %`;

  const volMM3 = K_SHAPE * c.d * c.d * (c.d * REF.hOverD);   // мм³
  const mBead = volMM3 * c.rho;                              // мг
  const mTot = mBead * centers.length;                       // мг
  $('oN').textContent = `${t().beads(centers.length)}`
    + ` / ${mTot >= 1000 ? fmt(mTot / 1000) + ' ' + t().g : fmt(mTot) + ' ' + t().mg}`;
  const act = mTot * 1e-6 * (c.wU / 100) * A_U238_PER_KG_U;  // Бк
  $('oAct').textContent = act >= 1e3 ? `${fmt(act / 1e3)} ${t().kBq}` : `${fmt(act)} ${t().Bq}`;

  const peak = doseAt(c, 0, 0, tab, centers);
  $('oPeak').textContent = `${fmt(peak)} ${t().uSv_h}`;
  $('oScale').textContent = `${fmt(peak)} ${t().uSv_h}`;

  const aSpec = (c.wU / 100) * A_U238_PER_KG_U;
  $('hAct').textContent = t().specAct(fmt(aSpec / 1000));
  $('hBead').textContent = t().beadInfo(fmt(c.d * REF.hOverD), fmt(mBead),
    fmt(100 * (1 - Math.exp(-REF.nu * c.rho * c.d * REF.hOverD / 10)), 3));
  $('hPitch').textContent = c.shape === 'single' ? t().noPitch : t().densePitch(fmt(c.d));

  // предупреждения о границах применимости
  if (c.d < 2 || c.d > 8) warns.push(t().wDiam(fmt(c.d)));
  if (c.wU > 5) warns.push(t().wU(fmt(c.wU)));
  if (c.rho < 2.2 || c.rho > 2.9) warns.push(t().wRho(fmt(c.rho)));
  if (perYear > 500) warns.push(t().wYear);
  $('warn').style.display = warns.length ? 'block' : 'none';
  $('warn').innerHTML = warns.map(w => '⚠ ' + w).join('<br>');

  const nb = centers.length;
  $('oNote').textContent = (nb === 1 ? t().single
    : `${t().beads(nb)}, ${t().pitchWord} ${fmt(c.pitch)} ${t().mm}`)
    + `, Ø ${fmt(c.d)} ${t().mm}, U ${fmt(c.wU)} ${t().wt}`;

  drawProfile(c, tab, centers, H);
  if (scene) scene.update(c, {
    relief: +$('cRelief').value / 100, showRing: $('cRing').checked,
    area, reframe: reframe || needReframe,
  });
  if (scene && scene.ext) $('oExt').textContent = t().scene(fmt(2 * scene.ext));
  needReframe = false;
}

// ------------------------------------------------------------- профиль вдоль X
function drawProfile(c, tab, centers, Havg) {
  const cv = $('prof'), dpr = Math.min(devicePixelRatio, 2);
  const W = cv.clientWidth, Hh = cv.clientHeight;
  cv.width = W * dpr; cv.height = Hh * dpr;
  const g = cv.getContext('2d'); g.setTransform(dpr, 0, 0, dpr, 0, 0); g.clearRect(0, 0, W, Hh);
  const muted = getComputedStyle(document.documentElement).getPropertyValue('--muted') || '#888';

  let ext = 0; for (const [x, y] of centers) ext = Math.max(ext, Math.abs(x), Math.abs(y));
  ext = Math.max(ext + c.d / 2 + 8, 12);
  const N = 320, xs = [], ys = []; let vmax = 0;
  for (let i = 0; i <= N; i++) {
    const x = -ext + 2 * ext * i / N, v = doseAt(c, x, 0, tab, centers);
    xs.push(x); ys.push(v); if (v > vmax) vmax = v;
  }
  const L = 46, R = 10, Tp = 10, B = 26, pw = W - L - R, ph = Hh - Tp - B;
  const X = x => L + (x + ext) / (2 * ext) * pw, Y = v => Tp + ph * (1 - v / (vmax * 1.08 || 1));

  g.strokeStyle = muted; g.globalAlpha = .35; g.lineWidth = 1;
  g.beginPath(); g.moveTo(L, Tp); g.lineTo(L, Tp + ph); g.lineTo(L + pw, Tp + ph); g.stroke();
  g.globalAlpha = 1;
  g.fillStyle = muted; g.font = '11px system-ui,sans-serif';
  g.textAlign = 'right'; g.fillText(dec(vmax.toPrecision(3)), L - 4, Tp + 9);
  g.fillText('0', L - 4, Tp + ph + 3);
  g.textAlign = 'center';
  g.fillText(`−${ext.toFixed(0)} ${t().mm}`, L + 16, Hh - 8);
  g.fillText(`${ext.toFixed(0)} ${t().mm}`, L + pw - 16, Hh - 8);
  g.fillText(t().axisUnit, L + pw / 2, Hh - 8);

  // уровень усреднения
  g.strokeStyle = '#2b5f8a'; g.setLineDash([4, 3]); g.beginPath();
  g.moveTo(L, Y(Havg)); g.lineTo(L + pw, Y(Havg)); g.stroke(); g.setLineDash([]);

  g.strokeStyle = '#c1440e'; g.lineWidth = 2; g.beginPath();
  xs.forEach((x, i) => i ? g.lineTo(X(x), Y(ys[i])) : g.moveTo(X(x), Y(ys[i])));
  g.stroke();
}

// -------------------------------------------------- таблица проверки по Geant4
const MCPOINTS = [
  [6.6909, { shape: 'single' }, 1.0],
  [19.1753, { shape: 'single' }, 0.1],
  [27.1719, { shape: 'single' }, 0.01],
  [18.3350, { shape: 'chain', nx: 11 }, 1.0],
  [48.0957, { shape: 'grid', nx: 5, ny: 5 }, 1.0],
  [48.7382, { shape: 'grid', nx: 7, ny: 7 }, 1.0],
  [48.4382, { shape: 'grid', nx: 9, ny: 9 }, 1.0],
];

function buildValidation() {
  const base = { shape: 'single', nx: 1, ny: 1, radius: 10, d: REF.d, pitch: REF.pitch, wU: REF.wU, rho: REF.rho };
  const tb = $('vtab').querySelector('tbody');
  tb.innerHTML = '';
  let s2 = 0;
  MCPOINTS.forEach(([mc, over, a], i) => {
    const v = doseRate({ ...base, ...over }, a);
    const e = 100 * (v / mc - 1); s2 += e * e;
    const tr = document.createElement('tr');
    tr.innerHTML = `<td>${t().vRows[i]}</td><td class="num-col">${t().vAreas[i]}</td>`
      + `<td class="num-col">${dec(mc.toFixed(2))}</td>`
      + `<td class="num-col">${dec(v.toFixed(2))}</td>`
      + `<td class="num-col">${(e >= 0 ? '+' : '−') + dec(Math.abs(e).toFixed(2))} %</td>`;
    tb.appendChild(tr);
  });
  const tr = document.createElement('tr');
  tr.innerHTML = `<td colspan="4"><b>${t().vTotal}</b></td>`
    + `<td class="num-col"><b>${dec(Math.sqrt(s2 / MCPOINTS.length).toFixed(2))} %</b></td>`;
  tb.appendChild(tr);
}

// ------------------------------------------------------------------- язык
function setLang(l) {
  LANG = l;
  document.body.dataset.lang = l;
  document.documentElement.lang = l;
  document.title = l === 'ru'
    ? 'Калькулятор Hp(0,07): урановый стеклянный бисер на коже'
    : 'Hp(0.07) calculator: uranium glass beads on skin';
  // подписи интерфейса: русский текст — исходный, английский — в data-en
  document.querySelectorAll('[data-en]').forEach(el => {
    if (el.dataset.ru === undefined) el.dataset.ru = el.textContent;
    el.textContent = l === 'en' ? el.dataset.en : el.dataset.ru;
  });
  $('btn-ru').classList.toggle('active', l === 'ru');
  $('btn-en').classList.toggle('active', l === 'en');
  try { localStorage.setItem('beadsCalcLang', l); } catch (_) { }
  buildValidation();
  recalc();
}

// ------------------------------------------------------------------- запуск
function bind() {
  ['nx', 'ny', 'radius', 'pitch', 'd', 'rho', 'wU', 'tses', 'nses']
    .forEach(id => $(id).addEventListener('input', () => recalc()));
  $('shape').addEventListener('change', () => { needReframe = true; recalc(true); });
  const link = (rid, nid) => {
    $(rid).addEventListener('input', () => { $(nid).value = $(rid).value; recalc(); });
  };
  link('pitchR', 'pitch'); link('dR', 'd'); link('wUR', 'wU');
  $('areaSeg').querySelectorAll('button').forEach(b => b.addEventListener('click', () => {
    $('areaSeg').querySelectorAll('button').forEach(x => x.classList.remove('on'));
    b.classList.add('on'); area = +b.dataset.a; recalc();
  }));
  $('areaSeg').querySelector('button').classList.add('on');
  $('dense').addEventListener('change', () => recalc());
  $('cRelief').addEventListener('input', () => recalc());
  $('cRing').addEventListener('change', () => recalc());
  $('bReset').addEventListener('click', () => {
    if (scene) { scene.az = -0.6; scene.el = 0.85; }
    recalc(true);
  });
  $('btn-ru').addEventListener('click', () => setLang('ru'));
  $('btn-en').addEventListener('click', () => setLang('en'));
  addEventListener('resize', () => recalc());
}

try {
  scene = new Scene3D($('cv'));
} catch (e) {
  $('cv').outerHTML = `<div class="callout">${T.ru.noWebGL}</div>`;
  console.error(e);
}
bind();

let saved = null;
try { saved = localStorage.getItem('beadsCalcLang'); } catch (_) { }
setLang(saved === 'en' ? 'en' : 'ru');      // по умолчанию русский, как в основной статье
recalc(true);

// точка входа для внешней проверки расчёта из консоли браузера
window.__calc = { scene, recalc, doseRate, doseAt, layout, cfg, setLang };
