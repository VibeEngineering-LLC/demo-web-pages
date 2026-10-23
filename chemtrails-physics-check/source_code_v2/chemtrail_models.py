# chemtrail_models.py (v2, 2026-10-18)
# Единый воспроизводимый расчёт. Все числа отчёта пишутся в results_v2/results.json этим скриптом.
# Допущения помечены ASSUMPTION; значения без источника помечены TO_VERIFY.
import json, math, os
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "results_v2")
os.makedirs(OUT, exist_ok=True)
RES = {}

# ---------- физические константы (стандартные значения) ----------
G0 = 9.80665          # м/с^2
R_AIR = 287.05        # Дж/(кг К)
CP_AIR = 1004.0       # Дж/(кг К)
EPS = 0.622           # M_H2O / M_air
Q_FUEL = 43.2e6       # Дж/кг, низшая теплота сгорания Jet A (TO_VERIFY по паспорту топлива)
RHO_ICE = 917.0       # кг/м^3
MU0, T0, S_SUTH = 1.716e-5, 273.15, 110.4   # Сазерленд, вязкость воздуха
EI_H2O = 1.25         # кг H2O / кг топлива (стехиометрия сгорания углеводородов)
ETA = 0.35            # КПД двигателя, ASSUMPTION (диапазон 0.30-0.35)


# ---------- ВХОДНЫЕ ДАННЫЕ С ИСТОЧНИКАМИ ----------
# ICAO, Annual Report 2024, Presentation of 2024 Air Transport Statistical Results, Table 4 (world total,
#   scheduled services, international + domestic): 58 725 млн авиа-км, 37 424 тыс. вылетов. Без нерегулярных, ГА и военных рейсов.
ICAO_2024_AIRCRAFT_KM = 58725e6         # км/год
ICAO_2024_DEPARTURES = 37424e3          # вылетов/год
# IATA, Global Outlook for Air Transport (Dec 2025 / Jun 2026): расход топлива 2024 = 99 млрд галлонов США.
IATA_FUEL_2024_GAL = 99e9
GAL_TO_L = 3.785411784
RHO_JETA = 0.80                         # кг/л, ASSUMPTION (типично 0.775-0.84)
# Smith & Wagner 2018, ERL 13, 124001 (DOI 10.1088/1748-9326/aae98d): ~4000 рейсов в 1-й год, +~4000 рейсов/год;
#   ~0.1 Мт S в 1-й год, линейный рост ~0.1 Мт/год (текст статьи, прочитан по выдержке из поисковой выдачи, не по полному PDF).
SW_FLIGHTS_Y1 = 4000.0
SW_FLIGHTS_Y15 = 60000.0                # рейсов/год к 15-му году: пресс-сводка статьи (вторичный источник), 4000+14*4000=60000 совпадает с линейным ростом из аннотации
SW_S_MT_Y1 = 0.1                        # Мт серы в год (год 1)
SW_S_MT_Y15 = 0.1 * 15                  # Мт серы в год, экстраполяция линейного роста до 15-го года (арифметика автора скрипта)

D_KM = ICAO_2024_AIRCRAFT_KM
FUEL_TOTAL_KG = IATA_FUEL_2024_GAL * GAL_TO_L * RHO_JETA
FUEL_PER_KM = FUEL_TOTAL_KG / D_KM      # кг топлива на км, среднее по флоту (IATA топливо / ICAO км: охват не идентичен)
RES["in_icao_aircraft_km"] = D_KM
RES["in_icao_departures"] = ICAO_2024_DEPARTURES
RES["in_mean_flight_km"] = D_KM / ICAO_2024_DEPARTURES
RES["in_fuel_total_Mt"] = FUEL_TOTAL_KG / 1e9
RES["in_fuel_per_km_kg"] = FUEL_PER_KM
RES["in_sw_flights_y1_share_of_departures"] = SW_FLIGHTS_Y1 / ICAO_2024_DEPARTURES
RES["in_sw_flights_y15_share_of_departures"] = SW_FLIGHTS_Y15 / ICAO_2024_DEPARTURES

def isa(h):
    """ISA 1976 до 20 км: h [м] -> T [К], p [Па]."""
    p11 = 101325.0 * (216.65 / 288.15) ** (G0 / (R_AIR * 0.0065))
    if h <= 11000.0:
        T = 288.15 - 0.0065 * h
        p = 101325.0 * (T / 288.15) ** (G0 / (R_AIR * 0.0065))
    else:
        T = 216.65
        p = p11 * math.exp(-G0 * (h - 11000.0) / (R_AIR * T))
    return T, p

def T_lc(p):
    """Критическая температура Шмидта-Аппельмана (Schumann 1996), p [Па]."""
    G = EI_H2O * CP_AIR * p / (EPS * Q_FUEL * (1 - ETA))   # [Па/К]
    L = math.log(G - 0.053)
    return 226.69 + 9.43 * L + 0.72 * L * L, G

def viscosity(T):
    return MU0 * (T / T0) ** 1.5 * (T0 + S_SUTH) / (T + S_SUTH)

# ================= Модель 1: термодинамика (SAC) =================
hs = np.arange(0.0, 20001.0, 50.0)
T_isa = np.zeros_like(hs); p_isa = np.zeros_like(hs); Tlc = np.zeros_like(hs); Gs = np.zeros_like(hs)
for i, h in enumerate(hs):
    T, p = isa(h); Tc, G = T_lc(p)
    T_isa[i], p_isa[i], Tlc[i], Gs[i] = T, p, Tc, G
h_km = hs / 1000.0
ok = T_isa < Tlc
RES["m1_G_at_250hPa_PaK"] = float(T_lc(25000.0)[1])
RES["m1_Tlc_at_250hPa_K"] = float(T_lc(25000.0)[0])
RES["m1_Tlc_at_250hPa_C"] = float(T_lc(25000.0)[0] - 273.15)
RES["m1_ok_min_km"] = float(h_km[ok].min()) if ok.any() else None
RES["m1_ok_max_km"] = float(h_km[ok].max()) if ok.any() else None
RES["m1_n_segments"] = int(np.sum(np.diff(ok.astype(int)) == 1) + (1 if ok[0] else 0))
for h in [5, 7, 8, 9, 10, 11, 12, 13, 15]:
    i = int(round(h * 1000 / 50))
    RES[f"m1_margin_K_{h}km"] = float(Tlc[i] - T_isa[i])
for dT in [-10, -5, 0, 5, 10]:
    mask = (h_km >= 8) & (h_km <= 13)
    frac = float(np.mean((T_isa[mask] + dT) < Tlc[mask]))
    RES[f"m1_frac_8_13km_dT{dT:+d}K"] = frac

# ================= Модель 2: оптика (геометрическая оптика, Qext=2) =================
# Только вода выхлопа; расход топлива на км = среднее по флоту (IATA топливо / ICAO км).
water_per_km = EI_H2O * FUEL_PER_KM                    # кг воды на км следа
m_l = water_per_km / 1000.0                            # кг/м
RES["m2_water_kg_per_km"] = water_per_km
def k_ext(r_um):
    return 3 * 2.0 / (4 * RHO_ICE * r_um * 1e-6)      # м^2/кг
radii = [0.5, 1.0, 2.0, 5.0]
widths = [100.0, 300.0, 1000.0]
for r in radii:
    RES[f"m2_kext_r{r}um_m2kg"] = k_ext(r)
    RES[f"m2_N_per_km_r{r}um"] = water_per_km / (RHO_ICE * 4/3 * math.pi * (r*1e-6)**3)   # частиц на км следа
    for W in widths:
        RES[f"m2_tau_r{r}um_W{int(W)}m"] = k_ext(r) * m_l / W
for mult in [0.5, 2.0]:   # чувствительность: узкофюзеляжный / тяжёлый широкофюзеляжный самолёт
    RES[f"m2_tau_r1.0um_W300m_fuelx{mult}"] = k_ext(1.0) * (m_l * mult) / 300.0

# ================= Модель 3: рассеивание =================
U = 40.0              # м/с, ASSUMPTION (струйное течение 30-60)
Ks = [10.0, 50.0, 200.0]   # м^2/с, ASSUMPTION (диапазон, без источника)
times_h = [0.5, 1.0, 3.0, 6.0]
for K in Ks:
    for th in times_h:
        t = th * 3600.0
        RES[f"m3_sigma_K{int(K)}_t{th}h_km"] = math.sqrt(2 * K * t) / 1000.0
for th in times_h:
    RES[f"m3_drift_t{th}h_km"] = U * th * 3600.0 / 1000.0

# ================= Модель 4: седиментация (Стокс + Каннингем) =================
T12, p12 = isa(12000.0)
rho_a = p12 / (R_AIR * T12)
mu12 = viscosity(T12)
lam = mu12 / (0.499 * p12) * math.sqrt(math.pi * R_AIR * T12 / 8)   # средняя длина свободного пробега, м
RES["m4_rho_air_12km"] = rho_a
RES["m4_mu_12km_Pas"] = mu12
RES["m4_mfp_12km_um"] = lam * 1e6
def v_stokes(r_um):
    r = r_um * 1e-6
    Kn = lam / r
    C = 1 + Kn * (1.257 + 0.4 * math.exp(-1.1 / Kn))
    return 2.0 / 9.0 * (RHO_ICE - rho_a) * G0 * r * r / mu12 * C, C
for r in [0.5, 1.0, 2.0, 5.0, 10.0]:
    v, C = v_stokes(r)
    RES[f"m4_v_r{r}um_mm_s"] = v * 1000
    RES[f"m4_C_r{r}um"] = C
    RES[f"m4_fall_12km_yr_r{r}um"] = 12000.0 / v / (365.25 * 86400)

# ================= Модель 3b: рассеивание со сдвигом ветра =================
# Линейный сдвиг s [1/с], вертикальная диффузия Kz, горизонтальная диффузия Kh. Ось следа перпендикулярна направлению сдвига
# (максимальное расползание). Дисперсия вдоль сдвига (замкнутая форма; проверяется Монте-Карло ниже):
#   sigma^2(t) = sigma0^2 + 2 Kh t + s^2 (sigz0^2 t^2 + (2/3) Kz t^3)
# Диапазоны параметров: Kh 5-20 м^2/с и Kz 0.01-0.5 м^2/с (Schumann et al. 2012 GMD 5, 543; Duerbeck & Gerz по обзору ACCRI);
# s = 0.001 и 0.002 1/с — значения в описанных случаях (Schumann et al. 2017, ACP 17, 403); 0.005 и 0.01 — ASSUMPTION (верхняя граница).
W0_VIS = 120.0        # м, начальная видимая ширина (80-150 м по лидару, Schumann et al. 2017)
D0 = 125.0            # м, глубина следа после вихревой фазы (пример из Schumann et al. 2017)
SIG0 = W0_VIS / (2.0 * math.sqrt(2.0))      # видимая ширина W = 2*sqrt(2)*sigma (1/e-ширина; соглашение скрипта)
SIGZ0 = D0 / (2.0 * math.sqrt(2.0))
def sigma_x(t, s_, Kh, Kz):
    return math.sqrt(SIG0**2 + 2*Kh*t + s_**2 * (SIGZ0**2 * t**2 + (2.0/3.0) * Kz * t**3))
def w_vis(sig): return 2.0 * math.sqrt(2.0) * sig
S_SET = [0.0, 0.001, 0.002, 0.005, 0.01]
KH_SET = [5.0, 20.0]
KZ_SET = [0.01, 0.1, 0.5]
DILUTION = 4.0        # во сколько раз падает пиковая колонка вещества (tau/tau0 = 1/DILUTION): условный порог, не наблюдаемая величина
def t_dilution(s_, Kh, Kz):
    lo, hi = 1.0, 1e7
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        if SIG0 / sigma_x(mid, s_, Kh, Kz) > 1.0 / DILUTION: lo = mid
        else: hi = mid
    return 0.5 * (lo + hi)
for s_ in S_SET:
    for Kh in KH_SET:
        for Kz in KZ_SET:
            tag = f"s{s_:g}_Kh{Kh:g}_Kz{Kz:g}"
            for th in [1.0, 3.0, 6.0]:
                RES[f"m3b_Wvis_km_{tag}_t{th:g}h"] = w_vis(sigma_x(th * 3600.0, s_, Kh, Kz)) / 1000.0
            RES[f"m3b_mean_rate_ms_{tag}"] = (w_vis(sigma_x(3600.0, s_, Kh, Kz)) - w_vis(sigma_x(60.0, s_, Kh, Kz))) / (3600.0 - 60.0)
            RES[f"m3b_t_dilution_h_{tag}"] = t_dilution(s_, Kh, Kz) / 3600.0
# проверка замкнутой формулы методом Монте-Карло (проверяет формулу для заданной модели, а не наблюдения)
rng = np.random.default_rng(12345)
Nmc, dtmc = 200000, 10.0
s_mc, Kh_mc, Kz_mc = 0.005, 20.0, 0.1
z = rng.normal(0.0, SIGZ0, Nmc); x = rng.normal(0.0, SIG0, Nmc)
checks = {3600: "1h", 10800: "3h", 21600: "6h"}
for step in range(1, int(21600 / dtmc) + 1):
    x += s_mc * z * dtmc + math.sqrt(2 * Kh_mc * dtmc) * rng.standard_normal(Nmc)
    z += math.sqrt(2 * Kz_mc * dtmc) * rng.standard_normal(Nmc)
    tcur = int(round(step * dtmc))
    if tcur in checks:
        RES[f"m3b_mc_sigma_m_{checks[tcur]}"] = float(np.std(x))
        RES[f"m3b_cf_sigma_m_{checks[tcur]}"] = sigma_x(tcur, s_mc, Kh_mc, Kz_mc)
        RES[f"m3b_mc_relerr_{checks[tcur]}"] = float(np.std(x) / sigma_x(tcur, s_mc, Kh_mc, Kz_mc) - 1.0)

# Диагностика: какая постоянная Dv дала бы лидарный рост глубины 0.3 м/с за 60-3600 с (Schumann et al. 2017, пересказ Freudenthaler et al.)
_dD = 0.3 * 3540.0
RES["m3c_lidar_depth_end_m"] = D0 + _dD
RES["m3c_Dv_needed_for_lidar_depth_m2s"] = (((D0 + _dD)**2 - D0**2) / 8.0) / (2.0 * 3540.0)

# ================= Модель 4b: оседание вещества (Стокс + Каннингем, интегрирование по ISA) =================
# Плотности: справочные значения, TO_VERIFY. Сферические частицы, только гравитационное оседание (без турбулентности, вымывания, коагуляции).
SUBST = {"ice": 917.0, "sulfate": 1700.0, "sio2": 2200.0, "al2o3": 3950.0, "tio2": 4230.0}
def v_settle_z(r_um, rho_p, z_m):
    T, p = isa(z_m); mu = viscosity(T); rho_a = p / (R_AIR * T)
    lam_ = mu / (0.499 * p) * math.sqrt(math.pi * R_AIR * T / 8)
    r = r_um * 1e-6; Kn = lam_ / r
    C = 1 + Kn * (1.257 + 0.4 * math.exp(-1.1 / Kn))
    v = 2.0 / 9.0 * (rho_p - rho_a) * G0 * r * r / mu * C
    return v, rho_a * v * 2 * r / mu       # скорость [м/с], число Рейнольдса
def fall_time_yr(r_um, rho_p, h0_m):
    dz = 50.0; zs = np.arange(dz / 2, h0_m, dz)
    tsum = sum(dz / v_settle_z(r_um, rho_p, z)[0] for z in zs)
    return tsum / (365.25 * 86400.0)
RE_MAX = 0.0
for name, rho_p in SUBST.items():
    for r_um in [0.1, 0.3, 1.0, 3.0, 10.0]:
        for h0 in [12000.0, 20000.0]:
            RES[f"m4b_fall_yr_{name}_r{r_um:g}_h{int(h0/1000)}km"] = fall_time_yr(r_um, rho_p, h0)
        for z in np.arange(25.0, 20000.0, 500.0):
            RE_MAX = max(RE_MAX, v_settle_z(r_um, rho_p, z)[1])
RES["m4b_Re_max"] = RE_MAX
RES["m4b_v_12km_mm_s_ice_r1"] = v_settle_z(1.0, SUBST["ice"], 12000.0)[0] * 1000
RES["m4b_v_12km_mm_s_al2o3_r1"] = v_settle_z(1.0, SUBST["al2o3"], 12000.0)[0] * 1000

# ================= Модель 3c: рассеивание с диффузиями, растущими с размером следа (формулы CoCiP) =================
# Формулы взяты из исходного кода pycontrails 0.63.5 (cocip/contrail_properties.py, cocip_params.py), реализующего Schumann (2012, GMD 5, 543):
#   Dh = 0.1 * S_T * D^2                          (D — глубина следа, S_T — полный сдвиг ветра)
#   Dv = w'^2 / N_BV + f_T * v_fall * D_eff       (w' = 0.1 м/с, f_T = 0.5 — значения по умолчанию в pycontrails; N_BV >= 0.001)
#   W = sqrt(8 sigma_yy), D = sqrt(8 sigma_zz)    (определение ширины и глубины в CoCiP)
#   пошаговая эволюция sigma_yy, sigma_zz, sigma_yz (plume_temporal_evolution); глубина ограничена max_depth = 1500 м.
# Здесь S_T = s (ось следа перпендикулярна сдвигу). Усиление сдвига из-за грубой сетки NWP (wind_shear_enhancement_factor) не применяется.
# N_BV = 0.011 и 0.027 1/с — значения в описанных случаях в Schumann et al. 2017 (ACP 17, 403); w', f_T — значения CoCiP по умолчанию.
W_MAXDEPTH = 1500.0
def cocip_like(s_, Nbv, r_ice_um, t_end=6*3600.0, dt=10.0, w_prime=0.1, f_T=0.5, h_m=10500.0, W0=W0_VIS, D0_=D0):
    vf = v_settle_z(r_ice_um, 917.0, h_m)[0]
    syy, szz, syz = W0**2/8.0, D0_**2/8.0, 0.0
    ts, Ws, Ds, Dhs, Dvs = [0.0], [W0], [D0_], [], []
    nsteps = int(round(t_end/dt))
    for k in range(nsteps):
        W = math.sqrt(8*syy); Dp = math.sqrt(8*szz)
        area = 2*math.pi*math.sqrt(max(syy*szz - syz**2, 0.0)); Deff = area / W
        Dh = 0.1 * s_ * Dp**2
        Dv = w_prime**2 / max(Nbv, 0.001) + f_T * vf * Deff
        Dv = min(Dv, (0.125*W_MAXDEPTH**2 - szz) / (2*dt))     # ограничение глубины как в plume_temporal_evolution
        syy_n = (2/3)*s_**2*Dv*dt**3 + s_**2*szz*dt**2 + 2*(Dh + s_*syz)*dt + syy
        szz_n = 2*Dv*dt + szz
        syz_n = s_*Dv*dt**2 + s_*szz*dt + syz
        syy, szz, syz = syy_n, szz_n, syz_n
        ts.append((k+1)*dt); Ws.append(math.sqrt(8*syy)); Ds.append(math.sqrt(8*szz)); Dhs.append(Dh); Dvs.append(Dv)
    return np.array(ts), np.array(Ws), np.array(Ds), np.array(Dhs), np.array(Dvs)
def _interp(ts, arr, t): return float(np.interp(t, ts, arr))
S3C = [0.0, 0.001, 0.002, 0.005, 0.01]; N3C = [0.011, 0.027]; R3C = [1.0, 10.0]
for s_ in S3C:
    for Nbv in N3C:
        for r_um in R3C:
            ts, Ws, Ds, Dhs, Dvs = cocip_like(s_, Nbv, r_um)
            tag = f"s{s_:g}_N{Nbv:g}_r{r_um:g}"
            for th in [1.0, 3.0, 6.0]:
                RES[f"m3c_Wvis_km_{tag}_t{th:g}h"] = _interp(ts, Ws, th*3600.0) / 1000.0
                RES[f"m3c_depth_m_{tag}_t{th:g}h"] = _interp(ts, Ds, th*3600.0)
            RES[f"m3c_rateW_ms_{tag}"] = (_interp(ts, Ws, 3600.0) - _interp(ts, Ws, 60.0)) / 3540.0
            RES[f"m3c_rateD_ms_{tag}"] = (_interp(ts, Ds, 3600.0) - _interp(ts, Ds, 60.0)) / 3540.0
            # время падения пиковой колонки (ось y) в DILUTION раз; колонка ~ 1/sqrt(sigma_yy) ~ 1/W
            idx = np.argmax(Ws / W0_VIS >= DILUTION)
            RES[f"m3c_t_dilution_h_{tag}"] = float(ts[idx] / 3600.0) if Ws[-1] / W0_VIS >= DILUTION else float("nan")
            RES[f"m3c_Dh_1h_{tag}"] = float(np.interp(3600.0, ts[:-1], Dhs)); RES[f"m3c_Dv_1h_{tag}"] = float(np.interp(3600.0, ts[:-1], Dvs))


# ================= Модель 5: массовый баланс =================
# Гипотеза H1: видимость следа создаёт само распылённое вещество (плотность льда как заглушка, r=1 мкм, W=300 м).
TAU_TARGETS = [0.05, 0.2]
W_REF, R_REF = 300.0, 1.0
for tau_t in TAU_TARGETS:
    m_req = tau_t * W_REF / k_ext(R_REF)   # кг/м
    RES[f"m5_H1_kg_per_km_tau{tau_t}"] = m_req * 1000.0
F_SCEN = [0.001, 0.01, 0.1, 1.0]   # доля авиа-км с распылением: ПАРАМЕТР сценария, не данные
for tau_t in TAU_TARGETS:
    for f in F_SCEN:
        Mt = RES[f"m5_H1_kg_per_km_tau{tau_t}"] * D_KM * f / 1e9
        RES[f"m5_H1_Mt_tau{tau_t}_f{f}"] = Mt
        RES[f"m5_H1_ratio_SWy1_tau{tau_t}_f{f}"] = Mt / SW_S_MT_Y1

# ================= Модель 2b: теория Ми вместо Qext = 2 =================
# Алгоритм BHMIE: Bohren C.F., Huffman D.R. (1983) Absorption and Scattering of Light by Small Particles, Wiley, прил. A.
# Только фактор эффективности ослабления Qext для однородной сферы. Длина волны 0,55 мкм.
# Показатели преломления (действительная часть, поглощение не учитывается) — справочные значения, TO_VERIFY:
#   лёд 1,311; сульфат (раствор H2SO4) 1,43; Al2O3 1,77; TiO2 (рутил) 2,6.
# Распределение по размерам: логнормальное, стандартное геометрическое отклонение 1,5 (ASSUMPTION), среднее Qext взвешено по площади сечения (r^2).
LAM_UM = 0.55
def mie_qext(m, x):
    nstop = int(x + 4.0 * x ** (1.0 / 3.0) + 2); y = m * x; nmx = int(max(nstop, abs(y)) + 15)
    D = [0j] * (nmx + 1)
    for n_ in range(nmx, 0, -1): D[n_ - 1] = n_ / y - 1.0 / (D[n_] + n_ / y)
    psi0, psi1, chi0, chi1 = math.cos(x), math.sin(x), -math.sin(x), math.cos(x)
    xi1 = complex(psi1, -chi1); q = 0.0
    for n_ in range(1, nstop + 1):
        psi = (2 * n_ - 1) * psi1 / x - psi0; chi = (2 * n_ - 1) * chi1 / x - chi0; xi = complex(psi, -chi)
        an = ((D[n_] / m + n_ / x) * psi - psi1) / ((D[n_] / m + n_ / x) * xi - xi1)
        bn = ((D[n_] * m + n_ / x) * psi - psi1) / ((D[n_] * m + n_ / x) * xi - xi1)
        q += (2 * n_ + 1) * (an.real + bn.real)
        psi0, psi1, chi0, chi1, xi1 = psi1, psi, chi1, chi, xi
    return 2.0 * q / (x * x)
# проверки реализации: геометрический предел и предел Рэлея
RES["m2b_check_large_x"] = mie_qext(complex(1.33, 0), 500.0)
RES["m2b_check_rayleigh_ratio"] = mie_qext(complex(1.5, 0), 0.1) / ((8.0 / 3.0) * 0.1 ** 4 * ((1.5 ** 2 - 1) / (1.5 ** 2 + 2)) ** 2)
SG = 1.5
def q_lognorm(nr, rmed_um, sg=SG, N=400):
    lr = np.linspace(math.log(rmed_um) - 3 * math.log(sg), math.log(rmed_um) + 3 * math.log(sg), N); r = np.exp(lr)
    w = np.exp(-0.5 * ((lr - math.log(rmed_um)) / math.log(sg)) ** 2) * r ** 2
    q = np.array([mie_qext(complex(nr, 0), 2 * math.pi * ri / LAM_UM) for ri in r])
    return float((q * w).sum() / w.sum())
NREF = {"ice": 1.311, "sulfate": 1.43, "al2o3": 1.77, "tio2": 2.6}
RHO_SUB = {"ice": 917.0, "sulfate": 1700.0, "al2o3": 3950.0, "tio2": 4230.0}
for nm_, nr in NREF.items():
    for rm in [0.5, 1.0]:
        Q = q_lognorm(nr, rm); RES[f"m2b_Q_{nm_}_r{rm:g}"] = Q
        k_m = 3 * Q / (4 * RHO_SUB[nm_] * rm * 1e-6)                    # м2/кг
        RES[f"m2b_k_{nm_}_r{rm:g}"] = k_m
        for tau_t in TAU_TARGETS:
            kgkm = float(tau_t) * 300.0 / k_m * 1000.0                    # кг/км при W = 300 м
            RES[f"m2b_kg_per_km_{nm_}_r{rm:g}_tau{tau_t}"] = kgkm
            RES[f"m2b_over_fuel_{nm_}_r{rm:g}_tau{tau_t}"] = kgkm / FUEL_PER_KM
    for rm in [0.5, 1.0]:
        pass
# вода выхлопа с Ми (лёд): τ и ширина, при которой τ = 0,05
for rm in [0.5, 1.0]:
    k_i = RES[f"m2b_k_ice_r{rm:g}"]
    for W in [100.0, 300.0, 1000.0]:
        RES[f"m2b_tau_water_r{rm:g}_W{int(W)}"] = k_i * (water_per_km / 1000.0) / W
    for tau_t in TAU_TARGETS:
        RES[f"m2b_Wmax_m_water_r{rm:g}_tau{tau_t}"] = k_i * (water_per_km / 1000.0) / float(tau_t)
# отношение массы вещества к массе воды выхлопа для того же следа (не зависит от Q, если частицы одинаковы)
RES["m2b_substance_over_water_ice_r1_tau0.05"] = RES["m2b_kg_per_km_ice_r1_tau0.05"] / water_per_km
RES["m2b_substance_over_water_ice_r1_tau0.2"] = RES["m2b_kg_per_km_ice_r1_tau0.2"] / water_per_km



# ================= Модель 5b: сравнение с перевозками (пассажиры, груз) и масса на один рейс =================
# ICAO, Presentation of 2024 Air Transport Statistical Results, Table 1 (world total, scheduled services, 2024):
#   пасс-км 9 097 611 млн; кресло-км 10 933 133 млн; грузовые т-км 243 740 млн; почтовые т-км 3 832 млн;
#   платные т-км (RTK) 1 089 914 млн; предельные т-км (ATK) 1 596 995 млн; коэфф. загрузки по массе 68 %.
#   RTK посчитаны по фактической массе пассажиров, сообщённой государствами (примечание 1 к таблицам).
# ICAO, Annual Report 2024, The World of Air Transport in 2024: 4,7 млрд пассажиров; 60,8 млн т груза (регулярные рейсы).
# IATA, Global Outlook for Air Transport, Dec 2025, Table 3: груз 2024 = 67,5 млн т (вся отрасль).
ICAO_RPK = 9097611e6; ICAO_FTK = 243740e6; ICAO_MTK = 3832e6; ICAO_RTK = 1089914e6; ICAO_ATK = 1596995e6
ICAO_PAX = 4.7e9; ICAO_FREIGHT_T = 60.8e6; IATA_FREIGHT_T = 67.5e6
pax_tkm = ICAO_RTK - ICAO_FTK - ICAO_MTK                      # т-км, перевезённые как пассажиры с багажом
RES["m5b_pax_tkm"] = pax_tkm
RES["m5b_mass_per_pax_kg"] = pax_tkm / ICAO_RPK * 1000.0       # средняя масса пассажира с багажом, кг
RES["m5b_pax_Mt"] = ICAO_PAX * RES["m5b_mass_per_pax_kg"] / 1e9  # масса перевезённых пассажиров, Мт/год (по сегментам)
RES["m5b_freight_Mt_icao"] = ICAO_FREIGHT_T / 1e6; RES["m5b_freight_Mt_iata"] = IATA_FREIGHT_T / 1e6
RES["m5b_payload_Mt"] = RES["m5b_pax_Mt"] + RES["m5b_freight_Mt_icao"]
# средний самолёт: т-км делим на авиа-км -> тонн на борту в среднем в полёте
RES["m5b_payload_t_onboard"] = ICAO_RTK / D_KM                 # фактическая платная загрузка, т
RES["m5b_capacity_t"] = ICAO_ATK / D_KM                        # предельная платная загрузка, т
RES["m5b_spare_t"] = RES["m5b_capacity_t"] - RES["m5b_payload_t_onboard"]
RES["m5b_fuel_per_flight_t"] = FUEL_PER_KM * RES["in_mean_flight_km"] / 1000.0
RES["m5b_fuel_over_payload"] = RES["m5b_fuel_per_flight_t"] / RES["m5b_payload_t_onboard"]
RES["m5b_fuel_over_capacity"] = RES["m5b_fuel_per_flight_t"] / RES["m5b_capacity_t"]
_fe = json.load(open(os.path.join(OUT, "results_era5.json"), encoding="utf-8")).get("era5_form_250_global") if os.path.exists(os.path.join(OUT, "results_era5.json")) else None
for tau_t in TAU_TARGETS:
    kgkm = RES[f"m5_H1_kg_per_km_tau{tau_t}"]
    for flab, f in ([("fera", _fe)] if _fe else []) + [("f1", 1.0)]:
        t_fl = kgkm * RES["in_mean_flight_km"] * f / 1000.0        # т вещества на средний рейс (распыление на доле f пути)
        RES[f"m5b_t_per_flight_tau{tau_t}_{flab}"] = t_fl
        RES[f"m5b_over_payload_tau{tau_t}_{flab}"] = t_fl / RES["m5b_payload_t_onboard"]
        RES[f"m5b_over_capacity_tau{tau_t}_{flab}"] = t_fl / RES["m5b_capacity_t"]
        RES[f"m5b_over_spare_tau{tau_t}_{flab}"] = t_fl / RES["m5b_spare_t"]
        RES[f"m5b_over_fuel_flight_tau{tau_t}_{flab}"] = t_fl / RES["m5b_fuel_per_flight_t"]
        Mt = kgkm * D_KM * f / 1e9
        RES[f"m5b_Mt_over_pax_tau{tau_t}_{flab}"] = Mt / RES["m5b_pax_Mt"]
        RES[f"m5b_Mt_over_freight_tau{tau_t}_{flab}"] = Mt / RES["m5b_freight_Mt_icao"]
        RES[f"m5b_Mt_over_payload_tau{tau_t}_{flab}"] = Mt / RES["m5b_payload_Mt"]

# ================= Модель 7: следствия гипотезы H1 для воздуха у поверхности =================
# Вещество, распылённое на эшелоне, в итоге осаждается на поверхность (стационарный баланс: выпадение = выброс).
# Площади: Земля 5.10e14 м^2; пояс 30-60 с.ш. = 2 pi R^2 (sin60 - sin30). Равномерное выпадение по площади — ASSUMPTION (нижняя оценка локальных потоков).
# Сравнение: глобальная эмиссия пустынной пыли PM20 = 4600 (3400-9100) Тг/год (Kok et al. 2021a, ACP 21, 8127; значение из аннотации/выдержек, PDF не открывался).
# Приземная концентрация в стационаре: c = F / v_d, v_d = 0.001-0.01 м/с — типичная скорость сухого осаждения частиц ~1 мкм, ASSUMPTION (учебный диапазон, источник не открывался).
# Ориентир: рекомендация ВОЗ 2021 по PM2.5, среднегодовая 5 мкг/м^3 (документ ВОЗ не открывался).
R_EARTH = 6.371e6; A_GLOBE = 4*math.pi*R_EARTH**2; A_N3060 = 2*math.pi*R_EARTH**2*(math.sin(math.radians(60))-math.sin(math.radians(30)))
DUST_TG = 4600.0; DUST_TG_LO, DUST_TG_HI = 3400.0, 9100.0; WHO_PM25 = 5.0
VD_SET = [0.001, 0.01]
RES["m7_area_globe_m2"] = A_GLOBE; RES["m7_area_N30_60_m2"] = A_N3060
_era = os.path.join(OUT, "results_era5.json")
F_ERA = json.load(open(_era, encoding="utf-8")).get("era5_form_250_global") if os.path.exists(_era) else None
RES["m7_f_era5_250_global"] = F_ERA
RES["m7_mean_flight_km"] = RES["in_mean_flight_km"]; RES["m7_fuel_per_flight_t"] = FUEL_PER_KM * RES["in_mean_flight_km"] / 1000.0
for tau_t in TAU_TARGETS:
    mkm = RES[f"m5_H1_kg_per_km_tau{tau_t}"]
    RES[f"m7_H1_t_per_flight_tau{tau_t}"] = mkm * RES["in_mean_flight_km"] / 1000.0
    RES[f"m7_H1_substance_to_fuel_tau{tau_t}"] = mkm / FUEL_PER_KM
    for flab, f in ([("fera", F_ERA)] if F_ERA else []) + [("f1", 1.0)]:
        M_kg = mkm * D_KM * f
        RES[f"m7_H1_Mt_tau{tau_t}_{flab}"] = M_kg / 1e9
        RES[f"m7_H1_over_fuel_tau{tau_t}_{flab}"] = M_kg / FUEL_TOTAL_KG
        RES[f"m7_H1_over_dust_tau{tau_t}_{flab}"] = (M_kg / 1e9) / DUST_TG
        for alab, A in [("globe", A_GLOBE), ("N3060", A_N3060)]:
            F_gm2yr = M_kg * 1000.0 / A
            RES[f"m7_H1_dep_g_m2_yr_tau{tau_t}_{flab}_{alab}"] = F_gm2yr
            F_kgm2s = M_kg / A / (365.25*86400.0)
            for vd in VD_SET:
                RES[f"m7_H1_conc_ugm3_tau{tau_t}_{flab}_{alab}_vd{vd:g}"] = F_kgm2s / vd * 1e9
RES["m7_dust_dep_g_m2_yr_globe"] = DUST_TG*1e12 / A_GLOBE   # средний поток пыли по планете, г/м^2/год
RES["m7_who_pm25_ugm3"] = WHO_PM25


# ================= Модель 7b: концентрация через время жизни аэрозоля в тропосфере =================
# Стационарный баланс: масса в слое = выброс * время жизни. Среднее по тропосферному слою толщиной H_TROP, однородно по площади.
# Время жизни субмикронных частиц в тропосфере: 3-14 суток (обзор по сухому и мокрому осаждению; ScienceDirect, «Atmospheric Aerosol»: 3-14 сут для
#   аккумуляционной моды; NOAA, обзор по сухому осаждению: «около недели»; 210Pb: 4 сут у поверхности до 25 сут у тропопаузы — значения из выдержек поиска, PDF не открывались).
# H_TROP = 10 км — ASSUMPTION (толщина слоя перемешивания). Однородное перемешивание по слою — нижняя оценка пиков и верхняя оценка фона.
# Пределы регистрации массы PM2.5 (выдержки поиска, документы не открывались): расхождение BAM-1020 с эталоном около ±4 мкг/м3; фильтровой метод — следы до 2 мкг/м3.
RES_DAYS = [3.0, 7.0, 14.0]; H_TROP = 10000.0
DET_LIM_LOW, DET_LIM_BAM = 2.0, 4.0
for tau_t in TAU_TARGETS:
    for flab in (["fera"] if F_ERA else []) + ["f1"]:
        M_kg = RES[f"m7_H1_Mt_tau{tau_t}_{flab}"] * 1e9
        for alab, A in [("globe", A_GLOBE), ("N3060", A_N3060)]:
            for d in RES_DAYS:
                RES[f"m7b_conc_ugm3_tau{tau_t}_{flab}_{alab}_res{d:g}d"] = M_kg * (d / 365.25) / (A * H_TROP) * 1e9
RES["m7b_det_lim_low_ugm3"] = DET_LIM_LOW; RES["m7b_det_lim_bam_ugm3"] = DET_LIM_BAM; RES["m7b_H_trop_m"] = H_TROP
# отношение времени гравитационного падения (лёд, 1 мкм, 12 км; модель 4b) ко времени жизни 7 суток
RES["m7b_fall_over_residence_ice_r1_12km"] = RES["m4b_fall_yr_ice_r1_h12km"] * 365.25 / 7.0


# ================= Модель 2c: поправка Ми к основным величинам =================
# Все массы в моделях 5, 5b, 7, 7b посчитаны при Qext = 2 для льда. Для льда при медиане 1 мкм (логнормальное, σg = 1,5) по Ми
# масса для той же τ меньше в Q/2 раз; концентрации и тоннаж масштабируются так же (линейно по массе).
MIE_SCALE = 2.0 / RES["m2b_Q_ice_r1"]
RES["m2c_mie_scale_ice_r1"] = MIE_SCALE
for key in ["m5_H1_kg_per_km_tau0.05", "m5_H1_kg_per_km_tau0.2", "m7_H1_Mt_tau0.05_f1", "m7_H1_Mt_tau0.2_f1"]:
    RES["m2c_" + key] = RES[key] * MIE_SCALE

# ================= Вывод =================
with open(os.path.join(OUT, "results.json"), "w", encoding="utf-8") as fh:
    json.dump(RES, fh, ensure_ascii=False, indent=2)

# таблица значений с указанием происхождения
rows = [(k, v) for k, v in RES.items()]
with open(os.path.join(OUT, "results_table.csv"), "w", encoding="utf-8-sig") as fh:
    fh.write("quantity;value\n")
    for k, v in rows:
        fh.write(f"{k};{v}\n")

# ================= Рисунки =================
fig, ax = plt.subplots(figsize=(7, 4.5))
ax.plot(T_isa - 273.15, h_km, label="T ISA 1976")
ax.plot(Tlc - 273.15, h_km, label="порог T_LM (насыщение над водой; Schumann 1996, ур. 31)")
ax.fill_betweenx(h_km, T_isa - 273.15, Tlc - 273.15, where=ok, alpha=0.25, label="условие образования выполнено")
ax.set_xlabel("Температура, °C"); ax.set_ylabel("Высота, км"); ax.set_ylim(0, 20); ax.legend(fontsize=8)
fig.tight_layout(); fig.savefig(os.path.join(OUT, "fig1_sac_isa.png"), dpi=200); plt.close(fig)

fig, ax = plt.subplots(figsize=(7, 4.5))
Wg = np.logspace(np.log10(50), np.log10(2000), 50)
for r in radii:
    ax.loglog(Wg, k_ext(r) * m_l / Wg, label=f"r = {r} мкм")
ax.axhline(0.1, ls="--", c="gray", lw=0.8, label="τ = 0.1 (условный ориентир)")
ax.set_xlabel("Ширина следа W, м"); ax.set_ylabel("Оптическая глубина τ (только вода выхлопа)")
ax.legend(fontsize=8); fig.tight_layout(); fig.savefig(os.path.join(OUT, "fig2_optics_tau.png"), dpi=200); plt.close(fig)

fig, axs = plt.subplots(1, 2, figsize=(9, 4))
tt = np.linspace(0.05, 6, 120)
for K in Ks:
    axs[0].plot(tt, np.sqrt(2 * K * tt * 3600) / 1000, label=f"K = {int(K)} м²/с")
axs[0].set_xlabel("Время, ч"); axs[0].set_ylabel("σ (поперечная), км"); axs[0].legend(fontsize=8)
axs[1].plot(tt, U * tt * 3.6, c="k")   # м/с * ч -> км
axs[1].set_xlabel("Время, ч"); axs[1].set_ylabel("Смещение за счёт ветра, км (U = 40 м/с)")
fig.tight_layout(); fig.savefig(os.path.join(OUT, "fig3_dispersion.png"), dpi=200); plt.close(fig)

fig, ax = plt.subplots(figsize=(6.5, 4.2))
rr = np.logspace(-1, 1, 60)
ax.loglog(rr, [12000.0 / v_stokes(r)[0] / (365.25 * 86400) for r in rr])
ax.set_xlabel("Радиус частицы, мкм"); ax.set_ylabel("Время падения с 12 км, лет")
fig.tight_layout(); fig.savefig(os.path.join(OUT, "fig4_sedimentation.png"), dpi=200); plt.close(fig)


fig, ax = plt.subplots(figsize=(7.2, 5.6))
fs = np.array(F_SCEN)
for tau_t in TAU_TARGETS:
    ax.loglog(fs, [RES[f"m5_H1_Mt_tau{tau_t}_f{f}"] for f in F_SCEN], marker="o", label=f"распыление: вещество = видимый след, τ = {tau_t}")
ax.axhline(SW_S_MT_Y1, c="k", lw=1, label="Smith & Wagner 2018, год 1: 0.1 Мт S")
ax.axhline(SW_S_MT_Y15, c="gray", lw=1, label="экстраполяция до 15-го года: 1.5 Мт S")
ax.set_xlabel("Доля авиа-км с распылением f (параметр сценария)"); ax.set_ylabel("Масса вещества, Мт/год")
ax.axhline(FUEL_TOTAL_KG/1e9, c="tab:red", lw=1, ls=":", label="всё авиатопливо 2024 (IATA)")
ax.legend(fontsize=7, loc="upper center", bbox_to_anchor=(0.5, -0.14), ncol=2, frameon=False)
fig.tight_layout()
fig.savefig(os.path.join(OUT, "fig5_mass_budget.png"), dpi=200); plt.close(fig)


fig, axs = plt.subplots(1, 2, figsize=(10, 4.3))
tt = np.linspace(60.0, 6 * 3600.0, 300)
for s_ in S_SET:
    axs[0].plot(tt / 3600, [w_vis(sigma_x(t, s_, 20.0, 0.1)) / 1000 for t in tt], label=f"s = {s_:g} 1/с")
    axs[1].semilogy(tt / 3600, [SIG0 / sigma_x(t, s_, 20.0, 0.1) for t in tt], label=f"s = {s_:g} 1/с")
tobs = np.linspace(60.0, 3600.0, 20)
axs[0].plot(tobs / 3600, (W0_VIS + 2.3 * (tobs - 60.0)) / 1000, "k--", lw=1.5, label="наблюдения: 2.3 м/с, возраст 60–3600 с")
axs[0].set_xlabel("Возраст следа, ч"); axs[0].set_ylabel("Видимая ширина W, км"); axs[0].legend(fontsize=7)
axs[1].axhline(1.0 / DILUTION, c="gray", ls="--", lw=1, label=f"порог: падение в {DILUTION:g} раза")
axs[1].set_xlabel("Возраст следа, ч"); axs[1].set_ylabel("Пиковая колонка вещества / начальная")
axs[1].legend(fontsize=7, loc="upper center", bbox_to_anchor=(0.5, -0.16), ncol=3, frameon=False)
fig.suptitle("Расползание следа при разном сдвиге ветра s", fontsize=10)
fig.tight_layout(rect=(0, 0.04, 1, 1)); fig.savefig(os.path.join(OUT, "fig6_shear_spreading.png"), dpi=200); plt.close(fig)

fig, axs = plt.subplots(1, 2, figsize=(10, 4.3), sharey=True)
rr = np.logspace(-1, 1, 25)
labels_sub = {"ice": "лёд (для сравнения)", "sulfate": "сульфат (1.7 г/см³)", "sio2": "SiO₂ (2.2)", "al2o3": "Al₂O₃ (3.95)", "tio2": "TiO₂ рутил (4.23)"}
for ax_, h0 in zip(axs, [12000.0, 20000.0]):
    for name, rho_p in SUBST.items():
        ax_.loglog(rr, [fall_time_yr(r_, rho_p, h0) for r_ in rr], ls="--" if name == "ice" else "-", label=labels_sub[name])
    ax_.set_xlabel("Радиус частицы, мкм"); ax_.set_title(f"Высота выпуска {int(h0/1000)} км", fontsize=9)
axs[0].set_ylabel("Время падения до земли, лет (только оседание)"); axs[0].legend(fontsize=7)
fig.tight_layout(); fig.savefig(os.path.join(OUT, "fig7_substance_sedimentation.png"), dpi=200); plt.close(fig)


fig, axs = plt.subplots(1, 2, figsize=(10, 4.4))
for s_ in S3C:
    ts_, Ws_, Ds_, _, _ = cocip_like(s_, 0.011, 1.0)
    axs[0].plot(ts_/3600, Ws_/1000, label=f"s = {s_:g} 1/с"); axs[1].plot(ts_/3600, Ds_, label=f"s = {s_:g} 1/с")
tob = np.linspace(60.0, 3600.0, 20)
axs[0].plot(tob/3600, (W0_VIS + 2.3*(tob-60.0))/1000, "k--", lw=1.5, label="лидар: 2.3 м/с (60–3600 с)")
axs[1].plot(tob/3600, D0 + 0.3*(tob-60.0), "k--", lw=1.5, label="лидар: 0.3 м/с (60–3600 с)")
axs[0].set_xlabel("Возраст следа, ч"); axs[0].set_ylabel("Ширина W, км"); axs[0].set_xlim(0, 3); axs[0].set_ylim(0, 25)
axs[1].set_xlabel("Возраст следа, ч"); axs[1].set_ylabel("Глубина D, м"); axs[1].set_xlim(0, 3)
axs[0].legend(fontsize=7, loc="upper center", bbox_to_anchor=(0.5, -0.17), ncol=3, frameon=False); axs[1].legend(fontsize=7, loc="upper center", bbox_to_anchor=(0.5, -0.17), ncol=3, frameon=False)
fig.suptitle("Расползание следа: расчёт по модели CoCiP и лидарные измерения", fontsize=10)
axs[0].set_ylim(0, 25); axs[1].set_ylim(100, 1250)
fig.tight_layout(rect=(0, 0.05, 1, 1)); fig.savefig(os.path.join(OUT, "fig8_cocip_like_spreading.png"), dpi=200); plt.close(fig)



from matplotlib.patches import Patch
def conc_figure(kind, fname, title, xlabel, range_label, with_monitor):
    fig, ax = plt.subplots(figsize=(8.5, 5.6))
    labs, lo, hi, cols = [], [], [], []
    shares = ([("fera", f"{100*F_ERA:.0f} % авиа-км")] if F_ERA else []) + [("f1", "100 % авиа-км")]
    for tau_t, tname, col in [("0.05", "Тонкий след (τ = 0,05)", "tab:blue"), ("0.2", "Плотный след (τ = 0,2)", "tab:orange")]:
        for flab, ftxt in shares:
            for alab, atxt in [("globe", "весь мир"), ("N3060", "пояс 30–60° с. ш.")]:
                labs.append(f"{tname}\n{ftxt} · {atxt}"); cols.append(col)
                if kind == "dry":
                    lo.append(RES[f"m7_H1_conc_ugm3_tau{tau_t}_{flab}_{alab}_vd0.01"]); hi.append(RES[f"m7_H1_conc_ugm3_tau{tau_t}_{flab}_{alab}_vd0.001"])
                else:
                    v = [RES[f"m7b_conc_ugm3_tau{tau_t}_{flab}_{alab}_res{d:g}d"] for d in RES_DAYS]; lo.append(min(v)); hi.append(max(v))
    y = np.arange(len(labs))
    ax.barh(y, np.array(hi) - np.array(lo), left=lo, color=cols, alpha=0.65, height=0.62)
    ax.set_xscale("log"); ax.set_yticks(y); ax.set_yticklabels(labs, fontsize=7.5); ax.invert_yaxis()
    h1 = ax.axvline(WHO_PM25, c="k", ls="--", lw=1)
    handles = [Patch(color="tab:blue", alpha=0.65), Patch(color="tab:orange", alpha=0.65), h1]
    names = ["тонкий след: " + range_label, "плотный след: " + range_label, "норма ВОЗ для PM2.5 (среднегодовая): 5 мкг/м³"]
    if with_monitor:
        sp = ax.axvspan(DET_LIM_LOW, DET_LIM_BAM, color="tab:red", alpha=0.15); handles.append(sp)
        names.append("погрешность массовых мониторов PM2.5: 2–4 мкг/м³")
    ax.set_xlabel(xlabel, fontsize=8.5); ax.set_title(title, fontsize=9.5)
    ax.legend(handles, names, fontsize=7.5, loc="upper center", bbox_to_anchor=(0.5, -0.14), ncol=1, frameon=False)
    fig.tight_layout(); fig.savefig(os.path.join(OUT, fname), dpi=200); plt.close(fig)

conc_figure("dry", "fig10_ground_level.png",
            "Верхняя оценка: частицы удаляются только осаждением на землю",
            "Прирост концентрации частиц у земли, мкг/м³", "скорость осаждения 0,001–0,01 м/с", False)
conc_figure("res", "fig11_residence_time_conc.png",
            "Прирост концентрации частиц в воздухе (среднее по слою 10 км)",
            "Прирост концентрации частиц, мкг/м³", "время жизни частиц 3–14 суток", True)


fig, axs = plt.subplots(1, 2, figsize=(13, 5.4))
_fe12 = RES.get("m7_f_era5_250_global") or 1.0
labs = ["Топливо\nна рейс", "Платная\nзагрузка\nна борту", "Предельная\nплатная\nзагрузка", "Вещество\nτ = 0,05\nf = %d %%" % round(100*_fe12), "Вещество\nτ = 0,2\nf = %d %%" % round(100*_fe12), "Вещество\nτ = 0,2\nf = 100 %"]
vals = [RES["m5b_fuel_per_flight_t"], RES["m5b_payload_t_onboard"], RES["m5b_capacity_t"],
        RES["m5b_t_per_flight_tau0.05_fera"], RES["m5b_t_per_flight_tau0.2_fera"], RES["m5b_t_per_flight_tau0.2_f1"]]
cols = ["0.55", "tab:green", "tab:green", "tab:red", "tab:red", "tab:red"]
b = axs[0].bar(range(len(vals)), vals, color=cols, alpha=0.8)
axs[0].bar(2, vals[2], color="none", edgecolor="tab:green", hatch="//")
for i, v in enumerate(vals): axs[0].text(i, v * 1.02, ("%.1f" % v).replace(".", ","), ha="center", fontsize=8)
axs[0].set_xticks(range(len(vals))); axs[0].set_xticklabels(labs, fontsize=8); axs[0].set_ylabel("Масса на средний рейс 1570 км, т")
axs[0].set_title("Один рейс: что самолёт везёт и что пришлось бы распылить", fontsize=9.5)
labs2 = ["Груз\n(ICAO)", "Пассажиры\nс багажом\n(ICAO)", "Авиа-\nтопливо\n(IATA)", "Вещество\nτ = 0,05\nf = %d %%" % round(100*_fe12), "Вещество\nτ = 0,2\nf = %d %%" % round(100*_fe12), "Вещество\nτ = 0,2\nf = 100 %"]
vals2 = [RES["m5b_freight_Mt_icao"], RES["m5b_pax_Mt"], RES["in_fuel_total_Mt"], RES["m7_H1_Mt_tau0.05_fera"], RES["m7_H1_Mt_tau0.2_fera"], RES["m7_H1_Mt_tau0.2_f1"]]
axs[1].bar(range(len(vals2)), vals2, color=["tab:green", "tab:green", "0.55", "tab:red", "tab:red", "tab:red"], alpha=0.8)
axs[1].set_yscale("log")
for i, v in enumerate(vals2): axs[1].text(i, v * 1.1, ("%.0f" % v), ha="center", fontsize=8)
axs[1].set_xticks(range(len(vals2))); axs[1].set_xticklabels(labs2, fontsize=8); axs[1].set_ylabel("Масса, млн т в год")
axs[1].set_title("Год: перевезённая масса и масса вещества", fontsize=9.5)
fig.tight_layout(); fig.savefig(os.path.join(OUT, "fig12_payload_comparison.png"), dpi=200); plt.close(fig)

print("Модель 1: T_LC(250 гПа) = %.1f K (%.1f C), G = %.2f Pa/K" % (RES["m1_Tlc_at_250hPa_K"], RES["m1_Tlc_at_250hPa_C"], RES["m1_G_at_250hPa_PaK"]))
print("Модель 1: ISA, условие выполнено на %s..%s км, сегментов: %d" % (RES["m1_ok_min_km"], RES["m1_ok_max_km"], RES["m1_n_segments"]))
print("Модель 2: m_l = %.1f кг/км воды; tau(r=1, W=300) = %.3f" % (water_per_km, RES["m2_tau_r1.0um_W300m"]))
print("Модель 4: v(1 мкм) = %.3f мм/с, падение с 12 км = %.2f лет" % (RES["m4_v_r1.0um_mm_s"], RES["m4_fall_12km_yr_r1.0um"]))
print("Входные: D = %.4g км/год, топливо %.1f Мт/год, %.2f кг/км, средний рейс %.0f км" % (D_KM, RES["in_fuel_total_Mt"], FUEL_PER_KM, RES["in_mean_flight_km"]))
print("Модель 5 (H1): m(tau=0.2) = %.1f кг/км" % RES["m5_H1_kg_per_km_tau0.2"])
print("Готово: results_v2/results.json, results_table.csv, fig1-fig12 PNG")
