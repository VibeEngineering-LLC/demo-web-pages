# atomfast-retry-delay-sweep

Sanity-прогон BLE retry_delay (1400–1800 мс, шаг 100, 4×30 с/точка) на
AtomFast-дозиметре. Цель серии — валидация инфраструктуры адаптивного
sweep'а перед production-исследованием.

**Отчёт**: https://vibeengineering-llc.github.io/demo-web-pages/atomfast-retry-delay-sweep/

## Что внутри

- `index.html` — статическая страница с таблицей и двумя графиками
  (rec/min и connect-latency vs retry_delay). Chart.js через CDN.

## Метод

- Test-сборка AtomFast Android-app (`.atftest` flavor) с broadcast-receiver'ом
  `SET_RETRY_DELAY` — устанавливает `AtomDeviceNRF.retry_delay` без перезапуска.
- На PC: `adb shell` наблюдает рост `arch_*` файлов в app-sandbox'е
  (`/data/data/<pkg>/files/`). BLE-пакет дозиметра = 28 байт каждые ~2.4 с,
  номинал ≈ 25 rec/min.
- Каждой итерации: launch → wait first BLE record → monitor 30 с → planned
  disconnect → check clean.

## Stability rule

retry_delay помечается **UNSTABLE** если хотя бы одно из:

1. в ≥2 итерациях `sudden_disconnect_count ≥ 1`
2. `median(records_per_minute) < 17.0`

(17 rec/min ≈ 70 % номинала.)

## Дисклеймер

N=4/точка — слишком мало для статистических выводов. Это **sanity** на
инфраструктуру, не production-исследование. Для рабочего прогона —
N=10/точка с adaptive early-stop и bootstrap-CI анализом.
