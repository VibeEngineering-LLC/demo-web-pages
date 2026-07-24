// Связка интерфейса, расчёта и 3D-сцены.
import { doseRate, doseAt, beadResponse, layout, scaleFactor, fmtPM, REF, A_U238_PER_KG_U } from './physics.js';
import { Scene3D } from './view3d.js';

const $ = id => document.getElementById(id);
const REL_U = 0.10;                      // относительная неопределённость результата
const K_SHAPE = 63.96 / (4.10 * 4.10 * 2.20 * 2.50);   // коэффициент формы рокайля (объём)
const MAX_BEADS = 4000;

let area = 1.0, scene = null, needReframe = true;

// ------------------------------------------------------------------ конфигурация
// Склонение существительного при числительном: 1 бусина, 2 бусины, 5 бусин.
function plural(n, one, few, many) {
  const a = Math.abs(n) % 100, b = a % 10;
  if (a > 10 && a < 20) return many;
  if (b > 1 && b < 5) return few;
  return b === 1 ? one : many;
}

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
  return (+s).toLocaleString('ru-RU', { maximumFractionDigits: 6 });
}

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
  $('r-nx').querySelector('label').textContent = c.shape === 'chain' ? 'Число бусин в ряду' : 'Бусин по оси X';

  let centers = layout(c);
  const warns = [];
  if (centers.length > MAX_BEADS) {
    centers = centers.slice(0, MAX_BEADS);
    warns.push(`Раскладка ограничена ${MAX_BEADS} бусинами — уменьшите размер или увеличьте шаг.`);
  }
  const tab = beadResponse(c.d / 2);

  // основной результат
  const H = doseRate(c, area, 0, 0, tab, centers);
  const r = fmtPM(H, REL_U);
  $('oVal').textContent = `${r.v} ± ${r.u}`;
  $('oArea').textContent = area === 1 ? '1 см²' : area === 0.1 ? '0,1 см²' : '0,01 см²';

  // производные величины
  const tS = +$('tses').value, nS = +$('nses').value;
  const perSes = H * tS / 1000, perYear = perSes * nS;   // мЗв
  $('oSes').textContent = perSes >= 1 ? `${fmt(perSes)} мЗв` : `${fmt(perSes * 1000)} мкЗв`;
  $('oYear').textContent = `${fmt(perYear)} мЗв/год`;
  $('oLimA').textContent = `${fmt(100 * perYear / 500)} %`;
  $('oLimB').textContent = `${fmt(100 * perYear / 50)} %`;

  const volMM3 = K_SHAPE * c.d * c.d * (c.d * REF.hOverD);   // мм³
  const mBead = volMM3 * c.rho;                              // мг
  const mTot = mBead * centers.length;                       // мг
  $('oN').textContent = `${centers.length} ${plural(centers.length, 'бусина', 'бусины', 'бусин')}`
    + ` / ${mTot >= 1000 ? fmt(mTot / 1000) + ' г' : fmt(mTot) + ' мг'}`;
  const act = mTot * 1e-6 * (c.wU / 100) * A_U238_PER_KG_U;  // Бк
  $('oAct').textContent = act >= 1e3 ? `${fmt(act / 1e3)} кБк` : `${fmt(act)} Бк`;

  const peak = doseAt(c, 0, 0, tab, centers);
  $('oPeak').textContent = `${fmt(peak)} мкЗв/ч`;
  $('oScale').textContent = `${fmt(peak)} мкЗв/ч`;

  const aSpec = (c.wU / 100) * A_U238_PER_KG_U;
  $('hAct').textContent = `Удельная активность стекла по U-238: ${fmt(aSpec / 1000)} кБк/кг`
    + ` (эталон статьи — 1,85 % масс., 227 кБк/кг).`;
  $('hBead').textContent = `Высота рокайля ${fmt(c.d * REF.hOverD)} мм, масса бусины ${fmt(mBead)} мг;`
    + ` насыщение по толщине ${fmt(100 * (1 - Math.exp(-REF.nu * c.rho * c.d * REF.hOverD / 10)), 3)} %.`;
  $('hPitch').textContent = c.shape === 'single' ? 'Для одиночной бусины шаг не используется.'
    : `Плотная укладка — шаг равен диаметру (${fmt(c.d)} мм). Больший шаг — разрежённая раскладка.`;

  // предупреждения о границах применимости
  if (c.d < 2 || c.d > 8) warns.push(`Диаметр ${fmt(c.d)} мм вне области калибровки (2…8 мм): результат — экстраполяция.`);
  if (c.wU > 5) warns.push(`Содержание урана ${fmt(c.wU)} % масс. заметно выше типичного для уранового стекла (0,5…3 %).`);
  if (c.rho < 2.2 || c.rho > 2.9) warns.push(`Плотность ${fmt(c.rho)} г/см³ нетипична для натрий-кальциевого стекла.`);
  if (perYear > 500) warns.push('Расчётная годовая доза превышает предел для кожи персонала. Проверьте режим контакта независимо.');
  $('warn').style.display = warns.length ? 'block' : 'none';
  $('warn').innerHTML = warns.map(w => '⚠ ' + w).join('<br>');
  const nb = centers.length;
  $('oNote').textContent = (nb === 1 ? 'одиночная бусина'
    : `${nb} ${plural(nb, 'бусина', 'бусины', 'бусин')}, шаг ${fmt(c.pitch)} мм`)
    + `, Ø ${fmt(c.d)} мм, U ${fmt(c.wU)} % масс.`;

  drawProfile(c, tab, centers, H);
  if (scene) scene.update(c, {
    relief: +$('cRelief').value / 100, showRing: $('cRing').checked,
    area, reframe: reframe || needReframe,
  });
  if (scene && scene.ext) $('oExt').textContent = `сцена ${fmt(2 * scene.ext)} × ${fmt(2 * scene.ext)} мм`;
  needReframe = false;
}

// ------------------------------------------------------------- профиль вдоль X
function drawProfile(c, tab, centers, Havg) {
  const cv = $('prof'), dpr = Math.min(devicePixelRatio, 2);
  const W = cv.clientWidth, Hh = cv.clientHeight;
  cv.width = W * dpr; cv.height = Hh * dpr;
  const g = cv.getContext('2d'); g.setTransform(dpr, 0, 0, dpr, 0, 0); g.clearRect(0, 0, W, Hh);
  const css = getComputedStyle(document.body);
  const fg = css.color, muted = getComputedStyle(document.documentElement).getPropertyValue('--muted') || '#888';

  let ext = 0; for (const [x, y] of centers) ext = Math.max(ext, Math.abs(x), Math.abs(y));
  ext = Math.max(ext + c.d / 2 + 8, 12);
  const N = 320, xs = [], ys = []; let vmax = 0;
  for (let i = 0; i <= N; i++) {
    const x = -ext + 2 * ext * i / N, v = doseAt(c, x, 0, tab, centers);
    xs.push(x); ys.push(v); if (v > vmax) vmax = v;
  }
  const L = 46, R = 10, T = 10, B = 26, pw = W - L - R, ph = Hh - T - B;
  const X = x => L + (x + ext) / (2 * ext) * pw, Y = v => T + ph * (1 - v / (vmax * 1.08 || 1));

  g.strokeStyle = muted; g.globalAlpha = .35; g.lineWidth = 1;
  g.beginPath(); g.moveTo(L, T); g.lineTo(L, T + ph); g.lineTo(L + pw, T + ph); g.stroke();
  g.globalAlpha = 1;
  g.fillStyle = muted; g.font = '11px system-ui,sans-serif';
  g.textAlign = 'right'; g.fillText(vmax.toPrecision(3), L - 4, T + 9);
  g.fillText('0', L - 4, T + ph + 3);
  g.textAlign = 'center';
  g.fillText(`−${ext.toFixed(0)} мм`, L + 16, Hh - 8);
  g.fillText(`${ext.toFixed(0)} мм`, L + pw - 16, Hh - 8);
  g.fillText('мкЗв/ч, локально', L + pw / 2, Hh - 8);

  // уровень усреднения
  g.strokeStyle = '#2b5f8a'; g.setLineDash([4, 3]); g.beginPath();
  g.moveTo(L, Y(Havg)); g.lineTo(L + pw, Y(Havg)); g.stroke(); g.setLineDash([]);

  g.strokeStyle = '#c1440e'; g.lineWidth = 2; g.beginPath();
  xs.forEach((x, i) => i ? g.lineTo(X(x), Y(ys[i])) : g.moveTo(X(x), Y(ys[i])));
  g.stroke();
}

// -------------------------------------------------- таблица проверки по Geant4
const MCPOINTS = [
  ['Одиночная бусина', '1 см²', 6.6909, { shape: 'single' }, 1.0],
  ['Одиночная бусина', '0,1 см²', 19.1753, { shape: 'single' }, 0.1],
  ['Одиночная бусина', '0,01 см²', 27.1719, { shape: 'single' }, 0.01],
  ['Цепочка 11 бусин', '1 см²', 18.3350, { shape: 'chain', nx: 11 }, 1.0],
  ['Раскладка 5×5', '1 см²', 48.0957, { shape: 'grid', nx: 5, ny: 5 }, 1.0],
  ['Раскладка 7×7', '1 см²', 48.7382, { shape: 'grid', nx: 7, ny: 7 }, 1.0],
  ['Раскладка 9×9', '1 см²', 48.4382, { shape: 'grid', nx: 9, ny: 9 }, 1.0],
];

function buildValidation() {
  const base = { shape: 'single', nx: 1, ny: 1, radius: 10, d: REF.d, pitch: REF.pitch, wU: REF.wU, rho: REF.rho };
  const tb = $('vtab').querySelector('tbody');
  let s2 = 0;
  for (const [name, av, mc, over, a] of MCPOINTS) {
    const c = { ...base, ...over };
    const v = doseRate(c, a);
    const e = 100 * (v / mc - 1); s2 += e * e;
    const tr = document.createElement('tr');
    tr.innerHTML = `<td>${name}</td><td class="num-col">${av}</td>`
      + `<td class="num-col">${mc.toFixed(2).replace('.', ',')}</td>`
      + `<td class="num-col">${v.toFixed(2).replace('.', ',')}</td>`
      + `<td class="num-col">${(e >= 0 ? '+' : '−') + Math.abs(e).toFixed(2).replace('.', ',')} %</td>`;
    tb.appendChild(tr);
  }
  const tr = document.createElement('tr');
  tr.innerHTML = `<td colspan="4"><b>Среднеквадратичное отклонение модели от Geant4</b></td>`
    + `<td class="num-col"><b>${Math.sqrt(s2 / MCPOINTS.length).toFixed(2).replace('.', ',')} %</b></td>`;
  tb.appendChild(tr);
}

// ------------------------------------------------------------------- запуск
function bind() {
  ['shape', 'nx', 'ny', 'radius', 'pitch', 'd', 'rho', 'wU', 'tses', 'nses']
    .forEach(id => $(id).addEventListener('input', () => recalc($(id) === $('shape'))));
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
  addEventListener('resize', () => recalc());
}

try {
  scene = new Scene3D($('cv'));
} catch (e) {
  $('cv').outerHTML = '<div class="callout">Трёхмерная визуализация недоступна: '
    + 'браузер не поддерживает WebGL. Расчётная часть работает без неё.</div>';
  console.error(e);
}
bind();
buildValidation();
recalc(true);

// точка входа для внешней проверки расчёта из консоли браузера
window.__calc = { scene, recalc, doseRate, doseAt, layout, cfg };
