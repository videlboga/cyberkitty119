#!/usr/bin/env python3
import asyncio
import os
import tempfile
import uuid
import time
from pathlib import Path
from typing import Optional, List

from fastapi import FastAPI, File, UploadFile, HTTPException, Depends, Header, Query, Request
from fastapi.responses import JSONResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn
import httpx

from core_api.api.v1 import system as core_system_router

# Добавляем корневую директорию проекта в sys.path
import sys
current_dir = Path(__file__).parent.resolve()
sys.path.append(str(current_dir))

try:
    from transkribator_modules.transcribe.transcriber_v4 import transcribe_audio, format_transcript_with_llm
    from transkribator_modules.audio.extractor import extract_audio_from_video
    from transkribator_modules.config import logger, BOT_TOKEN
    from transkribator_modules.db.database import (
        init_database, get_db, UserService, ApiKeyService, TranscriptionService,
        calculate_audio_duration, get_plans, SessionLocal
    )
    from transkribator_modules.db.models import User, ApiKey
    from transkribator_modules.api.miniapp import router as miniapp_router
    from transkribator_modules.google_api import GoogleCredentialService, parse_state
except ImportError as e:
    print(f"Ошибка импорта: {e}")
    sys.exit(1)

app = FastAPI(
    title="Transkribator API",
    description="API для транскрибации видео с системой монетизации",
    version="2.0.0"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Подключаем мини-приложение API и статику, если собран дистрибутив
app.include_router(miniapp_router, prefix="/api")

# --- CORE API MODULES (V2) ---
app.include_router(core_system_router.router, prefix="/api/v1/system")
from core_api.api.v1 import auth as core_auth_router
app.include_router(core_auth_router.router, prefix="/api/v1/auth")
# -----------------------------

MINIAPP_DIST_PATH = current_dir / "miniapp_dist"

EVENTS_DASHBOARD_HTML = """
<!doctype html>
<html lang=\"ru\">
  <head>
    <meta charset=\"UTF-8\" />
    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
    <title>CyberKitty Admin Dashboard</title>
    <link rel=\"preconnect\" href=\"https://fonts.googleapis.com\" />
    <link rel=\"preconnect\" href=\"https://fonts.gstatic.com\" crossorigin />
    <link href=\"https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap\" rel=\"stylesheet\" />
    <script src=\"https://cdn.jsdelivr.net/npm/chart.js@4.4.6/dist/chart.umd.min.js\"></script>
    <style>
      * { box-sizing: border-box; margin: 0; padding: 0; }
      body {
        font-family: 'Inter', sans-serif;
        background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%);
        color: #e2e8f0;
        min-height: 100vh;
        padding: 20px;
      }
      .container { max-width: 1400px; margin: 0 auto; }
      
      h1 {
        font-size: 32px;
        font-weight: 700;
        margin-bottom: 8px;
        background: linear-gradient(135deg, #60a5fa 0%, #a78bfa 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
      }
      .subtitle { color: #94a3b8; margin-bottom: 24px; font-size: 14px; }
      
      /* Tabs */
      .tabs {
        display: flex;
        gap: 8px;
        margin-bottom: 24px;
        border-bottom: 2px solid rgba(148, 163, 184, 0.2);
        padding-bottom: 0;
      }
      .tab {
        padding: 12px 24px;
        background: transparent;
        border: none;
        color: #94a3b8;
        cursor: pointer;
        font-size: 14px;
        font-weight: 500;
        border-bottom: 3px solid transparent;
        transition: all 0.2s;
        position: relative;
        bottom: -2px;
      }
      .tab:hover { color: #e2e8f0; }
      .tab.active {
        color: #60a5fa;
        border-bottom-color: #60a5fa;
      }
      
      .tab-content { display: none; }
      .tab-content.active { display: block; }
      
      /* Controls */
      .controls {
        display: flex;
        gap: 12px;
        align-items: center;
        margin-bottom: 20px;
        flex-wrap: wrap;
      }
      label {
        font-size: 14px;
        font-weight: 500;
        color: #cbd5e1;
      }
      select, button {
        padding: 8px 16px;
        border-radius: 8px;
        border: 1px solid rgba(148, 163, 184, 0.3);
        background: rgba(30, 41, 59, 0.6);
        color: #e2e8f0;
        font-size: 14px;
        cursor: pointer;
        transition: all 0.2s;
      }
      select:hover, button:hover {
        border-color: #60a5fa;
        background: rgba(30, 41, 59, 0.8);
      }
      button {
        background: linear-gradient(135deg, #3b82f6 0%, #8b5cf6 100%);
        border: none;
        font-weight: 500;
      }
      button:hover { opacity: 0.9; transform: translateY(-1px); }
      
      /* Stats Cards */
      .stats-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
        gap: 16px;
        margin-bottom: 24px;
      }
      .stat-card {
        background: rgba(30, 41, 59, 0.6);
        backdrop-filter: blur(10px);
        border: 1px solid rgba(148, 163, 184, 0.2);
        border-radius: 12px;
        padding: 20px;
        transition: all 0.2s;
      }
      .stat-card:hover {
        border-color: #60a5fa;
        transform: translateY(-2px);
      }
      .stat-label {
        font-size: 12px;
        color: #94a3b8;
        text-transform: uppercase;
        letter-spacing: 0.5px;
        margin-bottom: 8px;
      }
      .stat-value {
        font-size: 28px;
        font-weight: 700;
        color: #60a5fa;
      }
      .stat-subtext {
        font-size: 12px;
        color: #64748b;
        margin-top: 4px;
      }
      
      /* Charts */
      .chart-container {
        background: rgba(30, 41, 59, 0.6);
        backdrop-filter: blur(10px);
        border: 1px solid rgba(148, 163, 184, 0.2);
        border-radius: 12px;
        padding: 24px;
        margin-bottom: 24px;
      }
      .chart-title {
        font-size: 16px;
        font-weight: 600;
        margin-bottom: 16px;
        color: #e2e8f0;
      }
      canvas { max-height: 300px !important; }
      
      /* Table */
      .table-container {
        background: rgba(30, 41, 59, 0.6);
        backdrop-filter: blur(10px);
        border: 1px solid rgba(148, 163, 184, 0.2);
        border-radius: 12px;
        padding: 24px;
        overflow-x: auto;
      }
      table {
        width: 100%;
        border-collapse: collapse;
      }
      th, td {
        padding: 12px;
        text-align: left;
        border-bottom: 1px solid rgba(148, 163, 184, 0.1);
        font-size: 13px;
      }
      th {
        background: rgba(148, 163, 184, 0.1);
        font-weight: 600;
        color: #cbd5e1;
        position: sticky;
        top: 0;
      }
      tr:hover { background: rgba(148, 163, 184, 0.05); }
      td code {
        background: rgba(0, 0, 0, 0.3);
        padding: 2px 6px;
        border-radius: 4px;
        font-size: 11px;
        color: #a78bfa;
      }
      
      /* Category badges */
      .badge {
        display: inline-block;
        padding: 4px 10px;
        border-radius: 12px;
        font-size: 11px;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.3px;
      }
      .badge-miniapp { background: rgba(59, 130, 246, 0.2); color: #60a5fa; }
      .badge-bot { background: rgba(34, 197, 94, 0.2); color: #4ade80; }
      .badge-payment { background: rgba(234, 179, 8, 0.2); color: #facc15; }
      .badge-search { background: rgba(168, 85, 247, 0.2); color: #a78bfa; }
      .badge-other { background: rgba(148, 163, 184, 0.2); color: #94a3b8; }
      
      /* Status */
      #status {
        font-size: 13px;
        color: #64748b;
        margin-top: 12px;
        text-align: right;
      }
      
      /* Grid layout for charts */
      .charts-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(400px, 1fr));
        gap: 20px;
        margin-bottom: 24px;
      }
      
      @media (max-width: 768px) {
        .stats-grid { grid-template-columns: 1fr; }
        .charts-grid { grid-template-columns: 1fr; }
        .controls { flex-direction: column; align-items: stretch; }
      }
    </style>
  </head>
  <body>
    <div class=\"container\">
      <h1>🎯 CyberKitty Admin Dashboard</h1>
      <p class=\"subtitle\">Аналитика событий пользователей и поисковых запросов</p>
      
      <div class=\"tabs\">
        <button class=\"tab active\" onclick=\"switchTab('events')\">📊 События пользователей</button>
        <button class=\"tab\" onclick=\"switchTab('search')\">🔍 Аналитика поиска</button>
        <button class=\"tab\" onclick=\"switchTab('errors')\">⚠️ Ошибки</button>
      </div>
      
      <!-- TAB 1: User Events -->
      <div id=\"events-tab\" class=\"tab-content active\">
        <div class=\"controls\">
          <label for=\"hours\">Интервал:</label>
          <select id=\"hours\">
            <option value=\"1\">1 час</option>
            <option value=\"6\" selected>6 часов</option>
            <option value=\"12\">12 часов</option>
            <option value=\"24\">24 часа</option>
            <option value=\"72\">72 часа</option>
            <option value=\"168\">7 дней</option>
          </select>
          <label for=\"categoryFilter\">Категория:</label>
          <select id=\"categoryFilter\">
            <option value=\"all\">Все</option>
            <option value=\"bot_command\">Команды</option>
            <option value=\"bot_button\">Кнопки</option>
            <option value=\"bot_media\">Медиа</option>
            <option value=\"miniapp\">MiniApp</option>
            <option value=\"payment\">Платежи</option>
            <option value=\"error\">Ошибки</option>
            <option value=\"other\">Другое</option>
          </select>
          <label for=\"userFilter\">Пользователь:</label>
          <select id=\"userFilter\">
            <option value=\"all\">Все пользователи</option>
          </select>
          <button onclick=\"loadEventsData()\">Обновить</button>
        </div>
        
        <div class=\"stats-grid\">
          <div class=\"stat-card\">
            <div class=\"stat-label\">Всего событий</div>
            <div class=\"stat-value\" id=\"totalEvents\">–</div>
          </div>
          <div class=\"stat-card\">
            <div class=\"stat-label\">Уникальных типов</div>
            <div class=\"stat-value\" id=\"uniqueKinds\">–</div>
          </div>
          <div class=\"stat-card\">
            <div class=\"stat-label\">Активных пользователей</div>
            <div class=\"stat-value\" id=\"activeUsers\">–</div>
          </div>
          <div class=\"stat-card\">
            <div class=\"stat-label\">Событий/час</div>
            <div class=\"stat-value\" id=\"eventsPerHour\">–</div>
          </div>
        </div>
        
        <div class=\"chart-container\">
          <div class=\"chart-title\">Распределение событий по типам</div>
          <canvas id=\"eventsChart\"></canvas>
        </div>
        
        <div class=\"table-container\">
          <div class=\"chart-title\">Последние события</div>
          <table>
            <thead>
              <tr>
                <th>Время</th>
                <th>Категория</th>
                <th>Тип</th>
                <th>Пользователь</th>
                <th>Telegram ID</th>
                <th>Детали</th>
              </tr>
            </thead>
            <tbody id=\"eventsBody\"></tbody>
          </table>
          <p id=\"eventsStatus\"></p>
        </div>
      </div>
      
      <!-- TAB 2: Search Analytics -->
      <div id=\"search-tab\" class=\"tab-content\">
        <div class=\"controls\">
          <label for=\"searchDays\">Период:</label>
          <select id=\"searchDays\">
            <option value=\"1\">1 день</option>
            <option value=\"7\" selected>7 дней</option>
            <option value=\"30\">30 дней</option>
          </select>
          <button onclick=\"loadSearchData()\">Обновить</button>
        </div>
        
        <div class=\"stats-grid\">
          <div class=\"stat-card\">
            <div class=\"stat-label\">Всего запросов</div>
            <div class=\"stat-value\" id=\"totalSearches\">–</div>
          </div>
          <div class=\"stat-card\">
            <div class=\"stat-label\">Кэш hit rate</div>
            <div class=\"stat-value\" id=\"cacheHitRate\">–%</div>
          </div>
          <div class=\"stat-card\">
            <div class=\"stat-label\">CTR</div>
            <div class=\"stat-value\" id=\"searchCTR\">–%</div>
          </div>
          <div class=\"stat-card\">
            <div class=\"stat-label\">Средняя скорость</div>
            <div class=\"stat-value\" id=\"avgDuration\">–</div>
            <div class=\"stat-subtext\">ms</div>
          </div>
        </div>
        
        <div class=\"charts-grid\">
          <div class=\"chart-container\">
            <div class=\"chart-title\">Тренд запросов</div>
            <canvas id=\"trendsChart\"></canvas>
          </div>
          <div class=\"chart-container\">
            <div class=\"chart-title\">Производительность</div>
            <canvas id=\"performanceChart\"></canvas>
          </div>
        </div>
        
        <div class=\"table-container\">
          <div class=\"chart-title\">Топ запросов</div>
          <table>
            <thead>
              <tr>
                <th>Запрос</th>
                <th>Кол-во</th>
                <th>Результатов</th>
                <th>Features</th>
              </tr>
            </thead>
            <tbody id=\"topQueriesBody\"></tbody>
          </table>
        </div>
        
        <div class=\"table-container\" style=\"margin-top: 20px;\">
          <div class=\"chart-title\">Последние поиски</div>
          <table>
            <thead>
              <tr>
                <th>Время</th>
                <th>Запрос</th>
                <th>Результатов</th>
                <th>Время</th>
                <th>Features</th>
              </tr>
            </thead>
            <tbody id=\"recentSearchesBody\"></tbody>
          </table>
          <p id=\"searchStatus\"></p>
        </div>
      </div>
      
      <!-- TAB 3: Errors -->
      <div id=\"errors-tab\" class=\"tab-content\">
        <div class=\"controls\">
          <label for=\"errorDays\">Период:</label>
          <select id=\"errorDays\">
            <option value=\"1\">1 день</option>
            <option value=\"7\" selected>7 дней</option>
            <option value=\"30\">30 дней</option>
          </select>
          <label for=\"errorSeverity\">Серьёзность:</label>
          <select id=\"errorSeverity\">
            <option value=\"all\">Все</option>
            <option value=\"critical\">Критические</option>
            <option value=\"error\">Ошибки</option>
            <option value=\"warning\">Предупреждения</option>
          </select>
          <button onclick=\"loadErrorsData()\">Обновить</button>
        </div>
        
        <div class=\"stats-grid\">
          <div class=\"stat-card\">
            <div class=\"stat-label\">Всего ошибок</div>
            <div class=\"stat-value\" id=\"totalErrors\">–</div>
          </div>
          <div class=\"stat-card\">
            <div class=\"stat-label\">Критических</div>
            <div class=\"stat-value\" style=\"color: #ef4444;\" id=\"criticalErrors\">–</div>
          </div>
          <div class=\"stat-card\">
            <div class=\"stat-label\">Затронуто пользователей</div>
            <div class=\"stat-value\" id=\"affectedUsers\">–</div>
          </div>
          <div class=\"stat-card\">
            <div class=\"stat-label\">Уникальных типов</div>
            <div class=\"stat-value\" id=\"errorTypes\">–</div>
          </div>
        </div>
        
        <div class=\"chart-container\">
          <div class=\"chart-title\">Ошибки по типам</div>
          <canvas id=\"errorsChart\"></canvas>
        </div>
        
        <div class=\"table-container\">
          <div class=\"chart-title\">Последние ошибки</div>
          <table>
            <thead>
              <tr>
                <th>Время</th>
                <th>Серьёзность</th>
                <th>Тип</th>
                <th>Сообщение</th>
                <th>Пользователь</th>
                <th>Traceback</th>
              </tr>
            </thead>
            <tbody id=\"errorsBody\"></tbody>
          </table>
          <p id=\"errorsStatus\"></p>
        </div>
      </div>
    </div>
    
    <script>
      let eventsChart, trendsChart, performanceChart, errorsChart;
      
      function switchTab(tab) {
        document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
        document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
        
        event.target.classList.add('active');
        document.getElementById(`${tab}-tab`).classList.add('active');
        
        if (tab === 'events') {
          loadEventsData();
        } else if (tab === 'search') {
          loadSearchData();
        } else if (tab === 'errors') {
          loadErrorsData();
        }
      }
      
      // Event display names mapping
      const EVENT_NAMES = {
        // Bot Commands
        \"bot_command_start\": \"▶️ Запуск бота\",
        \"bot_command_help\": \"❓ Запрос помощи\",
        \"bot_command_stats\": \"📊 Просмотр статистики\",
        // Bot Buttons
        \"bot_button_personal_cabinet\": \"🏠 Личный кабинет\",
        \"bot_button_show_payment_plans\": \"💎 Просмотр тарифов\",
        \"bot_button_enter_promo_code\": \"🎁 Ввод промокода\",
        \"bot_button_show_help\": \"❓ Помощь\",
        \"bot_button_process_transcript\": \"🔧 Обработка транскрипции\",
        \"bot_button_send_more\": \"📤 Отправка ещё файлов\",
        \"bot_button_google_disconnect\": \"🚫 Отключить Google\",
        // Bot Media
        \"bot_media_video_received\": \"🎥 Получено видео\",
        \"bot_media_audio_received\": \"🎵 Получено аудио\",
        \"bot_media_video_transcribed\": \"✅ Видео транскрибировано\",
        \"bot_media_audio_transcribed\": \"✅ Аудио транскрибировано\",
        // MiniApp
        \"miniapp_auth\": \"🔐 Авторизация в MiniApp\",
        \"miniapp_note_created\": \"➕ Создана заметка\",
        \"miniapp_note_updated\": \"✏️ Обновлена заметка\",
        \"miniapp_note_deleted\": \"🗑️ Удалена заметка\",
        \"miniapp_agent_message\": \"💬 Сообщение агенту\",
        \"miniapp_agent_upload\": \"📤 Загрузка файла\",
        \"miniapp_beta_status\": \"🧪 Проверка бета-статуса\",
        // Payments
        \"promo_activated\": \"🎁 Промокод активирован\",
        \"referral_commission_recorded\": \"💰 Реферальная комиссия\",
        \"referral_bonus_applied\": \"🎁 Реферальный бонус\",
        // Search
        \"search_performed\": \"🔍 Выполнен поиск\",
        // Old event names (for backward compatibility)
        \"video_transcription_saved\": \"✅ Видео транскрибировано\",
        \"audio_transcription_saved\": \"✅ Аудио транскрибировано\",
        \"bot_personal_cabinet_open\": \"🏠 Личный кабинет\"
      };
      
      function getEventDisplayName(kind) {
        return EVENT_NAMES[kind] || kind;
      }
      
      function categorizeEvent(kind) {
        if (kind.startsWith('bot_command_')) return 'bot_command';
        if (kind.startsWith('bot_button_')) return 'bot_button';
        if (kind.startsWith('bot_media_')) return 'bot_media';
        if (kind.startsWith('miniapp_')) return 'miniapp';
        if (kind.startsWith('error_')) return 'error';
        if (kind.includes('payment') || kind.includes('promo') || kind.includes('referral')) return 'payment';
        return 'other';
      }
      
      function getCategoryBadge(category) {
        const badges = {
          bot_command: '<span class=\"badge badge-bot\">🤖 Команда</span>',
          bot_button: '<span class=\"badge badge-miniapp\">🔘 Кнопка</span>',
          bot_media: '<span class=\"badge badge-search\">🎬 Медиа</span>',
          miniapp: '<span class=\"badge badge-miniapp\">📱 MiniApp</span>',
          payment: '<span class=\"badge badge-payment\">💳 Платежи</span>',
          error: '<span class=\"badge\" style=\"background: rgba(239, 68, 68, 0.2); color: #ef4444;\">⚠️ Ошибка</span>',
          other: '<span class=\"badge badge-other\">📊 Другое</span>'
        };
        return badges[category] || badges.other;
      }
      
      async function loadEventsData() {
        const hours = document.getElementById('hours').value;
        const categoryFilter = document.getElementById('categoryFilter').value;
        const userFilter = document.getElementById('userFilter').value;
        const statusEl = document.getElementById('eventsStatus');
        statusEl.textContent = 'Загружаю...';
        
        try {
          const response = await fetch(`/api/miniapp/analytics/events?hours=${hours}`);
          if (!response.ok) throw new Error('Ошибка загрузки');
          
          const data = await response.json();
          
          // Populate user filter dropdown
          const users = new Map();
          data.events.forEach(e => {
            if (!users.has(e.userId)) {
              users.set(e.userId, {
                id: e.userId,
                username: e.username || `User ${e.userId}`,
                telegramId: e.telegramId
              });
            }
          });
          
          const userSelect = document.getElementById('userFilter');
          const currentUser = userSelect.value;
          userSelect.innerHTML = '<option value=\"all\">Все пользователи</option>';
          Array.from(users.values())
            .sort((a, b) => a.username.localeCompare(b.username))
            .forEach(user => {
              const option = document.createElement('option');
              option.value = user.id;
              option.textContent = `${user.username} (${user.telegramId})`;
              userSelect.appendChild(option);
            });
          userSelect.value = currentUser;
          
          // Filter by category and user
          let filteredEvents = data.events;
          if (categoryFilter !== 'all') {
            filteredEvents = filteredEvents.filter(e => categorizeEvent(e.kind) === categoryFilter);
          }
          if (userFilter !== 'all') {
            filteredEvents = filteredEvents.filter(e => e.userId == userFilter);
          }
          
          // Update stats
          document.getElementById('totalEvents').textContent = filteredEvents.length;
          document.getElementById('uniqueKinds').textContent = new Set(filteredEvents.map(e => e.kind)).size;
          
          const uniqueUsers = new Set(filteredEvents.map(e => e.userId)).size;
          document.getElementById('activeUsers').textContent = uniqueUsers;
          document.getElementById('eventsPerHour').textContent = Math.round(filteredEvents.length / hours);
          
          // Render chart
          const labels = data.byKind.slice(0, 15).map(item => item.kind);
          const counts = data.byKind.slice(0, 15).map(item => item.count);
          
          if (eventsChart) {
            eventsChart.data.labels = labels;
            eventsChart.data.datasets[0].data = counts;
            eventsChart.update();
          } else {
            const ctx = document.getElementById('eventsChart');
            eventsChart = new Chart(ctx, {
              type: 'bar',
              data: {
                labels,
                datasets: [{
                  label: 'События',
                  data: counts,
                  backgroundColor: 'rgba(96, 165, 250, 0.8)',
                  borderColor: 'rgba(96, 165, 250, 1)',
                  borderWidth: 1
                }],
              },
              options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                  legend: { display: false },
                },
                scales: {
                  x: { 
                    ticks: { color: '#cbd5e1', maxRotation: 45, minRotation: 45 },
                    grid: { color: 'rgba(148, 163, 184, 0.1)' }
                  },
                  y: { 
                    ticks: { color: '#cbd5e1', precision: 0 },
                    grid: { color: 'rgba(148, 163, 184, 0.1)' }
                  },
                },
              },
            });
          }
          
          // Render table
          const tbody = document.getElementById('eventsBody');
          tbody.innerHTML = '';
          filteredEvents.slice(0, 100).forEach(event => {
            const row = document.createElement('tr');
            const payload = event.payload ? JSON.stringify(event.payload) : '';
            const category = categorizeEvent(event.kind);
            const displayName = getEventDisplayName(event.kind);
            
            row.innerHTML = `
              <td>${new Date(event.ts).toLocaleString()}</td>
              <td>${getCategoryBadge(category)}</td>
              <td><strong>${displayName}</strong><br><code style=\"font-size: 10px; color: #64748b;\">${event.kind}</code></td>
              <td>${event.username ?? '–'}</td>
              <td>${event.telegramId ?? '–'}</td>
              <td style=\"max-width: 300px; overflow: hidden; text-overflow: ellipsis;\">${payload}</td>
            `;
            tbody.appendChild(row);
          });
          
          statusEl.textContent = `Обновлено: ${new Date().toLocaleTimeString()}`;
        } catch (error) {
          console.error(error);
          statusEl.textContent = 'Не удалось загрузить данные';
        }
      }
      
      async function loadSearchData() {
        const days = document.getElementById('searchDays').value;
        const statusEl = document.getElementById('searchStatus');
        statusEl.textContent = 'Загружаю...';
        
        try {
          // Load summary
          const summaryRes = await fetch(`/api/miniapp/analytics/search/summary?days=${days}`);
          const summary = await summaryRes.json();
          
          document.getElementById('totalSearches').textContent = summary.total_queries || '0';
          document.getElementById('cacheHitRate').textContent = 
            summary.cache_hit_rate ? (summary.cache_hit_rate * 100).toFixed(1) + '%' : '–%';
          document.getElementById('searchCTR').textContent = 
            summary.click_through_rate ? (summary.click_through_rate * 100).toFixed(1) + '%' : '–%';
          document.getElementById('avgDuration').textContent = 
            summary.avg_duration_ms ? Math.round(summary.avg_duration_ms) + ' ms' : '–';
          
          // Load trends
          const trendsRes = await fetch(`/api/miniapp/analytics/search/trends?days=${days}`);
          const trends = await trendsRes.json();
          
          const trendLabels = trends.map(t => new Date(t.date).toLocaleDateString());
          const trendCounts = trends.map(t => t.query_count);
          
          if (trendsChart) {
            trendsChart.data.labels = trendLabels;
            trendsChart.data.datasets[0].data = trendCounts;
            trendsChart.update();
          } else {
            const ctx = document.getElementById('trendsChart');
            trendsChart = new Chart(ctx, {
              type: 'line',
              data: {
                labels: trendLabels,
                datasets: [{
                  label: 'Запросов',
                  data: trendCounts,
                  borderColor: 'rgba(168, 85, 247, 1)',
                  backgroundColor: 'rgba(168, 85, 247, 0.1)',
                  tension: 0.4,
                  fill: true
                }]
              },
              options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { display: false } },
                scales: {
                  x: { 
                    ticks: { color: '#cbd5e1' },
                    grid: { color: 'rgba(148, 163, 184, 0.1)' }
                  },
                  y: { 
                    ticks: { color: '#cbd5e1' },
                    grid: { color: 'rgba(148, 163, 184, 0.1)' }
                  }
                }
              }
            });
          }
          
          // Load performance breakdown
          const perfRes = await fetch(`/api/miniapp/analytics/search/performance?days=${days}`);
          const perf = await perfRes.json();
          
          if (performanceChart) {
            performanceChart.data.datasets[0].data = [
              perf.avg_vector_duration_ms || 0,
              perf.avg_fulltext_duration_ms || 0,
              perf.avg_rerank_duration_ms || 0
            ];
            performanceChart.update();
          } else {
            const ctx = document.getElementById('performanceChart');
            performanceChart = new Chart(ctx, {
              type: 'bar',
              data: {
                labels: ['Vector', 'Full-text', 'Rerank'],
                datasets: [{
                  label: 'Время (ms)',
                  data: [
                    perf.avg_vector_duration_ms || 0,
                    perf.avg_fulltext_duration_ms || 0,
                    perf.avg_rerank_duration_ms || 0
                  ],
                  backgroundColor: [
                    'rgba(59, 130, 246, 0.8)',
                    'rgba(34, 197, 94, 0.8)',
                    'rgba(168, 85, 247, 0.8)'
                  ]
                }]
              },
              options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { display: false } },
                scales: {
                  x: { 
                    ticks: { color: '#cbd5e1' },
                    grid: { color: 'rgba(148, 163, 184, 0.1)' }
                  },
                  y: { 
                    ticks: { color: '#cbd5e1' },
                    grid: { color: 'rgba(148, 163, 184, 0.1)' }
                  }
                }
              }
            });
          }
          
          // Load top queries
          const topRes = await fetch(`/api/miniapp/analytics/search/top-queries?days=${days}&limit=10`);
          const topQueries = await topRes.json();
          
          const topBody = document.getElementById('topQueriesBody');
          topBody.innerHTML = '';
          topQueries.forEach(q => {
            const row = document.createElement('tr');
            const features = [];
            if (q.used_hybrid) features.push('<span class=\"badge badge-search\">H</span>');
            if (q.used_rerank) features.push('<span class=\"badge badge-miniapp\">R</span>');
            if (q.used_cache) features.push('<span class=\"badge badge-bot\">C</span>');
            
            row.innerHTML = `
              <td>${q.query}</td>
              <td>${q.count}</td>
              <td>${q.avg_results || 0}</td>
              <td>${features.join(' ')}</td>
            `;
            topBody.appendChild(row);
          });
          
          // Load recent searches
          const recentRes = await fetch(`/api/miniapp/analytics/search/recent?limit=20`);
          const recentSearches = await recentRes.json();
          
          const recentBody = document.getElementById('recentSearchesBody');
          recentBody.innerHTML = '';
          recentSearches.forEach(s => {
            const row = document.createElement('tr');
            const features = [];
            if (s.used_hybrid) features.push('<span class=\"badge badge-search\">H</span>');
            if (s.used_rerank) features.push('<span class=\"badge badge-miniapp\">R</span>');
            if (s.used_cache) features.push('<span class=\"badge badge-bot\">C</span>');
            
            row.innerHTML = `
              <td>${new Date(s.timestamp).toLocaleString()}</td>
              <td>${s.query}</td>
              <td>${s.results_count}</td>
              <td>${s.duration_ms ? Math.round(s.duration_ms) + ' ms' : '–'}</td>
              <td>${features.join(' ')}</td>
            `;
            recentBody.appendChild(row);
          });
          
          statusEl.textContent = `Обновлено: ${new Date().toLocaleTimeString()}`;
        } catch (error) {
          console.error(error);
          statusEl.textContent = 'Не удалось загрузить данные';
        }
      }
      
      async function loadErrorsData() {
        const days = document.getElementById('errorDays').value;
        const severity = document.getElementById('errorSeverity').value;
        const statusEl = document.getElementById('errorsStatus');
        statusEl.textContent = 'Загружаю...';
        
        try {
          // Load errors from events with error_ prefix
          const response = await fetch(`/api/miniapp/analytics/events?hours=${days * 24}`);
          if (!response.ok) throw new Error('Ошибка загрузки');
          
          const data = await response.json();
          const errorEvents = data.events.filter(e => e.kind.startsWith('error_'));
          
          // Filter by severity if needed
          let filteredErrors = errorEvents;
          if (severity !== 'all') {
            filteredErrors = errorEvents.filter(e => {
              const payload = e.payload || {};
              return payload.severity === severity;
            });
          }
          
          // Update stats
          document.getElementById('totalErrors').textContent = errorEvents.length;
          
          const criticalCount = errorEvents.filter(e => {
            const payload = e.payload || {};
            return payload.severity === 'critical' || e.kind === 'error_critical';
          }).length;
          document.getElementById('criticalErrors').textContent = criticalCount;
          
          const affectedUsers = new Set(errorEvents.map(e => e.userId)).size;
          document.getElementById('affectedUsers').textContent = affectedUsers;
          
          const errorTypes = new Set(errorEvents.map(e => e.kind)).size;
          document.getElementById('errorTypes').textContent = errorTypes;
          
          // Render chart
          const errorCounts = {};
          errorEvents.forEach(e => {
            errorCounts[e.kind] = (errorCounts[e.kind] || 0) + 1;
          });
          
          const sortedErrors = Object.entries(errorCounts)
            .sort((a, b) => b[1] - a[1])
            .slice(0, 10);
          
          const labels = sortedErrors.map(([kind]) => getEventDisplayName(kind));
          const counts = sortedErrors.map(([, count]) => count);
          
          if (errorsChart) {
            errorsChart.data.labels = labels;
            errorsChart.data.datasets[0].data = counts;
            errorsChart.update();
          } else {
            const ctx = document.getElementById('errorsChart');
            errorsChart = new Chart(ctx, {
              type: 'bar',
              data: {
                labels,
                datasets: [{
                  label: 'Количество',
                  data: counts,
                  backgroundColor: 'rgba(239, 68, 68, 0.8)',
                  borderColor: 'rgba(239, 68, 68, 1)',
                  borderWidth: 1
                }]
              },
              options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { display: false } },
                scales: {
                  x: { 
                    ticks: { color: '#cbd5e1', maxRotation: 45, minRotation: 45 },
                    grid: { color: 'rgba(148, 163, 184, 0.1)' }
                  },
                  y: { 
                    ticks: { color: '#cbd5e1', precision: 0 },
                    grid: { color: 'rgba(148, 163, 184, 0.1)' }
                  }
                }
              }
            });
          }
          
          // Render table
          const tbody = document.getElementById('errorsBody');
          tbody.innerHTML = '';
          filteredErrors.slice(0, 50).forEach(error => {
            const row = document.createElement('tr');
            const payload = error.payload || {};
            const severity = payload.severity || 'error';
            const severityBadge = {
              critical: '<span class=\"badge\" style=\"background: rgba(239, 68, 68, 0.2); color: #ef4444;\">🚨 Критическая</span>',
              error: '<span class=\"badge\" style=\"background: rgba(249, 115, 22, 0.2); color: #f97316;\">❌ Ошибка</span>',
              warning: '<span class=\"badge\" style=\"background: rgba(234, 179, 8, 0.2); color: #eab308;\">⚠️ Предупреждение</span>'
            }[severity] || '<span class=\"badge badge-other\">📊 Другое</span>';
            
            const displayName = getEventDisplayName(error.kind);
            const message = payload.message || payload.error || '–';
            const traceback = payload.traceback ? `<details><summary>Показать</summary><pre style=\"font-size: 10px; max-height: 200px; overflow: auto;\">${payload.traceback}</pre></details>` : '–';
            
            row.innerHTML = `
              <td>${new Date(error.ts).toLocaleString()}</td>
              <td>${severityBadge}</td>
              <td><strong>${displayName}</strong><br><code style=\"font-size: 10px; color: #64748b;\">${error.kind}</code></td>
              <td style=\"max-width: 300px; overflow: hidden; text-overflow: ellipsis;\">${message}</td>
              <td>${error.username || '–'} (${error.telegramId || '–'})</td>
              <td>${traceback}</td>
            `;
            tbody.appendChild(row);
          });
          
          statusEl.textContent = `Обновлено: ${new Date().toLocaleTimeString()}`;
        } catch (error) {
          console.error(error);
          statusEl.textContent = 'Не удалось загрузить данные';
        }
      }
      
      // Auto-refresh
      document.addEventListener('DOMContentLoaded', () => {
        loadEventsData();
        
        document.getElementById('hours').addEventListener('change', loadEventsData);
        document.getElementById('categoryFilter').addEventListener('change', loadEventsData);
        document.getElementById('userFilter').addEventListener('change', loadEventsData);
        document.getElementById('searchDays').addEventListener('change', loadSearchData);
        document.getElementById('errorDays').addEventListener('change', loadErrorsData);
        document.getElementById('errorSeverity').addEventListener('change', loadErrorsData);
        
        // Auto-refresh every 30 seconds
        setInterval(() => {
          const activeTab = document.querySelector('.tab-content.active');
          if (activeTab.id === 'events-tab') {
            loadEventsData();
          } else if (activeTab.id === 'search-tab') {
            loadSearchData();
          } else if (activeTab.id === 'errors-tab') {
            loadErrorsData();
          }
        }, 30000);
      });
    </script>
  </body>
</html>

"""

if MINIAPP_DIST_PATH.exists():
    assets_dir = MINIAPP_DIST_PATH / "assets"
    if assets_dir.exists():
        app.mount(
            "/miniapp/assets",
            StaticFiles(directory=str(assets_dir)),
            name="miniapp_assets",
        )

    def _build_version_redirect(request, target_path: str):
        version_file = MINIAPP_DIST_PATH / "version.txt"
        if not version_file.exists():
            return None
        try:
            version_value = version_file.read_text(encoding="utf-8").strip()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to read miniapp version", extra={"error": str(exc)})
            return None

        current_version = request.query_params.get("v")
        logger.debug(
            "Miniapp version check",
            extra={
                "target": target_path,
                "current_version": current_version,
                "required_version": version_value,
            },
        )
        if version_value and current_version != version_value:
            return RedirectResponse(url=f"{target_path}?v={version_value}", status_code=307)
        return None

    @app.get("/miniapp", response_class=HTMLResponse)
    async def miniapp_index(request: Request):
        redirect = _build_version_redirect(request, "/miniapp")
        if redirect is not None:
            return redirect
        index_path = MINIAPP_DIST_PATH / "index.html"
        if index_path.exists():
            content = index_path.read_text(encoding="utf-8")
            headers = {
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
                "Expires": "0",
            }
            return HTMLResponse(content=content, headers=headers)
        raise HTTPException(status_code=404, detail="Mini app bundle not found")

    @app.get("/miniapp/version.txt", response_class=HTMLResponse)
    async def miniapp_version():
        version_path = MINIAPP_DIST_PATH / "version.txt"
        if version_path.exists():
            content = version_path.read_text(encoding="utf-8")
            headers = {
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
                "Expires": "0",
            }
            return HTMLResponse(content=content, headers=headers)
        raise HTTPException(status_code=404, detail="Version metadata not found")

    @app.get("/miniapp/{path:path}", response_class=HTMLResponse)
    async def miniapp_catchall(path: str, request: Request):
        if path == "version.txt":
            return await miniapp_version()
        redirect = _build_version_redirect(request, f"/miniapp/{path}")
        if redirect is not None:
            return redirect
        index_path = MINIAPP_DIST_PATH / "index.html"
        if index_path.exists():
            content = index_path.read_text(encoding="utf-8")
            headers = {
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
                "Expires": "0",
            }
            return HTMLResponse(content=content, headers=headers)
        raise HTTPException(status_code=404, detail="Mini app bundle not found")

    @app.get("/events-dashboard", response_class=HTMLResponse)
    async def events_dashboard():
        return HTMLResponse(EVENTS_DASHBOARD_HTML)

# Инициализируем базу данных при запуске
init_database()

# Настраиваем webhook для ЮКассы
from transkribator_modules.bot.yukassa_webhook import setup_yukassa_webhook
setup_yukassa_webhook(app)

# Создаем временные директории
TEMP_DIR = Path("/tmp/transkribator")
TEMP_DIR.mkdir(exist_ok=True)

# Pydantic модели для API
class PlanInfo(BaseModel):
    name: str
    display_name: str
    minutes_per_month: Optional[float]
    max_file_size_mb: float
    price_rub: float
    price_usd: float
    description: str
    features: List[str]

class UserInfo(BaseModel):
    telegram_id: int
    username: Optional[str]
    current_plan: str
    plan_display_name: str
    minutes_used_this_month: float
    minutes_limit: Optional[float]
    minutes_remaining: float
    usage_percentage: float
    total_minutes_transcribed: float

class ApiKeyInfo(BaseModel):
    name: str
    created_at: str
    last_used_at: Optional[str]
    minutes_limit: Optional[float]
    minutes_used: float
    is_active: bool

class TranscriptionResult(BaseModel):
    task_id: str
    filename: str
    file_size_mb: float
    audio_duration_minutes: float
    raw_transcript: str
    formatted_transcript: str
    transcript_length: int
    processing_time_seconds: float
    formatted_with_llm: bool

# Dependency для проверки API ключа
async def verify_api_key(
    authorization: str = Header(None),
    x_api_key: str = Header(None),
    api_key: str = Query(None),
    db = Depends(get_db)
) -> tuple[User, Optional[ApiKey]]:
    """Проверка API ключа и возврат пользователя"""

    # Получаем ключ из разных источников
    key = None
    if authorization and authorization.startswith("Bearer "):
        key = authorization[7:]
    elif x_api_key:
        key = x_api_key
    elif api_key:
        key = api_key

    if not key:
        raise HTTPException(
            status_code=401,
            detail="API ключ не предоставлен. Используйте заголовок Authorization: Bearer <key> или X-API-Key"
        )

    api_key_service = ApiKeyService(db)
    api_key_obj = api_key_service.verify_api_key(key)

    if not api_key_obj:
        raise HTTPException(
            status_code=401,
            detail="Недействительный API ключ"
        )

    user_service = UserService(db)
    user = db.query(User).filter(User.id == api_key_obj.user_id).first()

    if not user or not user.is_active:
        raise HTTPException(
            status_code=401,
            detail="Пользователь не найден или заблокирован"
        )

    return user, api_key_obj

@app.get("/")
async def root():
    """Главная страница API"""
    return {
        "message": "Transkribator API v2.0",
        "version": "2.0.0",
        "features": ["Транскрибация видео", "Система монетизации", "API ключи", "Лимиты пользователей"],
        "endpoints": {
            "/transcribe": "POST - Загрузить видео для транскрибации (требует API ключ)",
            "/plans": "GET - Список доступных тарифных планов",
            "/user/info": "GET - Информация о пользователе и использовании",
            "/user/api-keys": "GET - Список API ключей пользователя",
            "/webhook/yukassa": "POST - Webhook для обработки платежей ЮКассы",
            "/health": "GET - Проверка состояния сервиса"
        }
    }

@app.get("/health")
async def health_check():
    """Проверка состояния сервиса"""
    return {"status": "healthy", "service": "transkribator-api", "version": "2.0.0"}


async def _notify_google_result(telegram_id: Optional[int], message: str) -> None:
    if not BOT_TOKEN or not telegram_id:
        return
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            await client.post(url, json={"chat_id": telegram_id, "text": message})
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Failed to notify user about Google OAuth result",
            extra={"error": str(exc), "telegram_id": telegram_id},
        )


def _html_response(title: str, body: str, status_code: int = 200) -> HTMLResponse:
    content = f"""
    <html>
        <head>
            <meta charset='utf-8'/>
            <title>{title}</title>
            <style>body{{font-family:Arial,sans-serif;background:#0f172a;color:#e2e8f0;padding:40px;text-align:center}}a{{color:#38bdf8}}</style>
        </head>
        <body>
            <h1>{title}</h1>
            <p>{body}</p>
            <p>Можно вернуться в Telegram 🤖</p>
        </body>
    </html>
    """
    return HTMLResponse(content=content, status_code=status_code)


@app.get("/google/callback", response_class=HTMLResponse)
async def google_oauth_callback(
    code: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
    error: Optional[str] = Query(None),
):
    logger.info(
        "Google OAuth callback received",
        extra={"code_present": bool(code), "state": state, "error": error},
    )

    if error:
        return _html_response("Авторизация отклонена", f"Google вернул ошибку: {error}", status_code=400)

    if not code or not state:
        return _html_response("Ошибка", "Не найден параметр code/state в ответе Google", status_code=400)

    try:
        user_id, _ = parse_state(state)
    except ValueError as exc:
        logger.warning("Invalid Google OAuth state", extra={"error": str(exc)})
        return _html_response("Ошибка", "Некорректный state. Попробуйте начать авторизацию заново.", status_code=400)

    db = SessionLocal()
    telegram_id: Optional[int] = None
    try:
        user = db.query(User).filter(User.id == user_id).one_or_none()
        if not user:
            logger.error("User not found for Google OAuth", extra={"user_id": user_id})
            return _html_response("Ошибка", "Пользователь не найден. Попробуйте снова.", status_code=404)

        telegram_id = user.telegram_id

        google_service = GoogleCredentialService(db)
        flow = google_service.build_flow(state=state)
        flow.fetch_token(code=code)
        credentials = flow.credentials

        tokens = {
            "access_token": credentials.token,
            "refresh_token": credentials.refresh_token,
            "expiry": credentials.expiry.isoformat() if credentials.expiry else None,
        }

        google_service.store_tokens(user_id, tokens, list(credentials.scopes or []))

        await _notify_google_result(
            telegram_id,
            "✅ Google Drive подключён. Возвращайся в Telegram — заметки будут сохраняться в Drive.",
        )

        return _html_response(
            "Google подключён",
            "Интеграция успешно настроена. Можно вернуться в чат с ботом.",
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception(
            "Google OAuth callback failed",
            extra={"user_id": user_id, "error": str(exc)},
        )
        await _notify_google_result(
            telegram_id,
            "⚠️ Не удалось подключить Google. Попробуй ещё раз через личный кабинет.",
        )
        return _html_response(
            "Ошибка",
            "Не удалось завершить авторизацию. Попробуйте начать подключение заново.",
            status_code=500,
        )
    finally:
        db.close()

@app.get("/plans", response_model=List[PlanInfo])
async def get_plans_endpoint():
    """Получить список доступных тарифных планов"""
    plans = get_plans()
    result = []

    for plan in plans:
        features = []
        if plan.features:
            import json
            try:
                features = json.loads(plan.features)
            except:
                features = [plan.features]

        result.append(PlanInfo(
            name=plan.name,
            display_name=plan.display_name,
            minutes_per_month=plan.minutes_per_month,
            max_file_size_mb=plan.max_file_size_mb,
            price_rub=plan.price_rub,
            price_usd=plan.price_usd,
            description=plan.description or "",
            features=features
        ))

    return result

@app.get("/user/info", response_model=UserInfo)
async def get_user_info(user_and_key: tuple = Depends(verify_api_key)):
    """Получить информацию о пользователе и его использовании"""
    user, api_key = user_and_key
    db = next(get_db())

    user_service = UserService(db)
    usage_info = user_service.get_usage_info(user)

    return UserInfo(
        telegram_id=user.telegram_id,
        username=user.username,
        current_plan=usage_info["current_plan"],
        plan_display_name=usage_info["plan_display_name"],
        minutes_used_this_month=usage_info["minutes_used_this_month"],
        minutes_limit=usage_info["minutes_limit"],
        minutes_remaining=usage_info["minutes_remaining"],
        usage_percentage=usage_info["usage_percentage"],
        total_minutes_transcribed=usage_info["total_minutes_transcribed"]
    )

@app.post("/transcribe", response_model=TranscriptionResult)
async def transcribe_video(
    file: UploadFile = File(...),
    format_with_llm: bool = True,
    user_and_key: tuple = Depends(verify_api_key)
):
    """
    Транскрибирует загруженное видео с проверкой лимитов

    - **file**: Видеофайл для транскрибации
    - **format_with_llm**: Форматировать ли результат с помощью LLM (по умолчанию True)
    """
    user, api_key = user_and_key
    db = next(get_db())

    # Проверяем тип файла по расширению и content_type
    video_extensions = {'.mp4', '.avi', '.mov', '.mkv', '.webm', '.flv', '.wmv', '.m4v'}
    audio_extensions = {'.mp3', '.wav', '.flac', '.aac', '.ogg', '.m4a', '.wma'}

    file_extension = Path(file.filename).suffix.lower() if file.filename else ''
    is_valid_extension = file_extension in video_extensions or file_extension in audio_extensions
    is_valid_content_type = file.content_type and file.content_type.startswith(('video/', 'audio/'))

    if not (is_valid_extension or is_valid_content_type):
        raise HTTPException(
            status_code=400,
            detail="Поддерживаются только видео и аудио файлы"
        )

    # Генерируем уникальный ID для обработки
    task_id = str(uuid.uuid4())
    start_time = time.time()
    logger.info(f"Начинаю обработку файла {file.filename}, task_id: {task_id}, пользователь: {user.telegram_id}")

    # Создаем временные файлы
    temp_video_path = TEMP_DIR / f"{task_id}_video"
    temp_audio_path = TEMP_DIR / f"{task_id}_audio.wav"

    try:
        # Сохраняем загруженный файл
        logger.info(f"Сохраняю загруженный файл: {file.filename}")
        with open(temp_video_path, "wb") as buffer:
            content = await file.read()
            buffer.write(content)

        file_size_mb = len(content) / (1024 * 1024)
        logger.info(f"Файл сохранен, размер: {file_size_mb:.1f} МБ")

        # Проверяем лимиты размера файла
        user_service = UserService(db)
        plan = user_service.get_user_plan(user)

        if plan and file_size_mb > plan.max_file_size_mb:
            raise HTTPException(
                status_code=413,
                detail=f"Файл слишком большой. Максимальный размер для вашего плана: {plan.max_file_size_mb} МБ"
            )

        # Оцениваем длительность аудио
        estimated_duration = calculate_audio_duration(file_size_mb)

        # Проверяем лимиты пользователя
        can_use, limit_message = user_service.check_usage_limit(user, estimated_duration)
        if not can_use:
            raise HTTPException(
                status_code=429,
                detail=f"Превышен лимит использования: {limit_message}"
            )

        # Проверяем лимиты API ключа
        if api_key:
            api_key_service = ApiKeyService(db)
            can_use_api, api_limit_message = api_key_service.check_api_key_limits(api_key, estimated_duration)
            if not can_use_api:
                raise HTTPException(
                    status_code=429,
                    detail=f"Превышен лимит API ключа: {api_limit_message}"
                )

        # Извлекаем аудио из видео
        logger.info("Извлекаю аудио из видео...")
        success = await extract_audio_from_video(temp_video_path, temp_audio_path)

        if not success or not temp_audio_path.exists():
            raise HTTPException(
                status_code=500,
                detail="Не удалось извлечь аудио из видеофайла"
            )

        audio_size_mb = temp_audio_path.stat().st_size / (1024 * 1024)
        logger.info(f"Аудио извлечено, размер: {audio_size_mb:.1f} МБ")

        # Более точный расчет длительности после извлечения аудио
        actual_duration = calculate_audio_duration(audio_size_mb)

        # Транскрибируем аудио (с разбивкой на сегменты для больших файлов)
        logger.info("Начинаю транскрибацию через DeepInfra API...")
        raw_transcript = await transcribe_audio(temp_audio_path)

        if not raw_transcript:
            raise HTTPException(
                status_code=500,
                detail="Не удалось получить транскрипцию от API"
            )

        logger.info(f"Получена сырая транскрипция длиной {len(raw_transcript)} символов")

        # Форматируем транскрипцию, если требуется
        formatted_transcript = raw_transcript
        formatting_service = None

        if format_with_llm:
            logger.info("Форматирую транскрипцию с помощью LLM...")
            try:
                formatted_result = await format_transcript_with_llm(raw_transcript)
                if formatted_result and formatted_result != raw_transcript:
                    formatted_transcript = formatted_result
                    formatting_service = "openrouter"
                    logger.info("Транскрипция отформатирована")
                else:
                    logger.info("Форматирование не изменило текст или не удалось")
            except Exception as e:
                logger.warning(f"Ошибка при форматировании: {e}, используем сырую транскрипцию")

        processing_time = time.time() - start_time

        # Сохраняем результат в базу данных
        transcription_service = TranscriptionService(db)
        transcription_record = transcription_service.save_transcription(
            user=user,
            filename=file.filename,
            file_size_mb=file_size_mb,
            audio_duration_minutes=actual_duration,
            raw_transcript=raw_transcript,
            formatted_transcript=formatted_transcript,
            processing_time=processing_time,
            transcription_service="deepinfra",
            formatting_service=formatting_service or "none"
        )

        # Логируем событие сохранения для аналитики
        try:
            from transkribator_modules.db.database import log_event as _log_event
            _log_event(user.id, "api_transcription_saved", {
                "filename": file.filename,
                "duration_min": actual_duration,
                "text_len": len(formatted_transcript or raw_transcript or ""),
                "formatting_service": formatting_service or "none",
            })
        except Exception:
            pass

        # Обновляем использование (минуты или генерации)
        user_service.add_usage(user, actual_duration)

        # Обновляем использованные минуты для API ключа
        if api_key:
            api_key_service.add_api_key_usage(api_key, actual_duration)

        # Возвращаем результат
        result = TranscriptionResult(
            task_id=task_id,
            filename=file.filename,
            file_size_mb=round(file_size_mb, 2),
            audio_duration_minutes=round(actual_duration, 2),
            raw_transcript=raw_transcript,
            formatted_transcript=formatted_transcript,
            transcript_length=len(formatted_transcript),
            processing_time_seconds=round(processing_time, 2),
            formatted_with_llm=format_with_llm and (formatted_transcript != raw_transcript)
        )

        logger.info(f"Транскрибация завершена успешно, task_id: {task_id}, время: {processing_time:.1f}с")
        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка при обработке файла {file.filename}: {e}")
        import traceback
        logger.error(traceback.format_exc())
        raise HTTPException(
            status_code=500,
            detail=f"Внутренняя ошибка сервера: {str(e)}"
        )

    finally:
        # Очищаем временные файлы
        try:
            if temp_video_path.exists():
                temp_video_path.unlink()
            if temp_audio_path.exists():
                temp_audio_path.unlink()
            logger.info(f"Временные файлы очищены для task_id: {task_id}")
        except Exception as e:
            logger.warning(f"Не удалось очистить временные файлы: {e}")


# ============================================================================
# WHISPER GPU PIPELINE ENDPOINTS
# ============================================================================

# Импортируем оркестратор
try:
    from pipeline_orchestrator import WhisperPipeline
    PIPELINE_AVAILABLE = True
except ImportError:
    PIPELINE_AVAILABLE = False
    logger.warning("Pipeline orchestrator not available - GPU transcription endpoint disabled")


class PipelineRequest(BaseModel):
    file_path: str
    language: str = "ru"


class PipelineResult(BaseModel):
    status: str
    job_id: str
    total_time: float
    preparation_time: float
    transcription_time: float
    result_file: str
    report_file: str
    segments: int
    audio_duration: float
    error: Optional[str] = None


@app.post("/api/v1/transcribe-gpu")
async def transcribe_gpu(request: PipelineRequest) -> PipelineResult:
    """
    Transcribe media file using local Whisper GPU (RTX 3070 Ti).
    
    This endpoint provides GPU-accelerated transcription using the local
    Whisper pipeline, achieving ~4x speedup vs CPU.
    
    Args:
        file_path: Path to media file (video or audio)
        language: Language code (default: "ru" for Russian)
    
    Returns:
        PipelineResult with transcription status and file paths
    
    Performance:
        - Single file: ~57 seconds for 21-min audio
        - 5 parallel: ~146 seconds (3.5x speedup)
        - GPU memory: 3.49GB peak (safe margin on 7.7GB)
    """
    
    if not PIPELINE_AVAILABLE:
        raise HTTPException(
            status_code=503,
            detail="GPU pipeline not available"
        )
    
    try:
        file_path = Path(request.file_path)
        
        # Validate file exists
        if not file_path.exists():
            logger.error(f"File not found: {file_path}")
            raise HTTPException(
                status_code=404,
                detail=f"File not found: {file_path}"
            )
        
        # Validate file size (max 1GB)
        file_size = file_path.stat().st_size
        if file_size > 1024 * 1024 * 1024:  # 1GB
            logger.error(f"File too large: {file_size} bytes")
            raise HTTPException(
                status_code=413,
                detail=f"File too large: {file_size / 1024**3:.1f}GB (max 1GB)"
            )
        
        logger.info(f"Starting GPU transcription: {file_path.name} ({file_size / 1024**2:.1f}MB)")
        
        # Process with pipeline
        pipeline = WhisperPipeline()
        result = pipeline.process(file_path)
        
        if result["status"] != "success":
            logger.error(f"Pipeline failed: {result.get('error')}")
            return PipelineResult(
                status="error",
                job_id="",
                total_time=0,
                preparation_time=0,
                transcription_time=0,
                result_file="",
                report_file="",
                segments=0,
                audio_duration=0,
                error=result.get("error", "Unknown error")
            )
        
        logger.info(f"GPU transcription completed: {result['job_id']}")
        logger.info(f"  Preparation: {result['preparation_time']:.2f}s")
        logger.info(f"  Transcription: {result['transcription_time']:.2f}s")
        logger.info(f"  Total: {result['total_time']:.2f}s")
        
        return PipelineResult(
            status="success",
            job_id=result["job_id"],
            total_time=result["total_time"],
            preparation_time=result["preparation_time"],
            transcription_time=result["transcription_time"],
            result_file=result["result_file"],
            report_file=result["report_file"],
            segments=result["segments"],
            audio_duration=result["audio_duration"]
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"GPU pipeline error: {e}")
        import traceback
        logger.error(traceback.format_exc())
        raise HTTPException(
            status_code=500,
            detail=f"Pipeline error: {str(e)}"
        )


@app.get("/api/v1/pipeline-status")
async def pipeline_status() -> dict:
    """Get pipeline status and GPU information."""
    
    if not PIPELINE_AVAILABLE:
        return {
            "status": "unavailable",
            "gpu": None
        }
    
    try:
        import torch
        gpu_available = torch.cuda.is_available()
        gpu_name = torch.cuda.get_device_name(0) if gpu_available else None
        gpu_memory = None
        
        if gpu_available:
            props = torch.cuda.get_device_properties(0)
            total_mem = props.total_memory / 1024**3
            free_mem = torch.cuda.mem_get_info()[0] / 1024**3
            gpu_memory = {
                "total_gb": round(total_mem, 1),
                "free_gb": round(free_mem, 1),
                "used_percent": round((1 - free_mem/total_mem) * 100, 1)
            }
        
        return {
            "status": "available",
            "gpu": {
                "available": gpu_available,
                "name": gpu_name,
                "memory": gpu_memory
            },
            "performance": {
                "single_file_time": "~57 seconds",
                "parallel_capacity": "5 concurrent",
                "throughput": "5.27 files/min max"
            }
        }
    except Exception as e:
        logger.error(f"Error getting pipeline status: {e}")
        return {
            "status": "error",
            "error": str(e)
        }


if __name__ == "__main__":
    # Запускаем сервер
    uvicorn.run(
        "api_server:app",
        host="0.0.0.0",
        port=8000,
        log_level="info"
    )
