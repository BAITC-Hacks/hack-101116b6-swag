"""Shared visual shell. Static product copy never substitutes for analysis data."""

from base64 import b64encode
from html import escape
from pathlib import Path

import streamlit as st


PAGES = {
    "Мои сравнения": {
        "title": "От документов —<br>к ясной структуре.",
        "description": "Сравнивайте редакции, проверяйте изменения и согласуйте решения. Документы, вопросы и история каждого анализа — рядом.",
        "action": "К моим сравнениям", "art": "analysis",
        "steps": [("Сравните", "Добавьте редакции до и после"),
                  ("Проверьте", "Изучите находки и задайте вопросы"),
                  ("Согласуйте", "Подготовьте документы для команды")],
    },
    "Мои документы": {
        "title": "Ваша роль.<br>Ваши документы.",
        "description": "Откройте назначенные документы и изменения по своей роли. Задайте вопрос или отметьте ознакомление с нужной версией.",
        "action": "К моим документам", "art": "onboarding",
        "steps": [("Выберите роль", "Демонстрационный профиль сотрудника"),
                  ("Изучите документы", "Назначенные версии и изменения"),
                  ("Отметьте прочитанное", "Или задайте уточняющий вопрос")],
    },
    "Анализ изменений": {
        "title": "От документов —<br>к ясной структуре.",
        "description": "Сравните редакции, найдите изменения в функциях и проверьте каждый вывод по источнику.",
        "action": "Начать сравнение", "art": "analysis",
        "steps": [("Сравните", "Загрузите документы до и после"),
                  ("Проверьте", "Изучите изменения и цитаты"),
                  ("Согласуйте", "Подготовьте проверенную версию")],
    },
    "ИИ-чат": {
        "title": "Ваш вопрос.<br>Ответ в документах.",
        "description": "Разберитесь в изменениях с помощью вопросов. Сверяйте ответы с пунктами и цитатами из вашего комплекта.",
        "action": "Перейти к вопросам", "art": "chat",
        "steps": [("Сравните документы", "Чат использует текущий анализ"),
                  ("Задайте вопрос", "О функции, роли или изменении"),
                  ("Проверьте источник", "Откройте пункт и его цитату")],
    },
    "Согласование": {
        "title": "Одна версия.<br>Общее решение.",
        "description": "Соберите решения участников по проверенной версии документов. Замечания и история останутся рядом.",
        "action": "К согласованию", "art": "approval",
        "steps": [("Выберите версию", "Документы и проверенные изменения"),
                  ("Задайте маршрут", "Укажите участников согласования"),
                  ("Соберите решения", "Согласование или возврат с комментарием")],
    },
    "Ознакомление": {
        "title": "Изменения понятны.<br>Команда в курсе.",
        "description": "Откройте сотрудникам согласованные документы. Следите за ознакомлением и отвечайте на вопросы по изменениям.",
        "action": "К документам команды", "art": "acknowledgement",
        "steps": [("Откройте доступ", "К согласованной версии"),
                  ("Изучите изменения", "Каждый сотрудник — для своей роли"),
                  ("Проверьте статус", "Отметки и вопросы в одном месте")],
    },
    "Документы новичка": {
        "title": "Первый день.<br>Понятный маршрут.",
        "description": "Соберите для нового сотрудника документы по его роли. Помогите освоиться и отслеживайте ознакомление с пакетом.",
        "action": "К пакету документов", "art": "onboarding",
        "steps": [("Выберите сотрудника", "Учитывайте его должность"),
                  ("Соберите пакет", "Из опубликованных версий"),
                  ("Следите за прогрессом", "По каждому назначенному документу")],
    },
}

LOGO = '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 48 48" fill="none" aria-hidden="true">
<rect width="48" height="48" rx="15" fill="#24584B"/>
<path d="M24 18v8m-11 4v-6h22v6" stroke="#B9D4C7" stroke-width="2"/>
<rect x="18" y="9" width="12" height="12" rx="4" fill="white"/>
<rect x="8" y="29" width="10" height="10" rx="3" fill="white"/>
<rect x="30" y="29" width="10" height="10" rx="3" fill="#C7DDB2"/></svg>'''


def install_design():
    st.html(f"<style>{Path(__file__).with_name('styles.css').read_text()}</style>")


def render_brand():
    logo = b64encode(LOGO.encode()).decode()
    st.html(f'<div class="org-brand"><img src="data:image/svg+xml;base64,{logo}" alt="" width="46" height="46"><div><strong>Оргструктура</strong>'
            '<span>Документы. Функции. Решения.</span></div></div>')


def _art(kind):
    """Concept illustrations, not fabricated findings or actionable controls."""
    if kind == "analysis":
        return '''<div class="art-overline">СВЯЗЬ МЕЖДУ РЕДАКЦИЯМИ</div>
        <div class="document-pair"><div class="paper paper-before"><span>До изменений</span>
        <div class="paper-line long"></div><div class="paper-line"></div><div class="clause old"></div>
        <div class="paper-line"></div><div class="paper-line short"></div><i>Предыдущая редакция</i></div>
        <div class="paper paper-after"><span>После изменений</span>
        <div class="paper-line long"></div><div class="paper-line"></div><div class="clause new"></div>
        <div class="paper-line"></div><div class="paper-line short"></div><i>Новая редакция</i></div>
        <div class="document-link">↔</div></div>
        <div class="art-note"><span class="note-mark">§</span> За каждым выводом — источник</div>'''
    if kind == "chat":
        return '''<div class="art-overline">ДИАЛОГ С ОПОРОЙ НА ИСТОЧНИК</div>
        <div class="conversation"><div class="question-note">Что изменилось в обязанностях?</div>
        <div class="answer-note"><span class="answer-label">ОТ ВОПРОСА К ИСТОЧНИКУ</span>
        <div class="paper-line long"></div><div class="paper-line"></div>
        <div class="source-note">Документ <b>→</b> Пункт <b>→</b> Цитата</div></div></div>
        <div class="art-note"><span class="note-mark">↗</span> Контекст вашего комплекта документов</div>'''
    if kind == "approval":
        return '''<div class="art-overline">МАРШРУТ ПРИНЯТИЯ РЕШЕНИЯ</div>
        <div class="route-illustration"><div class="route-row"><span class="route-dot">1</span>
        <div><b>Проверенная версия</b><small>Документы и изменения</small></div></div>
        <div class="route-row"><span class="route-dot">2</span>
        <div><b>Участники маршрута</b><small>Решения и комментарии</small></div></div>
        <div class="route-row"><span class="route-dot final-dot">3</span>
        <div><b>Итог согласования</b><small>Зафиксирован для этой версии</small></div></div></div>'''
    if kind == "acknowledgement":
        return '''<div class="art-overline">ОТ ДОКУМЕНТА К КОМАНДЕ</div>
        <div class="team-illustration"><div class="shared-document"><span class="note-mark">§</span>
        <div><b>Согласованная версия</b><small>Документы и изменения по ролям</small></div></div>
        <div class="team-connector"></div><div class="team-people"><span>Сотрудник</span><span>Сотрудник</span><span>Сотрудник</span></div></div>
        <div class="art-note"><span class="note-mark">✓</span> Ознакомление · вопросы · ответы</div>'''
    return '''<div class="art-overline">ВСЁ ДЛЯ ЗНАКОМСТВА С РОЛЬЮ</div>
    <div class="folder-illustration"><div class="folder-tab">Пакет сотрудника</div>
    <div class="folder-body"><div><span>01</span> Документы по должности</div>
    <div><span>02</span> Назначенные изменения</div><div><span>03</span> Отметки об ознакомлении</div></div></div>
    <div class="art-note"><span class="note-mark">→</span> Последовательно, документ за документом</div>'''


def render_hero(page, *, compact=False):
    content = PAGES[page]
    size = " compact" if compact else ""
    title = content["title"].replace("<br>", " ") if compact else content["title"]
    st.html(f'''<section class="org-hero{size}" aria-labelledby="page-heading">
      <div class="hero-copy"><p class="hero-section">{escape(page)}</p>
      <h1 id="page-heading">{title}</h1><p class="hero-description">{content['description']}</p>
      <a class="hero-action" href="#workspace" target="_self">{content['action']} <span aria-hidden="true">↓</span></a></div>
      <div class="hero-art art-{content['art']}" aria-hidden="true">{_art(content['art'])}</div>
    </section>''')
    if not compact:
        steps = "".join(f'<li><span class="step-number">{i:02}</span><div><b>{title}</b><span>{description}</span></div></li>'
                        for i, (title, description) in enumerate(content["steps"], 1))
        st.html(f'<ol class="org-steps" aria-label="Как работает раздел">{steps}</ol>')


def render_notice(text):
    st.html(f'<p class="org-notice"><span aria-hidden="true">ⓘ</span>{escape(text)}</p>')


def render_section_intro(section):
    content = {
        "Результат": ("Проверьте главное", "Начните с резюме и важных находок. Полные сопоставления и источники доступны ниже."),
        "Вопросы": ("Разберитесь в деталях", "Спросите о функции, роли или изменении. Чат использует только документы этого сравнения."),
        "Согласование": ("От проверки к решению", "Подготовьте версию и соберите решения участников. Замечания сохранятся в маршруте."),
        "Ознакомление": ("Передайте изменения команде", "Откройте согласованную версию сотрудникам и следите за ознакомлением. Здесь же можно собрать пакет новичку."),
    }
    title, description = content[section]
    st.html(f'<div class="org-section-intro"><h2>{title}</h2><p>{description}</p></div>')


def render_empty(title, description, *, symbol="§"):
    # Actions remain native Streamlit widgets so they preserve the session.
    st.html(f'<div class="org-empty"><span class="empty-symbol" aria-hidden="true">{escape(symbol)}</span>'
            f'<div><h2>{escape(title)}</h2><p>{escape(description)}</p></div></div>')


def render_footer():
    st.html('<footer class="org-footer"><span>Оргструктура <b>·</b> От документа к решению</span>'
            '<span>Рабочий прототип · данные в текущей сессии</span></footer>')
