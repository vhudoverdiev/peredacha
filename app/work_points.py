from __future__ import annotations

from functools import lru_cache


WORK_POINT_LABELS = {
    "1": "Пункт 1",
    "2": "Пункт 2",
    "3": "Пункт 3",
    "4": "Пункт 4",
    "5": "Пункт 5",
    "6": "Пункт 6",
    "7": "Пункт 7",
    "8": "Срок устранения замечаний по АПП",
    "9": "АВР",
    "10": "Вентиляция",
    "11": "Стены. Потолки (штукатурка/шпаклёвка)",
    "12": "Возведение коробки здания",
    "13": "Работы по устройству подстилающего слоя",
    "14": "Работы по устройству гидроизоляции пола в с/у",
    "15": "Работы по возведению блочных перегородок",
    "17": "Работы по монтажу ПВХ блоков",
    "18": "Работы по монтажу откосов и подоконников",
    "19": "Ростелеком",
    "20": "Работы по монтажу холодного витражного остекления балконов",
    "21": "Работы по монтажу системы отопления",
    "22": "Работы по монтажу канализации, в/с",
    "23": "Работы по монтажу входных дверей",
    "24": "Электрика",
    "25": "Прочее",
    "26": "Отступное (ТМЦ)",
}


CONTRACTOR_POINT_LABELS = WORK_POINT_LABELS

# Stable internal keys keep existing links, imports and category mappings safe.
# Public numbering is contiguous after retirement of the former point 16.
RETIRED_POINT_KEY = "16"


def display_point_number(number):
    value = str(number or "").strip()
    if value == RETIRED_POINT_KEY:
        return ""
    return str(int(value) - 1) if value.isdigit() and 17 <= int(value) <= 26 else value


def is_retired_point_label(value):
    import re
    return bool(re.search(r"\bразнорабоч", str(value or "").casefold()))


@lru_cache(maxsize=1)
def retired_phrase_hashes():
    """Fingerprints also identify examples relabelled by an older deploy."""
    import json
    from pathlib import Path
    return frozenset(json.loads((Path(__file__).parent / 'data' / 'retired_remark_hashes.json').read_text()))
