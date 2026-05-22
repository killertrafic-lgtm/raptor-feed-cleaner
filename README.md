# Raptor-UA Feed Cleaner

Автоматическая фильтрация Google Shopping фида raptor-ua.com для Meta Ads.

## Что делает

Скачивает оригинальный фид с raptor-ua.com (2829 товаров с дублями), схлопывает
дубли по `<g:title>` и публикует очищенную версию (~528 товаров) с правильно
заполненным `<g:item_group_id>` и `<g:size>` для Meta.

**URL очищенного фида:** `https://<USERNAME>.github.io/raptor-feed-cleaner/feed.xml`

## Как работает

1. **GitHub Actions** запускается каждый час по cron
2. Качает свежий фид с raptor-ua.com
3. Прогоняет через `scripts/filter_feed.py`
4. Сохраняет в `docs/feed.xml`
5. Коммитит в репо → GitHub Pages автоматически публикует

## Безопасность

- Если в скачанном фиде < 50 товаров после фильтрации — публикация прерывается,
  старая версия фида остаётся (защита от битого оригинала на стороне Horoshop).

## Подключение к Meta

1. Открыть [Meta Commerce Manager](https://business.facebook.com/commerce_manager/)
2. Каталог → **Data Sources** → **Add items** → **Use bulk upload** → **Scheduled feed**
3. Вставить URL: `https://<USERNAME>.github.io/raptor-feed-cleaner/feed.xml`
4. Поставить **Update hourly**

## Ручной запуск

В вкладке Actions → "Update filtered feed" → "Run workflow".

## Локальный тест

```bash
python3 scripts/filter_feed.py
# → docs/feed.xml будет создан
```
