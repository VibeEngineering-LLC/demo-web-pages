# Проверка приземной добавки по данным фоновой сети IMPROVE (США), годовые средние из EPA AirData.
# Источник: https://aqs.epa.gov/aqsweb/airdata/annual_conc_by_monitor_YYYY.zip (открытые данные EPA; IMPROVE-методы отбираются по Method Name).
# Величины: Al, Si, Ti в PM2.5 (88104, 88165, 88161) и масса PM2.5 по IMPROVE (88502). Полнота >= 75 %. Пояс 30-60° с. ш.
# Минеральные оксиды = 1,889·Al + 2,139·Si + 1,668·Ti (стехиометрия Al2O3, SiO2, TiO2) — масса гипотетического минерального вещества.
# Сравнение: предсказанная гипотезой распыления средняя добавка в слое 10 км (results.json, m7b_conc_*), пояс 30-60° с. ш.
import os, io, json, zipfile, math
import numpy as np, pandas as pd, requests
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
HERE = os.path.dirname(os.path.abspath(__file__)); OUT = os.path.join(HERE, "..", "results_v2"); CACHE = os.path.join(HERE, "..", "aqs_cache")
os.makedirs(CACHE, exist_ok=True)
YEARS = list(range(2000, 2024)); PC = {88104: "Al", 88165: "Si", 88161: "Ti", 88502: "pm25"}
OX = {"Al": 101.961 / (2 * 26.982), "Si": 60.084 / 28.086, "Ti": 79.866 / 47.867}
rows = []
for y in YEARS:
    fn = os.path.join(CACHE, f"annual_conc_by_monitor_{y}.zip")
    if not os.path.exists(fn):
        r = requests.get(f"https://aqs.epa.gov/aqsweb/airdata/annual_conc_by_monitor_{y}.zip", timeout=300); r.raise_for_status(); open(fn, "wb").write(r.content)
    with zipfile.ZipFile(fn) as z: d = pd.read_csv(z.open(z.namelist()[0]), low_memory=False)
    d = d[d["Parameter Code"].isin(PC) & d["Method Name"].astype(str).str.contains("IMPROVE", case=False) & d["Event Type"].isin(["No Events", "Events Included"])]
    d = d.sort_values("Event Type").drop_duplicates(["State Code", "County Code", "Site Num", "Parameter Code", "POC"])
    d = d[d["Observation Percent"] >= 75]
    d["site"] = d["State Code"].astype(str) + "-" + d["County Code"].astype(str) + "-" + d["Site Num"].astype(str)
    d["var"] = d["Parameter Code"].map(PC); d["Year"] = y
    rows.append(d[["site", "Year", "Latitude", "Longitude", "Local Site Name", "var", "Arithmetic Mean"]])
w = pd.concat(rows).pivot_table(index=["site", "Year", "Latitude", "Longitude", "Local Site Name"], columns="var", values="Arithmetic Mean", aggfunc="mean").reset_index()
w = w.dropna(subset=["Al", "Si", "Ti"]); w["oxides"] = sum(OX[k] * w[k] for k in OX)
band = w[(w["Latitude"] >= 30) & (w["Latitude"] <= 60)].copy()
band.to_csv(os.path.join(OUT, "improve_band_annual.csv"), index=False, encoding="utf-8-sig")
R = json.load(open(os.path.join(OUT, "results.json"), encoding="utf-8"))
C = lambda tau, f, d: R[f"m7b_conc_ugm3_tau{tau}_{f}_N3060_res{d}d"]
P = {"thin_lo": C("0.05", "fera", "3"), "thin_hi": C("0.05", "fera", "14"), "thick_lo": C("0.2", "fera", "3"), "thick_hi": C("0.2", "fera", "14")}
RES = {"imp_oxide_factors": OX, "imp_years": [YEARS[0], YEARS[-1]], "imp_pred_N3060_fera": P}
st = band.groupby("Year").agg(n=("site", "nunique"), ox_med=("oxides", "median"), ox_p90=("oxides", lambda s: s.quantile(0.9)), ox_max=("oxides", "max"), pm_med=("pm25", "median"), pm_p90=("pm25", lambda s: s.quantile(0.9)))
RES["imp_n_sites_range"] = [int(st["n"].min()), int(st["n"].max())]
RES["imp_ox_median_range"] = [float(st["ox_med"].min()), float(st["ox_med"].max())]
RES["imp_ox_p90_range"] = [float(st["ox_p90"].min()), float(st["ox_p90"].max())]
RES["imp_ox_max_allyears"] = float(st["ox_max"].max())
RES["imp_pm_median_range"] = [float(st["pm_med"].min()), float(st["pm_med"].max())]
RES["imp_ox_median_slope_per_yr"] = float(np.polyfit(st.index.values, st["ox_med"].values, 1)[0])
allv = band["oxides"]; RES["imp_siteyears"] = int(len(allv))
RES["imp_frac_siteyears_ox_below_thin_lo"] = float((allv < P["thin_lo"]).mean())
RES["imp_frac_siteyears_pm_below_thick_lo"] = float((band["pm25"].dropna() < P["thick_lo"]).mean())
b19 = band[band["Year"] == 2019]
RES["imp_2019_n"] = int(len(b19)); RES["imp_2019_ox_median"] = float(b19["oxides"].median())
RES["imp_2019_frac_ox_below_thin_lo"] = float((b19["oxides"] < P["thin_lo"]).mean())
RES["imp_2019_ratio_thin_lo_over_ox_median"] = P["thin_lo"] / float(b19["oxides"].median())
RES["imp_2019_frac_pm_below_thick_lo"] = float((b19["pm25"].dropna() < P["thick_lo"]).mean())
top = b19.sort_values("oxides", ascending=False).head(3)
RES["imp_2019_top_sites"] = [{"name": str(r["Local Site Name"]), "lat": float(r["Latitude"]), "oxides": float(r["oxides"])} for _, r in top.iterrows()]
json.dump(RES, open(os.path.join(OUT, "results_improve.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)

# --- уточнения по замечаниям рецензентов ---
Pg = {"thin_lo": R["m7b_conc_ugm3_tau0.05_fera_globe_res3d"], "thick_lo": R["m7b_conc_ugm3_tau0.2_fera_globe_res3d"]}
RES["imp_pred_globe_fera_3d"] = Pg
MS = R.get("m2c_mie_scale_ice_r1", 1.0); RES["imp_mie_scale"] = MS
RES["imp_pred_mie"] = {"band_thin_lo": P["thin_lo"] * MS, "band_thick_lo": P["thick_lo"] * MS, "globe_thin_lo": Pg["thin_lo"] * MS, "globe_thick_lo": Pg["thick_lo"] * MS}
st_mean = band.groupby("Year")["oxides"].mean(); RES["imp_ox_mean_range"] = [float(st_mean.min()), float(st_mean.max())]
RES["imp_ratio_band_thin_lo_over_median"] = [P["thin_lo"] / float(st["ox_med"].max()), P["thin_lo"] / float(st["ox_med"].min())]
by_site = band.groupby("site").agg(name=("Local Site Name", "first"), lat=("Latitude", "first"), ox_med=("oxides", "median"), ox_max=("oxides", "max"), n=("Year", "count"))
RES["imp_n_sites_total"] = int(len(by_site))
for lab, thr in [("band_thin", P["thin_lo"]), ("globe_thick", Pg["thick_lo"]), ("band_thin_mie", P["thin_lo"] * MS), ("globe_thick_mie", Pg["thick_lo"] * MS)]:
    RES[f"imp_sites_median_above_{lab}"] = int((by_site["ox_med"] >= thr).sum())
    RES[f"imp_sites_ever_above_{lab}"] = int((by_site["ox_max"] >= thr).sum())
    RES[f"imp_frac_siteyears_below_{lab}"] = float((band["oxides"] < thr).mean())
    RES[f"imp_sites_ever_above_{lab}_names"] = by_site[by_site["ox_max"] >= thr]["name"].astype(str).tolist()
# наибольшая доля авиа-км f, совместимая с измерениями, при выпадении по всей Земле (тонкий и плотный след, 3 сут; Ми-поправка)
F_ERA_ = R["m7_f_era5_250_global"]
for lab, obs in [("median_max", float(st["ox_med"].max())), ("p90_max", float(st["ox_p90"].max()))]:
    for tr, key in [("thin", "thin_lo"), ("thick", "thick_lo")]:
        RES[f"imp_fmax_globe_{tr}_{lab}"] = obs / (Pg[key] * MS / F_ERA_)
        RES[f"imp_fmax_band_{tr}_{lab}"] = obs / ((P[key] if key in P else 0) * MS / F_ERA_) if key in P else None
# наклон медианы по фиксированной панели станций (все 24 года), с 95 % интервалом
cnt = band.groupby("site")["Year"].nunique(); panel = cnt[cnt == len(YEARS)].index
pm = band[band["site"].isin(panel)].groupby("Year")["oxides"].median()
RES["imp_panel_n"] = int(len(panel))
if len(pm) > 5:
    xx = pm.index.values.astype(float); yy = pm.values; A = np.vstack([xx, np.ones_like(xx)]).T
    coef, res_, *_ = np.linalg.lstsq(A, yy, rcond=None); dof = len(xx) - 2
    se = math.sqrt(float(((yy - A @ coef) ** 2).sum()) / dof / ((xx - xx.mean()) ** 2).sum())
    RES["imp_panel_slope"] = float(coef[0]); RES["imp_panel_slope_ci95"] = [float(coef[0] - 2.07 * se), float(coef[0] + 2.07 * se)]
json.dump(RES, open(os.path.join(OUT, "results_improve.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)

fig, axs = plt.subplots(1, 2, figsize=(12, 4.8))
ax = axs[0]
ax.axhspan(P["thin_lo"], P["thin_hi"], color="tab:blue", alpha=0.18, label="ожидаемая добавка, тонкий след (τ = 0,05)")
ax.axhspan(P["thick_lo"], P["thick_hi"], color="tab:orange", alpha=0.18, label="ожидаемая добавка, плотный след (τ = 0,2)")
ax.plot(st.index, st["ox_med"], "k-o", ms=3, label="измерено: медиана по станциям")
ax.plot(st.index, st["ox_p90"], "k--", lw=1, label="измерено: 90-й процентиль")
ax.set_yscale("log"); ax.set_ylim(0.01, 50); ax.set_xlabel("Год"); ax.set_ylabel("Минеральные оксиды Al, Si, Ti в PM2.5, мкг/м³")
ax.set_title("Ряд 2000–2023, фоновые станции IMPROVE, 30–60° с. ш.", fontsize=9.5)
ax.legend(fontsize=7.5, loc="upper center", bbox_to_anchor=(0.5, -0.15), ncol=2, frameon=False)
ax = axs[1]
rng = np.random.default_rng(1)
for i, (col, lab) in enumerate([("oxides", "минеральные оксиды"), ("pm25", "вся масса PM2.5")]):
    v = b19[col].dropna().values; ax.scatter(i + rng.uniform(-0.18, 0.18, v.size), v, s=9, c="k", alpha=0.6)
ax.axhspan(P["thin_lo"], P["thin_hi"], color="tab:blue", alpha=0.18); ax.axhspan(P["thick_lo"], P["thick_hi"], color="tab:orange", alpha=0.18)
ax.set_yscale("log"); ax.set_ylim(0.01, 50); ax.set_xticks([0, 1]); ax.set_xticklabels(["Минеральные оксиды", "Вся масса PM2.5"])
ax.set_ylabel("Годовое среднее на станции, мкг/м³"); ax.set_title("2019 год: каждая точка — станция", fontsize=9.5)
fig.tight_layout(); fig.savefig(os.path.join(OUT, "fig13_improve_check.png"), dpi=200); plt.close(fig)
print("ok")
