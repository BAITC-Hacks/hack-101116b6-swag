"""Motion and chart presentation; no analysis, external assets or shared user cache."""

import streamlit as st


STEPS = {
    "parse": "Чтение документов",
    "structure": "Структура подразделений",
    "functions": "Извлечение функций",
    "match": "Сопоставление функций",
    "findings": "Поиск изменений",
    "verify": "Проверка цитат",
    "report": "Подготовка заключения",
}

# A small v2 component reads the device preference, which Python cannot access.
# It owns only its checkbox; native Streamlit widgets keep their semantics.
_MOTION_DEFINITION = dict(
    html="""
    <label><input type="checkbox" /> Плавные переходы</label>
    <small aria-live="polite"></small>
    """,
    css="""
    label { display:flex; align-items:center; gap:8px; min-height:40px;
      font:inherit; color:var(--st-text-color); cursor:pointer; }
    input { width:17px; height:17px; accent-color:var(--st-primary-color); }
    input:focus-visible { outline:2px solid var(--st-primary-color); outline-offset:4px; }
    small { display:block; color:var(--st-gray-text-color, #526571);
      font-size:12px; line-height:1.5; }
    """,
    js="""
    export default function(component) {
      const {parentElement, data, setStateValue} = component;
      const input = parentElement.querySelector('input');
      const note = parentElement.querySelector('small');
      const media = window.matchMedia('(prefers-reduced-motion: reduce)');
      const enabled = data.enabled !== false;
      const render = (wanted) => {
        input.checked = wanted && !media.matches;
        input.disabled = media.matches;
        note.textContent = media.matches
          ? 'Устройство настроено на уменьшение движения.'
          : 'Можно отключить в любой момент.';
      };
      const publish = (wanted) => {
        const reduced = media.matches || !wanted;
        render(wanted);
        if (data.reduced !== reduced) setStateValue('reduced', reduced);
      };
      render(enabled);
      publish(enabled);
      input.onchange = () => {
        const wanted = input.checked;
        setStateValue('enabled', wanted);
        publish(wanted);
      };
      const onPreference = () => publish(enabled);
      media.addEventListener('change', onPreference);
      return () => {
        media.removeEventListener('change', onPreference);
        input.onchange = null;
      };
    }
    """,
)


def motion_control():
    state = st.session_state.get("ui_motion", {})
    # Registration belongs to the active runtime, not to a bare Python import.
    # Streamlit deduplicates this unchanged definition on subsequent reruns.
    control = st.components.v2.component("org_motion_preference", **_MOTION_DEFINITION)
    control(
        key="ui_motion",
        data={"enabled": state.get("enabled", True), "reduced": state.get("reduced")},
        default={"enabled": True, "reduced": True},
        on_enabled_change=lambda: None,
        on_reduced_change=lambda: None,
    )


def motion_enabled():
    # No animation until the browser has reported its accessibility preference.
    return not st.session_state.get("ui_motion", {}).get("reduced", True)


def install_transitions():
    """Only requested interaction motion; colours/layout stay in the native theme."""
    active = motion_enabled()
    st.html("""
    <style>
    @keyframes org-reveal { from { opacity:.45; transform:translateY(5px); }
                           to { opacity:1; transform:translateY(0); } }
    @media (prefers-reduced-motion: no-preference) {
      .stButton button, .stDownloadButton button, .stTabs [role="tab"],
      .stFileUploader section, .stExpander summary {
        transition:background-color 160ms ease, border-color 160ms ease,
                   box-shadow 160ms ease, transform 160ms ease;
      }
      .stFileUploader section:hover, .stFileUploader section:focus-within {
        transform:translateY(-2px);
        box-shadow:0 3px 0 color-mix(in srgb, #356B70 20%, transparent);
      }
      .stButton button:active:not(:disabled) { transform:scale(.985); }
      .stTabs [role="tabpanel"]:not([hidden]) { animation:org-reveal 220ms ease-out; }
      .st-key-upload_before [data-testid="stFileUploaderFile"],
      .st-key-upload_after [data-testid="stFileUploaderFile"] {
        animation:org-reveal 220ms ease-out;
      }
      .stProgress [role="progressbar"] > div { transition:width 240ms ease; }
    }
    </style>
    """ if active else """
    <style>
    .stButton button, .stDownloadButton button, .stTabs [role="tab"],
    .stFileUploader section, .stExpander summary { transition:none !important; }
    .stTabs [role="tabpanel"], .stProgress *,
    [data-testid="stFileUploaderFile"] { animation:none !important; transition:none !important; }
    </style>
    """)


def upload_summary(uploads):
    size = sum(upload.size for upload in uploads)
    if uploads:
        st.badge(f"Файлов готово: {len(uploads)}", color="green", icon=":material/task_alt:")
        st.caption(f"{size / 1024 / 1024:.2f} МБ · получены, ещё не проанализированы")
    else:
        st.caption("Перетащите файлы сюда или нажмите Upload.")


class RunProgress:
    """Render actual log arrivals without inventing duration or completion events."""

    def __init__(self):
        self.seen = set()
        self.status = st.status("Читаем документы и подготавливаем сравнение…", expanded=True)
        self.bar = self.status.progress(0.0, text="Ожидаем события анализа")
        self.status.caption("Документы · структура · функции · сопоставление · находки · цитаты · заключение")
        self.latest = self.status.empty()

    def __call__(self, step, status, message):
        if step in STEPS:
            self.seen.add(step)
        self.bar.progress(len(self.seen) / len(STEPS), text=f"Этапов в журнале: {len(self.seen)} из {len(STEPS)}")
        self.status.update(label=f"{STEPS.get(step, step)} · {status}")
        self.latest.text(message)

    def finish(self, *, success):
        self.status.update(
            label="Сравнение завершено · результат ниже" if success else "Обработка остановлена",
            state="complete" if success else "error", expanded=not success,
        )


def bar_spec(rows, *, animate):
    """Counts retain their actual scale. Full labels also exist in the data table."""
    ordered = sorted(rows, key=lambda row: row["Количество"], reverse=True)
    return {
        "animation": animate, "animationDuration": 650,
        "animationDurationUpdate": 280, "animationEasing": "cubicOut",
        "aria": {"enabled": True, "label": {"description": "; ".join(
            f"{r['Категория']}: {r['Количество']}" for r in ordered)}},
        "grid": {"top": 12, "bottom": 30, "left": 166, "right": 38, "outerBoundsMode": "none"},
        "tooltip": {"trigger": "item", "renderMode": "richText", "confine": True,
                    "formatter": "{b}: {c}"},
        "xAxis": {"type": "value", "minInterval": 1, "min": 0, "splitNumber": 3,
                  "splitLine": {"lineStyle": {"type": "dashed", "opacity": 0.3}}},
        "yAxis": {"type": "category", "inverse": True,
                  "data": [row["Категория"] for row in ordered],
                  "axisLine": {"show": False}, "axisTick": {"show": False},
                  "axisLabel": {"width": 150, "overflow": "break", "lineHeight": 17, "fontSize": 12}},
        "series": [{"type": "bar", "id": "counts", "barMaxWidth": 22,
                    "label": {"show": True, "position": "right", "fontSize": 13},
                    "itemStyle": {"borderRadius": [0, 4, 4, 0]},
                    "emphasis": {"focus": "self"},
                    "data": [{"name": row["Категория"], "value": row["Количество"],
                              "itemStyle": {"color": row["color"]}} for row in ordered]}],
        "media": [{"query": {"maxWidth": 420}, "option": {
            "grid": {"left": 130, "right": 30},
            "yAxis": {"axisLabel": {"width": 116, "fontSize": 11}},
        }}],
    }


def render_animated_chart(rows, title, bars):
    with st.container(border=True):
        st.markdown(f"**{title}**")
        if not rows:
            st.caption("Нет данных.")
            return
        st.echarts_chart(
            bar_spec(rows, animate=motion_enabled()), renderer="svg",
            height=max(200, 50 + 54 * bars),
            key=f"{st.session_state.run_id}:chart:{title}",
        )
        with st.expander("Значения графика", icon=":material/table_rows:"):
            st.dataframe([{k: row[k] for k in ("Категория", "Количество")} for row in rows], hide_index=True)


def finding_counts(findings, decisions, view):
    if view == "Решения":
        counts = {"Подтверждено": 0, "Отклонено": 0, "Ожидает решения": 0}
        labels = {"confirmed": "Подтверждено", "rejected": "Отклонено"}
        colors = {"Подтверждено": "#5B8A6E", "Отклонено": "#8C9BA3", "Ожидает решения": "#B9854A"}
        for item in findings:
            counts[labels.get(decisions.get(item.get("id")), "Ожидает решения")] += 1
    else:
        field = "type" if view == "По типу" else "severity"
        labels = ({"loss": "Утрата функции", "duplicate": "Дублирование", "conflict": "Противоречие",
                   "reorganization": "Реорганизация"} if field == "type" else
                  {"high": "Высокая", "medium": "Средняя", "low": "Низкая"})
        colors = {"Утрата функции": "#B06565", "Дублирование": "#B9854A", "Противоречие": "#4F7F86",
                  "Реорганизация": "#8C9BA3", "Высокая": "#B06565", "Средняя": "#B9854A", "Низкая": "#8C9BA3"}
        counts = {}
        for item in findings:
            category = labels.get(item.get(field), item.get(field) or "Не указано")
            counts[category] = counts.get(category, 0) + 1
    return [{"Категория": name, "Количество": value, "color": colors.get(name, "#8C9BA3")}
            for name, value in counts.items() if value]


def render_findings_overview(findings, decisions):
    if not findings:
        return
    with st.expander("Очередь проверки находок", expanded=True, icon=":material/donut_large:"):
        view = st.segmented_control(
            "Группировка находок", ["По типу", "По важности", "Решения"], default="По важности",
            key=f"{st.session_state.run_id}:chart_view", required=True,
        )
        rows = finding_counts(findings, decisions, view)
        chart_col, text_col = st.columns([3, 2], vertical_alignment="center")
        with chart_col:
            spec = {
                "animation": motion_enabled(), "animationDuration": 650, "animationDurationUpdate": 280,
                "animationEasing": "cubicOut", "aria": {"enabled": True, "label": {
                    "description": f"Находок: {len(findings)}. " + "; ".join(
                        f"{r['Категория']}: {r['Количество']}" for r in rows)}},
                "tooltip": {"trigger": "item", "renderMode": "richText", "confine": True,
                            "formatter": "{b}: {c} ({d}%)"},
                "series": [{"type": "pie", "id": "findings", "radius": ["55%", "78%"],
                            "center": ["50%", "50%"], "avoidLabelOverlap": True,
                            "label": {"show": False}, "labelLine": {"show": False},
                            "itemStyle": {"borderRadius": 4}, "padAngle": 3,
                            "emphasis": {"scaleSize": 5},
                            "data": [{"name": r["Категория"], "value": r["Количество"],
                                      "itemStyle": {"color": r["color"]}} for r in rows]}],
                "title": {"text": str(len(findings)), "subtext": "находок", "left": "center",
                          "top": "38%", "textStyle": {"fontSize": 32, "fontWeight": 600}},
            }
            st.echarts_chart(spec, key=f"{st.session_state.run_id}:findings_chart", renderer="svg", height=260)
        with text_col:
            st.markdown(f"**{view}**")
            st.dataframe([{k: r[k] for k in ("Категория", "Количество")} for r in rows], hide_index=True)
            st.caption("Наведите на сегмент, чтобы увидеть долю. Решения принимает пользователь во вкладке «Находки».")
            st.caption("Подтверждение находки не меняет проверку цитаты.")
