<div align="center">

# 🎮 G-Blend

**Инструменты для переноса сцен Garry's Mod → Blender**

[![Blender](https://img.shields.io/badge/Blender-4.1%2B-orange?logo=blender&logoColor=white)](https://www.blender.org/)
[![GMod](https://img.shields.io/badge/Garry's%20Mod-required-brightgreen)](https://store.steampowered.com/app/4000/Garrys_Mod/)
[![License](https://img.shields.io/badge/license-MIT-blue)](LICENSE)

*Импортируй сцены, пропы и оружие ARC9 из GMod прямо в Blender — с материалами, Workshop-контентом и полной иерархией.*

</div>

---

## 📦 Что внутри

Репозиторий содержит **два компонента**, которые работают в связке:

| Компонент | Что делает |
|-----------|-----------|
| 🟠 **GMod Scene Importer** *(аддон для Blender)* | Импортирует сцены GMod (JSON) в Blender: пропы, модели, материалы, Workshop-кэш |
| 🟢 **GMod Exporter Addon** *(аддон для GMod)* | Экспортирует сцены GMod в JSON прямо из игры. Поддерживает экспорт по зоне, буфер AdvDupe2, захват ARC9 |

> [!NOTE]
> **Live Link** (синхронизация GMod и Blender в реальном времени) присутствует в коде, но **не входит в этот релиз**. Будет выпущен отдельно в следующем обновлении.

---

## ✨ Возможности

### GMod Scene Importer (Blender)
- 📁 Импорт полных GMod-сцен из экспортированных JSON-файлов
- 🔫 Импорт **оружия ARC9** со всеми насадками и правильной иерархией костей
- 🏭 Автоматический **Workshop-кэш** — сканирует `.gma`-файлы и извлекает недостающие модели
- 🎨 Загрузка материалов из папки GMod (VMT → ноды Blender)
- 📸 Поддержка замены камер
- ⚖️ Настройка глобального масштаба и поворота
- 🧩 Поддержка bodygroup
- 🗂️ Поддержка Workshop-контента и отдельных GMA-путей

### GMod Exporter Addon (GMod)
- 📤 Экспорт любой зоны карты в JSON
- 📋 Экспорт через буфер AdvDupe2
- 🔫 Захват рантайма ARC9 (кости, насадки, материалы)
- 🗂️ Встроенный файловый браузер для управления экспортами
- 🧰 Рантайм-инспекторы: анимации, скелет, материалы, attachment-точки, entity

---

## 🗂️ Структура репозитория

```
G-Blend/
├── gmod_scene_importer/     ← Аддон для Blender (устанавливается как .zip)
│   ├── __init__.py
│   ├── operators.py         ← Логика импорта сцен и ARC9
│   ├── operators_cache.py   ← Система кэша Workshop GMA
│   ├── operators_livelink.py
│   ├── ui.py                ← Все панели: Scene, ARC9, Live Link
│   ├── gma_reader.py
│   ├── utils.py
│   └── SourceIO_adv/        ← Встроенная библиотека SourceIO (MDL/BSP/VTF)
│
└── gmod_exporter_addon/     ← Серверный аддон для GMod
    ├── addon.json
    └── lua/
        ├── autorun/         ← Автозагружаемые скрипты
        ├── arc9_runtime/    ← Модули захвата ARC9
        └── advdupe2/        ← Поддержка буфера AdvDupe2
```

---

## 🚀 Установка

### Шаг 1 — Устанавливаем аддон для GMod

1. Скопируй папку `gmod_exporter_addon` в директорию аддонов GMod:
   ```
   ...\steamapps\common\GarrysMod\garrysmod\addons\gmod_exporter_addon\
   ```
2. Запусти (или перезапусти) Garry's Mod
3. Аддон загружается автоматически — ничего дополнительного делать не нужно

### Шаг 2 — Устанавливаем аддон для Blender

1. Открой **Blender 4.1+**
2. Перейди в **Edit → Preferences → Add-ons → Install...**
3. Выбери папку `gmod_scene_importer` (предварительно упакуй её в `.zip`)
4. Включи **«GMod Scene Importer»** в списке аддонов
5. Панель появится во **3D Viewport → Боковая панель (N) → GMod Tools**

---

## 📖 Руководство по использованию

### Экспорт сцены из GMod

1. Загрузи любую карту в GMod
2. Открой **Spawnmenu → Utilities** или используй консоль
3. Используй инструмент **Exporter** — выбери зону или экспортируй через AdvDupe2
4. Сохрани экспортированный `.json`-файл в удобное место

### Импорт сцены в Blender

1. Открой Blender, перейди на вкладку **GMod Tools** в боковой панели
2. В разделе **GMod Scene Importer**:
   - **Scene JSON** — укажи путь к экспортированному `.json`
   - **GMod Folder** — укажи путь к папке `GarrysMod/garrysmod/`
   - *(Опционально)* **Workshop Content** — путь к папке аддонов для поддержки Workshop-моделей
3. Нажми **Import Scene**

### Импорт оружия ARC9

1. В GMod используй инструмент захвата ARC9 для экспорта JSON-файла оружия
2. В Blender перейди на вкладку **ARC9 Weapon Importer**
3. Укажи **GMod Folder** и путь к **Weapon JSON**
4. Выбери **Spawn Mode** (Origin / Bone-relative)
5. Нажми **Import ARC9 Weapon**

### Workshop-кэш (если модели не найдены)

Если после импорта часть моделей отсутствует:
1. Укажи путь **Workshop Content** (папка загрузок Workshop в Steam)
2. Укажи папку **Cache Storage** (куда будут распакованы GMA)
3. Нажми **Scan & Cache GMAs** — аддон автоматически извлечёт весь нужный контент
4. Повтори импорт

---

## ⚙️ Требования

| Программа | Версия |
|-----------|--------|
| Blender | 4.1 и новее |
| Garry's Mod | Любая актуальная версия |
| Python | Встроен в Blender (отдельно устанавливать не нужно) |

---

## 📋 Релизы

| Версия | Дата | Содержимое |
|--------|------|-----------|
| [v1.0](https://github.com/Sinon1337/G-blend/releases/tag/v1.0) | 11.07.2026 | GMod Scene Importer + ARC9 Weapon Importer + GMod Exporter Addon |

---

## 🙏 Благодарности

- **SourceIO** — встроенная библиотека для парсинга MDL/BSP/VTF ([SourceIO на GitHub](https://github.com/REDxEYE/SourceIO))

---

## 📄 Лицензия

Проект распространяется под лицензией **MIT** — подробности в файле [LICENSE](LICENSE).
