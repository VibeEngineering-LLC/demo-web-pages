// Мощность эквивалентной дозы Hp(0,07) от уранового стеклянного бисера на коже.
// Модель: точечное поверхностное ядро h(r), откалиброванное по 7 точкам Geant4
// (одна бусина при усреднении 0,01 / 0,1 / 1 см²; цепочка 11; коврики 5×5, 7×7, 9×9),
// среднеквадратичное отклонение подгонки 0,68 %.
//
//   h(r) = C · exp(−(r/a)^b) / (r² + r0²)^s          [r в мм]
//   эмиссия по лицевой площадке бусины: q(ρ) ∝ (1 − (ρ/a_б)²)^m , среднее по площади = 1
//
// Вклад бусины пропорционален площади её лицевой площадки: β-частицы выходят только
// из приповерхностного слоя, поэтому «толстая» бусина светит площадью, а не объёмом.

export const KERNEL = { C: 1.6145209, a: 6.915497, b: 4.968286, r0: 0.214094, s: 0.509036, m: 2.184789 };

export const REF = {
  d: 4.10,          // мм — диаметр бусины-рокайля в расчёте Geant4
  aBead: 2.05,      // мм — радиус лицевой площадки
  pitch: 4.10,      // мм — шаг плотной укладки
  wU: 1.85,         // % масс. — доля урана в стекле
  rho: 2.50,        // г/см³ — плотность стекла
  hOverD: 2.20 / 4.10, // высота рокайля / диаметр
  nu: 5.19,         // см²/г — коэффициент поглощения β (Pa-234m, Loevinger)
  aSpec: 2.27e5,    // Бк/кг по U-238 при wU = 1,85 %
  massBead: 63.96,  // мг
};

// Удельная активность природного урана по U-238, Бк на кг урана.
export const A_U238_PER_KG_U = REF.aSpec / (REF.wU / 100);

// ---------------------------------------------------------------- квадратуры
// Узлы и веса Гаусса—Лежандра на [−1, 1] (Ньютон по нулям полинома).
function leggauss(n) {
  const x = new Float64Array(n), w = new Float64Array(n);
  for (let i = 0; i < n; i++) {
    let z = Math.cos(Math.PI * (i + 0.75) / (n + 0.5)), pp = 0;
    for (let it = 0; it < 100; it++) {
      let p0 = 1, p1 = 0;
      for (let j = 0; j < n; j++) { const p2 = p1; p1 = p0; p0 = ((2 * j + 1) * z * p1 - j * p2) / (j + 1); }
      pp = n * (z * p0 - p1) / (z * z - 1);
      const dz = p0 / pp; z -= dz;
      if (Math.abs(dz) < 1e-14) break;
    }
    x[i] = z; w[i] = 2 / ((1 - z * z) * pp * pp);
  }
  return { x, w };
}

// Узлы по диску радиуса R: радиальная квадратура Гаусса × равномерный азимут.
// Сумма весов = πR².
function diskNodes(R, nr, na) {
  const { x, w } = leggauss(nr), xs = [], ys = [], ws = [];
  for (let i = 0; i < nr; i++) {
    const r = R * 0.5 * (x[i] + 1), wr = w[i] * 0.5 * R * r * (2 * Math.PI / na);
    for (let k = 0; k < na; k++) {
      const th = (k + 0.5) * 2 * Math.PI / na;
      xs.push(r * Math.cos(th)); ys.push(r * Math.sin(th)); ws.push(wr);
    }
  }
  return { x: xs, y: ys, w: ws };
}

// ------------------------------------------------- отклик одиночной бусины K1(r)
// K1(r) — мощность дозы в точке кожи на расстоянии r от центра бусины,
// то есть ядро h, свёрнутое с профилем эмиссии по лицевой площадке.
// Возвращает интерполируемую таблицу; строится один раз на набор параметров.
const K1_RMAX = 80, K1_N = 1600;   // мм, число узлов

export function beadResponse(aBead) {
  const { C, a, b, r0, s, m } = KERNEL;
  const NR = 12, NA = 24;
  const nd = diskNodes(aBead, NR, NA);
  // нормировка профиля: среднее по площади = 1
  let sw = 0, sp = 0;
  const prof = new Float64Array(nd.x.length);
  for (let i = 0; i < nd.x.length; i++) {
    const rho2 = (nd.x[i] * nd.x[i] + nd.y[i] * nd.y[i]) / (aBead * aBead);
    prof[i] = Math.pow(Math.max(0, 1 - rho2), m);
    sw += nd.w[i]; sp += nd.w[i] * prof[i];
  }
  const norm = sp / sw;
  for (let i = 0; i < prof.length; i++) prof[i] *= nd.w[i] / norm;

  const tab = new Float64Array(K1_N + 1);
  for (let k = 0; k <= K1_N; k++) {
    const r = K1_RMAX * k / K1_N;
    let acc = 0;
    for (let i = 0; i < nd.x.length; i++) {
      const dx = r - nd.x[i], dy = nd.y[i];
      const rr = Math.sqrt(dx * dx + dy * dy);
      acc += prof[i] * C * Math.exp(-Math.pow(rr / a, b)) / Math.pow(rr * rr + r0 * r0, s);
    }
    tab[k] = acc;
  }
  return tab;
}

function k1(tab, r) {
  if (r >= K1_RMAX) return 0;
  const t = r * K1_N / K1_RMAX, i = t | 0, f = t - i;
  return tab[i] * (1 - f) + tab[i + 1] * f;
}

// ------------------------------------------------------------------ геометрия
// Возвращает центры бусин, мм. Раскладка центрирована в начале координат.
export function layout(cfg) {
  const p = cfg.pitch, c = [];
  if (cfg.shape === 'single') return [[0, 0]];
  if (cfg.shape === 'chain') {
    const n = cfg.nx, o = -(n - 1) / 2 * p;
    for (let i = 0; i < n; i++) c.push([o + i * p, 0]);
    return c;
  }
  if (cfg.shape === 'grid') {
    const ox = -(cfg.nx - 1) / 2 * p, oy = -(cfg.ny - 1) / 2 * p;
    for (let j = 0; j < cfg.ny; j++) for (let i = 0; i < cfg.nx; i++) c.push([ox + i * p, oy + j * p]);
    return c;
  }
  // 'disk' — квадратная укладка, обрезанная окружностью радиуса R
  const R = cfg.radius, n = Math.ceil(2 * R / p) + 2, o = -(n - 1) / 2 * p;
  for (let j = 0; j < n; j++) for (let i = 0; i < n; i++) {
    const x = o + i * p, y = o + j * p;
    if (Math.hypot(x, y) <= R) c.push([x, y]);
  }
  return c;
}

// -------------------------------------------------------------- масштабы задачи
// Доля урана входит линейно. Размер бусины — через площадь лицевой площадки
// (в интеграле) и через насыщение по толщине: β выходят из слоя ~1/(ν·ρ).
export function thicknessFactor(d, rho) {
  const h = d * REF.hOverD / 10;                 // см
  return 1 - Math.exp(-REF.nu * rho * h);
}

export function scaleFactor(cfg) {
  const fRef = thicknessFactor(REF.d, REF.rho);
  return (cfg.wU / REF.wU) * (thicknessFactor(cfg.d, cfg.rho) / fRef);
}

// ------------------------------------------------------------------- результат
// Мощность дозы, усреднённая по диску площадью area (см²) с центром в (cx, cy).
export function doseRate(cfg, area, cx = 0, cy = 0, tab = null, cent = null) {
  const aBead = cfg.d / 2;
  const T = tab || beadResponse(aBead);
  const centers = cent || layout(cfg);
  const R = Math.sqrt(area / Math.PI) * 10;      // мм
  const nd = diskNodes(R, 14, 28);
  let sw = 0; for (const w of nd.w) sw += w;
  let acc = 0;
  for (const [bx, by] of centers) {
    for (let i = 0; i < nd.x.length; i++) {
      const dx = cx + nd.x[i] - bx, dy = cy + nd.y[i] - by;
      acc += nd.w[i] * k1(T, Math.sqrt(dx * dx + dy * dy));
    }
  }
  return acc / sw * scaleFactor(cfg);
}

// Точечная (не усреднённая) мощность дозы — для карты поля.
export function doseAt(cfg, x, y, tab, centers) {
  let acc = 0;
  for (const [bx, by] of centers) acc += k1(tab, Math.hypot(x - bx, y - by));
  return acc * scaleFactor(cfg);
}

// --------------------------------------------------------------- оформление чисел
// Округление по правилам представления результата: погрешность до 1–2 значащих
// цифр, значение — до того же разряда.
export function fmtPM(v, rel, lang = 'ru') {
  const u = v * rel;
  if (!isFinite(v) || v <= 0) return { v: '0', u: '0' };
  const e = Math.floor(Math.log10(u));
  const lead = u / Math.pow(10, e);
  const dig = lead < 3 ? 1 : 0;                 // 2 значащие, если первая 1 или 2
  const step = Math.pow(10, e - dig);
  const ur = Math.ceil(u / step) * step, vr = Math.round(v / step) * step;
  const dec = Math.max(0, dig - e);
  // ГОСТ 8.417 — в русском тексте десятичная запятая, в английском точка
  const f = x => lang === 'ru' ? x.toFixed(dec).replace('.', ',') : x.toFixed(dec);
  return { v: f(vr), u: f(ur) };
}
