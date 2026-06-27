# demo-web-pages

Публичные демо-страницы **VibeEngineering-LLC**. Каждая демонстрация — в своей
подпапке; все страницы статические и обслуживаются через GitHub Pages.

**Витрина:** https://vibeengineering-llc.github.io/demo-web-pages/

## Демонстрации

| Демо | Описание | Страница |
|---|---|---|
| [atomfast-retry-delay-sweep](atomfast-retry-delay-sweep/) | Sanity-прогон BLE `retry_delay` (1400–1800 мс, 4×30 с/точка) на дозиметре AtomFast | https://vibeengineering-llc.github.io/demo-web-pages/atomfast-retry-delay-sweep/ |
| [atomfast-prod-sweep](atomfast-prod-sweep/) | Production-серия `retry_delay` 500–2500 мс × 10 итераций × 10–20 мин мониторинга (21/21 точка) | https://vibeengineering-llc.github.io/demo-web-pages/atomfast-prod-sweep/ |

## Структура

```
demo-web-pages/
├── index.html                       витрина со ссылками на все демо
├── atomfast-retry-delay-sweep/      sanity-прогон retry_delay
│   ├── index.html
│   └── README.md
└── atomfast-prod-sweep/             production-серия retry_delay
    └── index.html
```

## Как добавить новую демо-страницу

1. Создать подпапку `<имя-демо>/` с `index.html` (ссылки внутри — относительные).
2. Добавить карточку в корневой `index.html` и строку в таблицу выше.
3. `git commit` + `git push` в `main` — GitHub Pages обновится автоматически.

## Провенанс

Консолидировано из ранее раздельных публичных репозиториев
`VibeEngineering-LLC/atomfast-retry-delay-sweep` и
`VibeEngineering-LLC/atomfast-prod-sweep`. HTML-файлы перенесены побайтово;
у retry-delay обновлена устаревшая ссылка «Отчёт» на новое расположение.