# DWG / DXF Specification & Audit Exporter

Инструмент на Python для автоматического аудита чертежей **AutoCAD** (`.dxf` офлайн и `.dwg` через Windows COM), подсчёта спецификаций (**BOM** по блокам с атрибутами), расчёта суммарных длин и площадей по слоям и выгрузки готовой оформленной книги **Excel (`.xlsx`)** + отчёта в Markdown / PDF.

## Возможности

- **Два режима работы:**
  - **Офлайн DXF-режим (`ezdxf`)** — кроссплатформенно (Windows / Linux / macOS) без установленного AutoCAD.
  - **Live AutoCAD COM-режим (`--com`, `pywin32`)** — подключается к запущенному AutoCAD на Windows, читает `.dwg` напрямую (включая `EffectiveName` динамических блоков и атрибуты) и умеет пакетно экспортировать листы в `.pdf` (`--pdf-dir`).
- **Точные геометрические расчёты:**
  - Длины `LINE`, `LWPOLYLINE` (включая дуговые сегменты с `bulge`), `POLYLINE`, `ARC`, `CIRCLE`, `ELLIPSE` и `SPLINE`.
  - Площади замкнутых контуров и окружностей.
  - Подсчёт вхождений блоков (`INSERT`) с группировкой по слоям и извлечением атрибутов (`ATTRIB`).
- **Аудит качества чертежа:** предупреждения о `Unitless` (`$INSUNITS = 0`), неиспользуемых пустых слоях и примитивах, забытых на слое `0`.
- **Стилизованный отчёт Excel (`.xlsx`):** 4 листа (`Summary`, `Blocks BOM`, `Layers & Lengths`, `Audit Issues`) с заголовками, закреплением шапки, автошириной колонок и итоговыми формулами `=SUM(...)`.

## Структура проекта

```text
dwg-spec-exporter/
├── cli.py             # CLI и пакетный обход файлов/папок
├── dxf_analyzer.py    # Офлайн-анализатор DXF (ezdxf)
├── autocad_com.py     # Windows COM адаптер к AutoCAD (.dwg + PDF-экспорт)
├── excel_exporter.py  # Генерация .xlsx (openpyxl) и Markdown-отчёта
├── models.py          # Модели отчётов, слоёв, блоков и предупреждений
├── requirements.txt
└── tests/
    └── test_dwg_spec_exporter.py
```

## Быстрый старт

1. Установите зависимости:
   ```bash
   python -m venv .venv
   # Windows PowerShell:
   .\.venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   ```

2. Запустите анализ одного `.dxf` файла или целой папки чертежей:
   ```bash
   python cli.py ./drawings --recursive --out spec_report.xlsx --md spec_report.md
   ```

3. Режим прямого чтения `.dwg` и пакетного экспорта PDF через запущенный AutoCAD (Windows):
   ```bash
   python cli.py ./dwg_folder --com --out dwg_bom.xlsx --pdf-dir ./pdf_out
   ```

## Тесты

```bash
pytest
```
