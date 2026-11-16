## Context

OpenSpec инициализирован и локально валиден, но в GitHub Actions отсутствует автоматическая проверка.

## Goals / Non-Goals

**Goals:** блокировать объединение некорректных OpenSpec-артефактов.

**Non-Goals:** не менять код, конфигурацию и развёртывание Telegram-бота.

## Decisions

- Добавить отдельный workflow для путей `openspec/**`.
- Использовать OpenSpec `1.12.0` и команду `validate --all --strict --no-interactive`.
- Не добавлять общую проверку README: такое правило в репозитории не установлено.

## Risks / Trade-offs

- Недоступность npm временно заблокирует проверку → workflow можно повторить.
- Секреты не передаются в workflow.

## Migration Plan

Добавить и проверить workflow; откат выполняется удалением файла.
