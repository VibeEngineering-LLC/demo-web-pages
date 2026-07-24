// 3D-сцена: бусины на коже + поле мощности дозы Hp(0,07) в виде рельефа/карты.
import * as THREE from './vendor/three.module.min.js';
import { doseAt, beadResponse, layout, REF } from './physics.js?v=2';

const NG = 120;            // разбиение сетки поля
const RELIEF_MM = 14;      // высота рельефа при масштабе 100 %, мм (абсолютная,
                           // чтобы бусины оставались соизмеримы с поверхностью поля)

// Палитра поля (inferno-подобная), t = 0…1
function colorAt(t, out) {
  const stops = [
    [0.00, 0.001, 0.000, 0.014], [0.15, 0.129, 0.047, 0.281],
    [0.30, 0.325, 0.067, 0.427], [0.45, 0.523, 0.130, 0.395],
    [0.60, 0.717, 0.215, 0.290], [0.75, 0.883, 0.372, 0.146],
    [0.90, 0.977, 0.606, 0.024], [1.00, 0.988, 0.998, 0.645]];
  t = Math.max(0, Math.min(1, t));
  for (let i = 1; i < stops.length; i++) {
    if (t <= stops[i][0]) {
      const a = stops[i - 1], b = stops[i], f = (t - a[0]) / (b[0] - a[0]);
      out.setRGB(a[1] + f * (b[1] - a[1]), a[2] + f * (b[2] - a[2]), a[3] + f * (b[3] - a[3]));
      return out;
    }
  }
  return out.setRGB(1, 1, 1);
}

// Простая карта окружения: светлый «верх», тёплый «низ» и мягкая полоса блика.
// Нужна только для отражений на стекле — без неё бусины выглядят пластиковыми.
function makeEnvMap() {
  const c = document.createElement('canvas'); c.width = 256; c.height = 128;
  const g = c.getContext('2d');
  const grd = g.createLinearGradient(0, 0, 0, 128);
  grd.addColorStop(0.00, '#ffffff'); grd.addColorStop(0.45, '#dfe6ee');
  grd.addColorStop(0.55, '#8e8578'); grd.addColorStop(1.00, '#4a453d');
  g.fillStyle = grd; g.fillRect(0, 0, 256, 128);
  const spot = g.createRadialGradient(70, 34, 2, 70, 34, 42);
  spot.addColorStop(0, '#ffffff'); spot.addColorStop(1, 'rgba(255,255,255,0)');
  g.fillStyle = spot; g.fillRect(0, 0, 256, 128);
  const t = new THREE.CanvasTexture(c);
  t.mapping = THREE.EquirectangularReflectionMapping;
  t.colorSpace = THREE.SRGBColorSpace;
  return t;
}

export class Scene3D {
  constructor(canvas) {
    this.canvas = canvas;
    this.renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true });
    this.renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
    this.scene = new THREE.Scene();
    this.camera = new THREE.PerspectiveCamera(38, 1, 0.5, 4000);

    this.scene.add(new THREE.HemisphereLight(0xffffff, 0x404040, 1.5));
    const dl = new THREE.DirectionalLight(0xffffff, 1.4); dl.position.set(40, -60, 90);
    this.scene.add(dl);

    // поверхность поля дозы
    this.geo = new THREE.PlaneGeometry(1, 1, NG, NG);
    this.geo.setAttribute('color', new THREE.BufferAttribute(new Float32Array((NG + 1) * (NG + 1) * 3), 3));
    this.mesh = new THREE.Mesh(this.geo, new THREE.MeshStandardMaterial({
      vertexColors: true, roughness: 0.85, metalness: 0.0, side: THREE.DoubleSide,
    }));
    this.scene.add(this.mesh);

    // подложка «кожа»
    this.skin = new THREE.Mesh(new THREE.PlaneGeometry(1, 1),
      new THREE.MeshStandardMaterial({ color: 0xd7a893, roughness: 1.0 }));
    this.skin.position.z = -0.15;
    this.scene.add(this.skin);

    // окружение для бликов на стекле (процедурная эквидистантная карта)
    this.scene.environment = makeEnvMap();

    // бусины: рокайль — приплюснутый тор со сквозным отверстием.
    // Внешний диаметр 1, внутренний 0,2, толщина по z 0,4 в единичных координатах.
    this.beads = null;
    this.beadGeo = new THREE.TorusGeometry(0.30, 0.20, 18, 40);
    this.beadMat = new THREE.MeshPhysicalMaterial({
      color: 0xc6e63a, emissive: 0x86b300, emissiveIntensity: 0.32,
      roughness: 0.05, metalness: 0.0, clearcoat: 1.0, clearcoatRoughness: 0.06,
      ior: 1.52, reflectivity: 0.6, transparent: true, opacity: 0.82,
      side: THREE.DoubleSide,
    });

    // кольцо усреднения (1 см² и т. п.)
    this.ring = new THREE.Mesh(new THREE.RingGeometry(1, 1.04, 64),
      new THREE.MeshBasicMaterial({ color: 0x2b5f8a, side: THREE.DoubleSide }));
    this.scene.add(this.ring);

    // орбита
    this.az = -0.6; this.el = 0.85; this.dist = 60; this.target = new THREE.Vector3(0, 0, 0);
    this._bindControls();
    this._resize();
    addEventListener('resize', () => { this._resize(); this.render(); });
  }

  _bindControls() {
    const c = this.canvas; let drag = false, px = 0, py = 0;
    c.style.touchAction = 'none';
    const down = e => { drag = true; px = e.clientX; py = e.clientY; c.setPointerCapture(e.pointerId); };
    const move = e => {
      if (!drag) return;
      // как в привычных орбитальных контролах: тянем вниз — камера поднимается.
      // Угол места допускает отрицательные значения: поле дозы можно осмотреть снизу.
      this.az -= (e.clientX - px) * 0.008;
      this.el = Math.max(-1.50, Math.min(1.50, this.el + (e.clientY - py) * 0.006));
      px = e.clientX; py = e.clientY; this.render();
    };
    const up = e => { drag = false; try { c.releasePointerCapture(e.pointerId); } catch (_) { } };
    c.addEventListener('pointerdown', down); c.addEventListener('pointermove', move);
    c.addEventListener('pointerup', up); c.addEventListener('pointercancel', up);
    c.addEventListener('wheel', e => {
      e.preventDefault();
      this.dist = Math.max(8, Math.min(600, this.dist * Math.exp(e.deltaY * 0.0012)));
      this.render();
    }, { passive: false });
  }

  _resize() {
    const r = this.canvas.getBoundingClientRect();
    const w = Math.max(200, r.width), h = Math.max(200, r.height);
    this.renderer.setSize(w, h, false);
    this.camera.aspect = w / h; this.camera.updateProjectionMatrix();
  }

  // cfg — конфигурация из physics.js; opts.relief — высота рельефа (0 = плоская карта)
  update(cfg, opts) {
    const centers = layout(cfg), tab = beadResponse(cfg.d / 2);
    // размер сцены
    let ext = 0;
    for (const [x, y] of centers) ext = Math.max(ext, Math.abs(x), Math.abs(y));
    ext = Math.max(ext + cfg.d / 2 + 8, 12);
    this.ext = ext;

    // поле на сетке
    const N = NG + 1, pos = this.geo.attributes.position, col = this.geo.attributes.color;
    const vals = new Float64Array(N * N); let vmax = 0;
    for (let j = 0; j < N; j++) for (let i = 0; i < N; i++) {
      const x = -ext + 2 * ext * i / NG, y = -ext + 2 * ext * j / NG;
      const v = doseAt(cfg, x, y, tab, centers);
      vals[j * N + i] = v; if (v > vmax) vmax = v;
    }
    this.vmax = vmax;
    const c = new THREE.Color(), relief = opts.relief * RELIEF_MM;
    for (let j = 0; j < N; j++) for (let i = 0; i < N; i++) {
      const k = j * N + i, t = vmax > 0 ? vals[k] / vmax : 0;
      // индексация PlaneGeometry: строки идут сверху вниз
      const idx = (NG - j) * N + i;
      // рельеф уходит ВНИЗ: доза набирается в коже под бисером, а бусины остаются
      // на поверхности и не перекрываются полем
      pos.setXYZ(idx, -ext + 2 * ext * i / NG, -ext + 2 * ext * j / NG, -Math.pow(t, 0.6) * relief);
      colorAt(Math.pow(t, 0.55), c);
      col.setXYZ(idx, c.r, c.g, c.b);
    }
    pos.needsUpdate = true; col.needsUpdate = true;
    this.geo.computeVertexNormals();
    this.mesh.material.transparent = false;
    this.mesh.material.opacity = 1.0;
    this.mesh.material.depthWrite = true;

    // «кожа» — полупрозрачная поверхность на z = 0, сквозь неё видно поле в глубине
    this.skin.scale.set(2 * ext * 1.18, 2 * ext * 1.18, 1);
    this.skin.material.transparent = relief > 0.05;
    this.skin.material.opacity = relief > 0.05 ? 0.30 : 1.0;
    this.skin.position.z = relief > 0.05 ? 0 : -0.15;

    // бусины
    if (this.beads) { this.scene.remove(this.beads); this.beads.dispose && this.beads.dispose(); }
    const h = cfg.d * REF.hOverD;
    this.beads = new THREE.InstancedMesh(this.beadGeo, this.beadMat, centers.length);
    const M = new THREE.Matrix4(), q = new THREE.Quaternion(),
      sc = new THREE.Vector3(cfg.d, cfg.d, h / 0.4), p = new THREE.Vector3();
    centers.forEach(([x, y], i) => {
      p.set(x, y, h / 2);            // бусины лежат на коже (z = 0)
      this.beads.setMatrixAt(i, M.compose(p, q, sc));
    });
    this.beads.instanceMatrix.needsUpdate = true;
    this.scene.add(this.beads);

    // кольцо усреднения
    const Rav = Math.sqrt(opts.area / Math.PI) * 10;
    this.ring.scale.set(Rav, Rav, 1);
    this.ring.position.z = h + 0.6;            // над бусинами, на уровне кожи
    this.ring.visible = opts.showRing;

    if (opts.reframe) this.dist = ext * 2.45;
    this.render();
  }

  render() {
    // при осмотре снизу подложка кожи только мешала бы — убираем её
    this.skin.visible = this.el > 0.02;
    const ce = Math.cos(this.el), se = Math.sin(this.el);
    this.camera.position.set(
      this.target.x + this.dist * ce * Math.cos(this.az),
      this.target.y + this.dist * ce * Math.sin(this.az),
      this.target.z + this.dist * se);
    this.camera.up.set(0, 0, 1);
    this.camera.lookAt(this.target);
    this.renderer.render(this.scene, this.camera);
  }
}
