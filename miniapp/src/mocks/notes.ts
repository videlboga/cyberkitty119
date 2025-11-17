import type { Note } from '@/features/notes/types'

const now = new Date()

const daysAgo = (value: number) => {
  const date = new Date(now)
  date.setDate(date.getDate() - value)
  return date.toISOString()
}

const daysAhead = (value: number) => {
  const date = new Date(now)
  date.setDate(date.getDate() + value)
  return date.toISOString()
}

export const mockNotes: Note[] = [
  {
    id: 'note-001',
    title: 'Созвон с командой разработчиков',
    summary: 'Краткий обзор статуса задач и согласование следующих шагов.',
    content:
      'Обсудили прогресс по интеграции мини-приложения, утвердили сроки по API и фронтенду. Нужно подготовить демо в пятницу.',
    tags: ['команда', 'созвон'],
    groupIds: ['group-002'],
    type: 'meeting',
    createdAt: daysAgo(1),
    updatedAt: daysAgo(1),
    scheduledAt: daysAhead(1),
    attachments: [
      {
        id: 'att-001',
        name: 'Запись встречи',
        type: 'audio',
        url: '#',
      },
    ],
  },
  {
    id: 'note-002',
    title: 'Идеи по улучшению UX',
    summary: 'Черновой список улучшений для мобильного интерфейса.',
    content:
      '1. Добавить жесты свайпа в списке заметок. 2. Упростить выбор фильтров. 3. Переработать календарь под компактный режим.',
    tags: ['ux', 'idea'],
    groupIds: ['group-001'],
    type: 'idea',
    createdAt: daysAgo(3),
    updatedAt: daysAgo(2),
    scheduledAt: daysAhead(5),
  },
  {
    id: 'note-003',
    title: 'Релиз версии 1.3',
    summary: 'План по выкладке и чек-лист перед релизом.',
    content:
      'Проверить миграции, собрать changelog, обновить документацию. После выката мониторим метрики 24 часа.',
    tags: ['release', 'план'],
    groupIds: ['group-001'],
    type: 'task',
    createdAt: daysAgo(7),
    updatedAt: daysAgo(4),
    scheduledAt: daysAgo(1),
  },
  {
    id: 'note-004',
    title: 'Встреча с продуктом',
    summary: 'Бриф по roadmap на Q2.',
    content:
      'Обсудить фокус на AI-функции, оценить ресурсы, подготовить предложения по A/B тестам.',
    tags: ['product', 'roadmap'],
    groupIds: ['group-001'],
    type: 'meeting',
    createdAt: daysAgo(2),
    updatedAt: daysAgo(1),
    scheduledAt: daysAhead(2),
  },
  {
    id: 'note-005',
    title: 'Сводка по аналитике',
    summary: 'Основные метрики за прошлую неделю.',
    content:
      'Конверсия в регистрацию выросла на 4%, время до первой заметки сократилось на 12%. Надо продумать ретеншн-кампанию.',
    tags: ['аналитика'],
    groupIds: ['group-002'],
    type: 'summary',
    createdAt: daysAgo(5),
    updatedAt: daysAgo(3),
  },
  {
    id: 'note-006',
    title: 'AI предложения по группам',
    summary: 'Генерируем теги на основе новых заметок.',
    content:
      'Подготовить промпт, выделить ключевые слова и связать с текущими категориями. Проверить точность моделей.',
    tags: ['ai', 'исследование'],
    groupIds: ['group-003'],
    type: 'idea',
    createdAt: daysAgo(1),
    updatedAt: daysAgo(1),
  },
  {
    id: 'note-007',
    title: 'Согласование дизайна',
    summary: 'Финализировать экраны календаря и редактора.',
    content:
      'Получить апрув у дизайнера, уточнить отступы, подготовить версию для разработки.',
    tags: ['design', 'календарь'],
    groupIds: ['group-001'],
    type: 'task',
    createdAt: daysAgo(4),
    updatedAt: daysAgo(2),
    scheduledAt: daysAhead(3),
  },
  {
    id: 'note-008',
    title: 'Архив: миграция данных',
    summary: 'Завершённый проект по переносу заметок.',
    content:
      'Миграция завершена успешно. Храним документацию и скрипты в архиве.',
    tags: ['архив', 'infra'],
    groupIds: ['group-001'],
    type: 'summary',
    createdAt: daysAgo(30),
    updatedAt: daysAgo(29),
    archivedAt: daysAgo(10),
  },
  {
    id: 'note-009',
    title: 'Подготовить демо для Telegram',
    summary: 'Собрать сценарий презентации и тестовые данные.',
    content:
      'Собрать успешные кейсы для демонстрации, записать короткое видео по навигации.',
    tags: ['демо', 'telegram'],
    groupIds: ['group-002'],
    type: 'task',
    createdAt: daysAgo(1),
    updatedAt: daysAgo(1),
    scheduledAt: daysAhead(4),
  },
]
