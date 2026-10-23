# era5_sac_fraction.py (2026-10-18)
# Доля воздушного пространства на эшелонах крейсерского полёта, где выполнено условие образования следа (Шмидт-Аппельман), по ERA5.
# Источник данных: ERA5 (Hersbach et al. 2020) в копии WeatherBench2, 1.5 град, 6-часовой шаг, уровни 200/250/300 гПа, 1959-01-02..2021-12-31.
#   URL: weatherbench2.storage.googleapis.com/datasets/era5/1959-2022-6h-240x121_equiangular_with_poles_conservative.zarr
# Формулы взяты из исходного кода pycontrails 0.63.5 (models/sac.py, physics/thermo.py), реализующего Schumann (1996):
#   G = EI_H2O * c_pm * p / (eps * Q * (1 - eta));  T_LM = -46.46 + 273.15 + 9.43 ln(G-0.053) + 0.72 ln^2(G-0.053)   (уравнение 31)
#   RH_crit = clip((G (T - T_LM) + e_liq(T_LM)) / e_liq(T), 0, 1), inf при T > T_LM;   образование: T <= T_LM и RH_w >= RH_crit
#   e_liq — Murphy & Koop 2005; e_ice — Sonntag 1994 (как в pycontrails);  RH_w = q p / (eps e_liq),  RHi = q p / (eps e_ice)
# Устойчивость: образование и RHi >= 1 (ERA5 без поправки на влажность; известна сухая смещённость ERA5 в верхней тропосфере).
# Что НЕ вычисляется: трафик. Доли здесь — по площади (вес cos(широта)) и по выбранным поясам, а не по налёту.
import os, json, math, sys, time
import numpy as np
import xarray as xr, fsspec
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "results_v2"); os.makedirs(OUT, exist_ok=True)
URL = "https://weatherbench2.storage.googleapis.com/datasets/era5/1959-2022-6h-240x121_equiangular_with_poles_conservative.zarr"
YEAR = 2019
START_DAYS = [1, 15]            # ASSUMPTION: выборка дней, 2 суток подряд (8 сроков) начиная с этих дней каждого месяца
LEVELS = [200, 250, 300]        # гПа
EPS, CP, Q_FUEL, EI_H2O = 0.622, 1004.0, 43.2e6, 1.25
ETA_SET = [0.30, 0.35, 0.40]    # ASSUMPTION: КПД двигателя, диапазон для чувствительности
ETA0 = 0.35
RES = {}

def e_liq(T):  # Murphy & Koop 2005, Па
    return np.exp(54.842763 - 6763.22/T - 4.21*np.log(T) + 0.000367*T + np.tanh(0.0415*(T-218.8))*(53.878 - 1331.22/T - 9.44523*np.log(T) + 0.014025*T))
def e_ice(T):  # Sonntag 1994, Па (как в pycontrails)
    return 100.0*np.exp(-6024.5282/T + 24.7219 + 0.010613868*T - 1.3198825e-5*T**2 - 0.49382577*np.log(T))
def sac_masks(T, q, p_pa, eta):
    G = EI_H2O*CP*p_pa/(EPS*Q_FUEL*(1.0-eta))
    L = np.log(G - 0.053)
    T_LM = -46.46 + 273.15 + 9.43*L + 0.72*L*L
    rh_w = q*p_pa/(EPS*e_liq(T)); rhi = q*p_pa/(EPS*e_ice(T))
    rh_crit = np.clip((G*(T - T_LM) + e_liq(T_LM))/e_liq(T), 0.0, 1.0)
    form = (T <= T_LM) & (rh_w >= rh_crit)
    return form, rhi, T_LM, rh_w
def isa_alt_km(p_pa):
    g0, R = 9.80665, 287.05
    p11 = 101325.0*(216.65/288.15)**(g0/(R*0.0065))
    if p_pa >= p11: return (288.15/0.0065)*(1-(p_pa/101325.0)**(R*0.0065/g0))/1000.0
    return (11000.0 + R*216.65/g0*math.log(p11/p_pa))/1000.0

fs = fsspec.filesystem("http", client_kwargs={"trust_env": True})
ds = xr.open_zarr(fs.get_mapper(URL), consolidated=True)
lat = ds.latitude.values; lon = ds.longitude.values
RES["era5_lat_step_deg"] = float(lat[1]-lat[0]); RES["era5_year"] = YEAR; RES["era5_levels_hPa"] = LEVELS
w_lat = np.cos(np.deg2rad(lat))                       # вес по площади
BANDS = {"global": (-90, 90), "N30_60": (30, 60), "S30_60": (-60, -30), "T20": (-20, 20), "N60_90": (60, 90)}
def band_mean(field_lat_lon, lo, hi):                 # field [lat, lon] -> средневзвешенное по площади в поясе
    m = (lat >= lo) & (lat <= hi); w = w_lat[m][:, None]
    return float((field_lat_lon[m]*w).sum()/(w.sum()*field_lat_lon.shape[1]))

acc = {lev: {k: np.zeros((lat.size, lon.size)) for k in ["form", "pers"]} for lev in LEVELS}
acc_eta = {(lev, e): np.zeros((lat.size, lon.size)) for lev in LEVELS for e in ETA_SET}
monthly = {lev: {b: [] for b in BANDS} for lev in LEVELS}
diag = {lev: {"T": np.zeros((lat.size, lon.size)), "rhi": np.zeros((lat.size, lon.size)), "TLM": np.zeros((lat.size, lon.size))} for lev in LEVELS}
nt = 0; t0 = time.time()
for month in range(1, 13):
    mon_form = {lev: np.zeros((lat.size, lon.size)) for lev in LEVELS}; mon_pers = {lev: np.zeros((lat.size, lon.size)) for lev in LEVELS}; nm = 0
    for d in START_DAYS:
        blk = ds[["temperature", "specific_humidity"]].sel(level=LEVELS).sel(time=slice(f"{YEAR}-{month:02d}-{d:02d}", f"{YEAR}-{month:02d}-{d+1:02d} 18:00")).load()
        for it in range(blk.time.size):
            for lev in LEVELS:
                T = blk.temperature.sel(level=lev).isel(time=it).transpose("latitude", "longitude").values.astype(np.float64)
                q = blk.specific_humidity.sel(level=lev).isel(time=it).transpose("latitude", "longitude").values.astype(np.float64)
                p_pa = lev*100.0
                form, rhi, T_LM, rh_w = sac_masks(T, q, p_pa, ETA0)
                pers = form & (rhi >= 1.0)
                acc[lev]["form"] += form; acc[lev]["pers"] += pers
                mon_form[lev] += form; mon_pers[lev] += pers
                diag[lev]["T"] += T; diag[lev]["rhi"] += rhi; diag[lev]["TLM"] += T_LM
                for e in ETA_SET: acc_eta[(lev, e)] += sac_masks(T, q, p_pa, e)[0]
            nm += 1; nt += 1
    for lev in LEVELS:
        for b, (lo, hi) in BANDS.items(): monthly[lev][b].append(band_mean(mon_form[lev]/nm, lo, hi))
    print(f"месяц {month}: сроков {nm}, всего {nt}, {time.time()-t0:.0f} с", flush=True)
RES["era5_n_times"] = nt
for lev in LEVELS:
    RES[f"era5_alt_km_{lev}hPa"] = isa_alt_km(lev*100.0); RES[f"era5_FL_{lev}hPa"] = isa_alt_km(lev*100.0)*1000.0/0.3048/100.0
    form = acc[lev]["form"]/nt; pers = acc[lev]["pers"]/nt
    for b, (lo, hi) in BANDS.items():
        RES[f"era5_form_{lev}_{b}"] = band_mean(form, lo, hi); RES[f"era5_pers_{lev}_{b}"] = band_mean(pers, lo, hi)
        RES[f"era5_form_{lev}_{b}_month_min"] = float(min(monthly[lev][b])); RES[f"era5_form_{lev}_{b}_month_max"] = float(max(monthly[lev][b]))
        RES[f"era5_meanT_K_{lev}_{b}"] = band_mean(diag[lev]["T"]/nt, lo, hi); RES[f"era5_meanTLM_K_{lev}_{b}"] = band_mean(diag[lev]["TLM"]/nt, lo, hi)
        RES[f"era5_meanRHi_{lev}_{b}"] = band_mean(diag[lev]["rhi"]/nt, lo, hi)
    for e in ETA_SET:
        for b in ["global", "N30_60"]:
            lo, hi = BANDS[b]; RES[f"era5_form_{lev}_{b}_eta{e:g}"] = band_mean(acc_eta[(lev, e)]/nt, lo, hi)

fig, axs = plt.subplots(1, 2, figsize=(10, 4.4), sharey=True)
for lev in LEVELS:
    lab = f"{lev} гПа (≈FL{RES[f'era5_FL_{lev}hPa']:.0f})"
    axs[0].plot(lat, (acc[lev]["form"]/nt).mean(axis=1), label=lab); axs[1].plot(lat, (acc[lev]["pers"]/nt).mean(axis=1), label=lab)
axs[0].set_title("Условие образования (T ≤ T_LM и RH_w ≥ RH_crit)", fontsize=9); axs[1].set_title("Образование и RHi ≥ 1 (ERA5 без поправки)", fontsize=9)
for a in axs: a.set_xlabel("Широта, °"); a.set_xlim(-90, 90); a.set_ylim(0, 1)
axs[0].set_ylabel("Доля сроков и долгот, 2019 (192 срока)"); axs[0].legend(fontsize=7, loc="upper center", bbox_to_anchor=(0.5, -0.17), ncol=3, frameon=False)
fig.tight_layout(rect=(0, 0.05, 1, 1)); fig.savefig(os.path.join(OUT, "fig9_era5_sac_fraction.png"), dpi=200); plt.close(fig)
json.dump(RES, open(os.path.join(OUT, "results_era5.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("Готово: results_v2/results_era5.json, fig9_era5_sac_fraction.png")
