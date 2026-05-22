#!/usr/bin/env python3
r"""
Raptor-UA Feed Cleaner

Скачивает оригинальный Google Shopping фид с raptor-ua.com, схлопывает
дубли (товары с идентичным <g:title>), оставляет варианты размеров через
<g:item_group_id>, и сохраняет очищенный фид в docs/feed.xml для публикации
через GitHub Pages.

Логика дедупликации:
1. Парсим SKU: ^(\d+)([A-Za-z]+)?(\d+)?$ → (model, size, variant)
   Пример: "010S19" → model="010", size="S", variant="19"
2. Группируем товары по ключу (title, size) — это значит "тот же товар того же размера"
3. Из каждой группы оставляем артикул с минимальным variant (обычно "1" = базовая комплектация)
4. Добавляем поля для Meta:
   - <g:item_group_id> = md5(title)[:10] — стабильный идентификатор группы вариаций
   - <g:size>          = S / M / L / XL — извлечён из артикула

Safety check: если после фильтрации товаров < 50, фид не публикуется,
сохраняется предыдущая версия (защита от битого оригинального фида).
"""

import hashlib
import os
import re
import sys
import urllib.request
from collections import defaultdict
from xml.etree import ElementTree as ET

SOURCE_FEED_URL = "https://raptor-ua.com/marketplace-integration/google-feed/f3e3fcd5cff5ddc213ffea49d5b3ba98?langId=3"
OUTPUT_PATH = os.environ.get("OUTPUT_PATH", "docs/feed.xml")
MIN_ITEMS_THRESHOLD = 50  # ниже = не публикуем (битый фид)

NS = "http://base.google.com/ns/1.0"
ET.register_namespace("g", NS)
NS_MAP = {"g": NS}

SKU_RE = re.compile(r"^(\d+)([A-Za-z]+)?(\d+)?$")


def parse_sku(sku: str):
    """Парсит '010S19' → ('010', 'S', '19'). Если не матчится — возвращает (sku, '', '')."""
    m = SKU_RE.match(sku.strip())
    if m:
        return m.group(1), (m.group(2) or "").upper(), (m.group(3) or "")
    return sku.strip(), "", ""


def variant_sort_key(variant: str) -> int:
    """Сортируем варианты численно (variant='2' раньше variant='10')."""
    if variant.isdigit():
        return int(variant)
    return 10**9  # нечисловые варианты в конец


def stable_group_id(title: str) -> str:
    """Стабильный 10-символьный hash от title — пригоден для item_group_id."""
    return hashlib.md5(title.encode("utf-8")).hexdigest()[:10]


def download_feed(url: str) -> bytes:
    """Скачивает фид с User-Agent под бота (Horoshop любит роботов)."""
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 (compatible; RaptorFeedCleaner/1.0)"},
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.read()


def add_or_replace(item: ET.Element, tag: str, value: str):
    """Добавляет <g:tag>value</g:tag> в item, или заменяет если уже есть."""
    qname = f"{{{NS}}}{tag}"
    existing = item.find(qname)
    if existing is not None:
        existing.text = value
    else:
        el = ET.SubElement(item, qname)
        el.text = value


def filter_feed(xml_bytes: bytes) -> tuple[ET.ElementTree, dict]:
    """Возвращает (отфильтрованное_дерево, статистика)."""
    root = ET.fromstring(xml_bytes)
    channel = root.find("channel")
    if channel is None:
        raise RuntimeError("Невалидный фид: нет <channel>")

    items = channel.findall("item")
    original_count = len(items)

    # 1. Группируем по (title, size)
    groups: dict[tuple[str, str], list[tuple[str, ET.Element]]] = defaultdict(list)
    for it in items:
        sku_el = it.find(f"{{{NS}}}id")
        title_el = it.find(f"{{{NS}}}title")
        if sku_el is None or title_el is None:
            continue
        sku = (sku_el.text or "").strip()
        title = (title_el.text or "").strip()
        _, size, variant = parse_sku(sku)
        groups[(title, size)].append((variant, it))

    # 2. Из каждой группы — минимальный variant
    kept_items: list[ET.Element] = []
    for (title, size), candidates in groups.items():
        candidates.sort(key=lambda c: variant_sort_key(c[0]))
        chosen_variant, chosen_item = candidates[0]
        # Добавляем item_group_id (стабильный hash от title)
        add_or_replace(chosen_item, "item_group_id", stable_group_id(title))
        # Добавляем size (только если он реально S/M/L/XL и т.п.)
        if size:
            add_or_replace(chosen_item, "size", size)
        kept_items.append(chosen_item)

    # 3. Удаляем все старые <item> и вставляем отфильтрованные
    for it in items:
        channel.remove(it)
    for it in kept_items:
        channel.append(it)

    stats = {
        "original": original_count,
        "filtered": len(kept_items),
        "groups": len(set(stable_group_id(title) for (title, _) in groups)),
        "ratio": f"{len(kept_items) / original_count * 100:.1f}%" if original_count else "0%",
    }
    return ET.ElementTree(root), stats


def main():
    print(f"→ Скачиваю фид: {SOURCE_FEED_URL}")
    xml_bytes = download_feed(SOURCE_FEED_URL)
    print(f"  получено: {len(xml_bytes):,} байт")

    print("→ Фильтрую...")
    tree, stats = filter_feed(xml_bytes)

    print(f"  оригинал: {stats['original']} товаров")
    print(f"  после:    {stats['filtered']} товаров  ({stats['ratio']})")
    print(f"  групп вариаций: {stats['groups']}")

    if stats["filtered"] < MIN_ITEMS_THRESHOLD:
        print(
            f"✗ ОШИБКА: после фильтрации {stats['filtered']} товаров "
            f"(< порога {MIN_ITEMS_THRESHOLD}). Не публикую, прерываюсь."
        )
        sys.exit(1)

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    tree.write(OUTPUT_PATH, xml_declaration=True, encoding="utf-8")

    out_size = os.path.getsize(OUTPUT_PATH)
    print(f"✓ Сохранено: {OUTPUT_PATH} ({out_size:,} байт)")


if __name__ == "__main__":
    main()
