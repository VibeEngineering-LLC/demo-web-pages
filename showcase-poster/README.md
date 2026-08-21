# Витрина demo-web-pages — вариант «плакат»

Комплект для установки в отдельную папку сайта. Оформление повторяет
`geant4-detector-models/docs/gamma-1s-th232`: тёплая бумага, чернота вместо
серых, линейки 3 px, тень 7×7 без размытия, единственный акцент — жёлтая
маркерная плашка. Светлая и тёмная темы через `prefers-color-scheme`
(принудительно — `<html data-theme="light|dark">`).

## Состав

```
showcase-poster/
├── index.html               витрина: шапка, поиск, теги со счётчиками, указатель из 26 строк
├── styles/showcase.css      все стили (переменные темы + компоненты + адаптив)
└── README.md
```

Зависимостей и сборки нет: два файла + встроенный скрипт фильтра
(поиск, теги, счётчик, сброс, состояние в query-строке `?tags=…&q=…`).

## Установка

1. Скопировать папку `showcase-poster/` в корень репозитория
   `demo-web-pages` (получится `demo-web-pages/showcase-poster/`).
2. `git commit` + `git push` в `main`.
3. Открыть https://vibeengineering-llc.github.io/demo-web-pages/showcase-poster/

Ссылки на демо записаны как `../<имя-демо>/` — папка рассчитана на один
уровень ниже корня сайта. Если ставить витрину **вместо** корневого
`index.html`, заменить `../` на `./` (одна замена по файлу) и проверить, что
каталог `styles/` не конфликтует с существующим `styles/index.css`.

## Как добавить строку

```html
<a class="row" href="../имя-демо/" target="_blank" rel="noopener" data-tags="radon dose">
  <span class="row-num">27</span>
  <span class="row-body">
    <span class="row-title">Заголовок</span>
    <span class="row-desc">Описание — обрезается по двум строкам (line-clamp).</span>
  </span>
  <span class="row-meta">Радон · Дозиметрия</span>
</a>
```

Если внутри описания нужна своя ссылка — строка делается на `<div class="row">`
с перекрывающим `<a class="row-link">` (примеры в файле есть), а внутренняя
ссылка получает класс `inline-link`. Счётчики у тегов в `.chips` статические —
при добавлении строки поправить числа.
