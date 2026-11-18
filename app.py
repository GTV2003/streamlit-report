"""
Интерактивный доклад «Web-приложения на базе Streamlit» и общий квиз.
Запуск из этой папки: python -m streamlit run app.py
"""

import time
from html import escape
from urllib.parse import urlencode

import numpy as np
import pandas as pd
import streamlit as st

from quiz_ui import audience_page, ensure_participant, get_store, is_presenter, presenter_login, quiz_stage, watch_round

st.set_page_config(page_title="Streamlit · доклад", layout="wide")

ACCENT = "#E5483D"   # красный: читается и на светлом, и на тёмном фоне
GREEN = "#16A34A"
SURFACE = "rgba(128,128,128,.08)"   # фон карточек для обеих тем
LINE = "rgba(128,128,128,.25)"

# ============================================================ стили
st.markdown(
    f"""
    <style>
    /* кнопки Community Cloud (Share, звезда, редактирование, GitHub) и кнопка Deploy */
    [data-testid="stToolbarActions"], [data-testid="stAppDeployButton"] {{display:none !important;}}
    .block-container {{padding-top: 1.6rem; max-width: 1280px;}}
    .topbar {{display:flex; justify-content:space-between; align-items:center;
              font-size:.85rem; letter-spacing:.08em; opacity:.75; text-transform:uppercase;
              border-bottom:1px solid {LINE}; padding-bottom:.6rem; margin-bottom:1.2rem;}}
    .live {{color:{GREEN};}}
    .kicker {{color:{ACCENT}; font-size:.9rem; font-weight:700; letter-spacing:.12em;
              text-transform:uppercase; margin-bottom:.3rem;}}
    .h1 {{font-size:3rem; font-weight:800; line-height:1.05; margin:.2rem 0 1rem;}}
    .h1 span {{color:{ACCENT};}}
    .h2 {{font-size:2.2rem; font-weight:800; line-height:1.15; margin:.1rem 0 .5rem;}}
    .lead {{font-size:1.2rem; opacity:.85; margin-bottom:1.2rem; line-height:1.5;}}
    .card {{background:{SURFACE}; border:1px solid {LINE}; border-radius:12px;
            padding:1rem 1.1rem; height:100%;}}
    .card .num {{color:{ACCENT}; font-weight:800; font-size:.9rem;}}
    .card h4 {{margin:.25rem 0 .35rem; font-size:1.1rem; padding:0;}}
    .card p {{margin:0; opacity:.85; font-size:1rem; line-height:1.45;}}
    .panel-label {{font-size:.85rem; letter-spacing:.1em; text-transform:uppercase; opacity:.75;
                   display:flex; justify-content:space-between; margin-bottom:.4rem; font-weight:600;}}
    .hint {{border-left:3px solid {ACCENT}; padding:.4rem .8rem; opacity:.9; font-size:1rem;
            margin-top:.8rem;}}
    .flow {{display:flex; gap:.6rem; align-items:stretch; flex-wrap:wrap; margin:.6rem 0 1rem;}}
    .flow .step {{flex:1; min-width:150px;}}
    .flow .arrow {{align-self:center; color:{ACCENT}; font-size:1.4rem;}}
    .grid {{display:grid; gap:.8rem; margin-bottom:1.2rem;}}
    .grid.g4 {{grid-template-columns:repeat(4, 1fr);}}
    .grid.g2 {{grid-template-columns:repeat(2, 1fr);}}
    @media (max-width: 900px) {{ .grid.g4, .grid.g2 {{grid-template-columns:1fr;}} }}
    .grid .card h4 {{font-size:1.05rem;}}
    .grid .card p {{font-size:.95rem;}}
    .pc {{background:{SURFACE}; border:1px solid {LINE}; border-radius:12px; padding:1rem 1.2rem;}}
    .pc h3 {{margin:0 0 .6rem; font-size:1.25rem; padding:0;}}
    .pc ul {{list-style:none; padding:0; margin:0;}}
    .pc li {{display:flex; gap:.7rem; padding:.45rem 0; border-top:1px solid {LINE}; line-height:1.4;
             margin:0;}}
    .pc li:first-child {{border-top:none;}}
    .pc .mk {{flex:0 0 1.4rem; height:1.4rem; border-radius:6px; display:flex; align-items:center;
              justify-content:center; font-weight:800;}}
    .pc.plus .mk {{background:rgba(22,163,74,.15); color:{GREEN};}}
    .pc.minus .mk {{background:rgba(229,72,61,.15); color:{ACCENT};}}
    .pc li b {{display:block;}}
    .pc li small {{opacity:.8; font-size:.95rem;}}
    .authors {{margin-top:1.6rem;}}
    .authors .names {{display:grid; grid-template-columns:repeat(2, max-content); gap:.35rem 2.2rem;
                      font-size:1.45rem; font-weight:600; line-height:1.3;}}
    .quiz-stage h1 {{font-size:clamp(2.8rem,6vw,5rem); line-height:1.05; margin:.35rem 0 .6rem;
                    padding:0; letter-spacing:-.035em;}}
    .quiz-stage h1 span {{color:{ACCENT};}}
    .finish-cloud {{display:flex; flex-wrap:wrap; align-content:center; justify-content:center;
                   align-items:center; gap:.7rem 1.1rem; min-height:235px; padding:1.2rem;
                   border:1px solid {LINE}; border-radius:12px; background:{SURFACE}; text-align:center;}}
    .cloud-name {{max-width:100%; overflow-wrap:anywhere; font-weight:650; line-height:1.25;}}
    .empty-cloud p {{margin:.35rem 0 0; opacity:.75;}}
    .st-key-quiz_options [role="radiogroup"] {{gap:.5rem;}}
    .st-key-quiz_options [data-testid="stRadio"] label {{padding:.65rem 1rem; width:100%;
                       border:1px solid {LINE}; border-radius:8px;}}
    .st-key-quiz_options [data-testid="stRadio"] label:has(input:checked) {{border-color:{ACCENT};}}
    @media (max-width: 700px) {{
        .authors .names {{grid-template-columns:1fr; font-size:1.15rem;}}
    }}
    .theme-links {{display:flex; gap:.5rem;}}
    .theme-links a {{flex:1; text-align:center; padding:.35rem .5rem; border:1px solid {LINE};
                     border-radius:8px; text-decoration:none; color:inherit; font-size:.9rem;}}
    .theme-links a:hover {{border-color:{ACCENT};}}
    </style>
    """,
    unsafe_allow_html=True,
)


def html(s: str) -> None:
    st.markdown(s, unsafe_allow_html=True)


def title(kicker: str, text: str, lead: str = "") -> None:
    html(f'<div class="kicker">{kicker}</div><div class="h2">{text}</div>')
    if lead:
        html(f'<div class="lead">{lead}</div>')


def card(num: str, head: str, body: str) -> None:
    html(f'<div class="card"><div class="num">{num}</div><h4>{head}</h4><p>{body}</p></div>')


def live_label(text: str) -> None:
    html(f'<div class="panel-label"><span>{text}</span><span class="live">● работает</span></div>')


def code(src: str) -> None:
    if st.session_state.get("show_code", True):
        st.code(src, language="python", line_numbers=True)


def hint(text: str) -> None:
    html(f'<div class="hint">{text}</div>')


AUTHORS = ["Габараев Владимир", "Глухарев Тихон", "Овсяник Геннадий", "Головачев Егор", "Кобелев Иван"]

# ============================================================ данные
REGIONS =["Москва", "Казань", "Волгоград", "Новосибирск"]


@st.cache_data
def load_sales() -> pd.DataFrame:
    """Учебные продажи по дням и регионам за первое полугодие 2026 года."""
    rng = np.random.default_rng(7)
    dates = pd.date_range("2026-01-01", "2026-06-30", freq="D")
    rows = []
    for r_i, region in enumerate(REGIONS):
        base = [32000, 18000, 12000, 15000][r_i]
        for d in dates:
            trend = 1 + 0.25 * (d.dayofyear / 181)
            weekend = 1.25 if d.dayofweek >= 5 else 1.0
            sales = max(0, rng.normal(base * trend * weekend, base * 0.12))
            orders = max(1, int(sales / rng.normal(1700, 120)))
            rows.append((d, region, round(sales), orders))
    return pd.DataFrame(rows, columns=["date", "region", "sales", "orders"])


def daily_total(df: pd.DataFrame) -> pd.DataFrame:
    return df.groupby("date", as_index=False)[["sales", "orders"]].sum()


def rub(x: float) -> str:
    return f"{x:,.0f} ₽".replace(",", " ")


# ============================================================ СЛАЙДЫ
def s_intro():
    c1, c2 = st.columns([1.3, 1], gap="large")
    with c1:
        html('<div class="kicker">Python → Web / интерактивный доклад</div>')
        html('<div class="h1">Web-приложения<br>на базе<br><span>Streamlit</span></div>')
        html('<div class="lead">Как превратить Python-скрипт в интерактивный сервис.</div>')
        html('<div class="authors"><div class="panel-label"><span>Студенты</span></div><div class="names">'
             + "".join(f"<span>{n}</span>" for n in AUTHORS) + "</div></div>")
    with c2:
        with st.container(border=True):
            live_label("Анализ продаж")
            days = st.slider("Период, дней", 7, 30, 14, key="intro_days")
            period = daily_total(load_sales()).tail(days)
            st.metric("Выручка за период", rub(period.sales.sum()))
            st.area_chart(period, x="date", y="sales", color=ACCENT, height=220,
                          x_label="", y_label="Продажи, ₽")
        code('days = st.slider("Период, дней", 7, 30, 14)\n'
             "period = daily.tail(days)\n"
             'st.metric("Выручка", period.sales.sum())')


def s_what():
    title("Знакомство", "Что такое Streamlit",
          "Open-source библиотека, которая превращает Python-скрипт в веб-приложение "
          "без HTML, CSS и JavaScript. Появилась в 2019 году, с 2022 года принадлежит Snowflake.")
    c1, c2 = st.columns([1, 1], gap="large")
    with c1:
        code('import streamlit as st\n\nst.title("Анализ продаж")\nst.metric("Выручка", "1,2 млн ₽")')
        st.code("pip install streamlit\nstreamlit run app.py", language="bash")
    with c2:
        with st.container(border=True):
            live_label("Результат")
            st.title("Анализ продаж")
            st.metric("Выручка", "1,2 млн ₽")
        st.caption("Одна команда Python — один элемент интерфейса. Справа настоящий результат, а не картинка.")
    st.write("")
    cols = st.columns(4)
    items = [("Аналитика", "Дашборды, отчёты, фильтры."),
             ("Машинное обучение", "Ввод признаков и просмотр предсказаний."),
             ("Прототипы", "Быстрая проверка идеи."),
             ("Обучение", "Интерактивные примеры для аудитории.")]
    for i, (col, (h, b)) in enumerate(zip(cols, items), 1):
        with col:
            card(f"0{i}", h, b)


def s_how():
    title("Знакомство", "Как устроено приложение",
          "Python выполняется на сервере, а пользователь работает с результатом в браузере.")
    html("""
    <div class="flow">
      <div class="step"><div class="card"><div class="num">01</div><h4>app.py</h4><p>Ваш Python-код</p></div></div>
      <div class="arrow">→</div>
      <div class="step"><div class="card"><div class="num">02</div><h4>Streamlit</h4><p>Сервер приложения</p></div></div>
      <div class="arrow">→</div>
      <div class="step"><div class="card"><div class="num">03</div><h4>Браузер</h4><p>Интерфейс</p></div></div>
      <div class="arrow">→</div>
      <div class="step"><div class="card"><div class="num">04</div><h4>Действие</h4><p>Скрипт выполняется заново</p></div></div>
    </div>""")
    st.session_state.how_runs = st.session_state.get("how_runs", 0) + 1
    c1, c2 = st.columns([1, 1], gap="large")
    with c1:
        with st.container(border=True):
            live_label("Проверьте сами")
            n = st.slider("Измените число", 1, 10, 3, key="how_n")
            st.metric("Квадрат числа", n * n)
            st.button("Выполнить скрипт ещё раз", key="how_btn")
    with c2:
        with st.container(border=True):
            st.metric("Выполнений скрипта на этом слайде", st.session_state.how_runs)
            st.caption("Каждое движение ползунка и каждый клик запускают app.py сверху вниз.")
    hint("Формы позволяют отправить несколько значений разом, а Session State сохраняет данные между запусками.")


def s_first():
    title("Первые шаги", "Первое приложение",
          "Поле ввода возвращает строку. Дальше работает обычный Python.")
    c1, c2 = st.columns([1, 1], gap="large")
    with c1:
        code('import streamlit as st\n\nst.subheader("Мой первый сайт")\n'
             'name = st.text_input("Ваше имя")\n\nif name.strip():\n    st.success(f"Привет, {name}!")')
    with c2:
        with st.container(border=True):
            live_label("Результат")
            st.subheader("Мой первый сайт")
            name = st.text_input("Ваше имя", key="first_name", placeholder="Введите имя и нажмите Enter")
            if name.strip():
                st.success(f"Привет, {name}!")


def s_widgets():
    title("Первые шаги", "Виджеты управляют расчётом",
          "Значение виджета сразу лежит в обычной переменной. На его основе фильтруем данные и строим графики.")
    df = load_sales()
    c1, c2 = st.columns([1, 1.1], gap="large")
    with c1:
        code('days = st.slider("Период", 1, 30, 7)\n'
             'city = st.selectbox("Город", cities)\n'
             'show_table = st.checkbox("Показать таблицу")\n\n'
             "period = df[df.region == city].tail(days)\n"
             'st.metric("Выручка", period.sales.sum())\n'
             'st.line_chart(period, x="date", y="sales")\n'
             "if show_table:\n    st.dataframe(period)")
    with c2:
        with st.container(border=True):
            live_label("Результат")
            a, b = st.columns(2)
            days = a.slider("Период", 1, 30, 7, key="w_days")
            city = b.selectbox("Город", REGIONS, key="w_city")
            show = st.checkbox("Показать таблицу", key="w_table")
            period = df[df.region == city].tail(days)
            st.metric("Выручка", rub(period.sales.sum()))
            st.line_chart(period, x="date", y="sales", color=ACCENT, height=200, x_label="", y_label="")
            if show:
                st.dataframe(period, hide_index=True, height=180)


def s_charts():
    title("Данные и графики", "Графики без сложной настройки",
          "Один набор данных можно показать разными способами.")
    weekly = (load_sales().set_index("date").resample("W")["sales"].sum().reset_index())
    kind = st.segmented_control("Вид графика", ["Линия", "Столбцы", "Точки"], default="Линия", key="ch_kind") or "Линия"
    c1, c2 = st.columns([1, 2], gap="large")
    fn = {"Линия": "line_chart", "Столбцы": "bar_chart", "Точки": "scatter_chart"}[kind]
    with c1:
        code(f'# weekly — продажи по неделям\nst.{fn}(weekly, x="date", y="sales")')
        st.caption({"Линия": "Линия показывает изменение продаж во времени.",
                    "Столбцы": "Столбцы удобно сравнивать между собой.",
                    "Точки": "Точки помогают заметить выбросы."}[kind])
        hint("Для сложных графиков есть интеграция с Plotly, Altair и Matplotlib.")
    with c2:
        getattr(st, fn)(weekly, x="date", y="sales", color=ACCENT, height=330, x_label="", y_label="Продажи, ₽")


def s_state():
    title("Состояние и кеш", "Session State: сохраняем состояние",
          "Обычные переменные создаются заново при каждом запуске скрипта. "
          "Session State хранит значения внутри сессии пользователя.")
    c1, c2, c3 = st.columns([1.1, 1, 1], gap="large")
    with c1:
        code('if "count" not in st.session_state:\n    st.session_state.count = 0\n\n'
             'if st.button("Прибавить"):\n    st.session_state.count += 1\n\n'
             'st.metric("Счётчик", st.session_state.count)')
    with c2:
        with st.container(border=True):
            html('<div class="panel-label"><span>Обычная переменная</span></div>')
            count = 0
            if st.button("+1 к обычной переменной", key="st_plain", width="stretch"):
                count += 1
            st.metric("count", count)
            st.caption("В начале каждого запуска count = 0, поэтому больше 1 не получится.")
    with c3:
        with st.container(border=True):
            live_label("Session State")
            st.session_state.setdefault("count", 0)
            if st.button("+1 в session_state", key="st_ss", type="primary", width="stretch"):
                st.session_state.count += 1
            st.metric("st.session_state.count", st.session_state.count)
            st.caption("Перейдите на другой слайд и вернитесь: число сохранится.")


@st.cache_data(ttl=600, show_spinner=False)
def slow_report(rows: int) -> float:
    time.sleep(0.8)  # учебная задержка
    rng = np.random.default_rng(42)
    return float(rng.normal(100, 15, rows).mean())


def s_cache():
    title("Состояние и кеш", "Кеширование вычислений",
          "Первый вызов выполняет функцию. Повторный вызов с теми же аргументами берёт сохранённый результат.")
    c1, c2 = st.columns([1, 1], gap="large")
    with c1:
        code("@st.cache_data(ttl=600)\ndef slow_report(rows):\n    time.sleep(0.8)  # учебная задержка\n"
             "    values = rng.normal(100, 15, rows)\n    return values.mean()\n\nresult = slow_report(rows)")
        st.caption("@st.cache_data — для данных (DataFrame, ответы API). "
                   "@st.cache_resource — для моделей и подключений к БД.")
    with c2:
        with st.container(border=True):
            live_label("Сравните два запуска")
            rows = st.select_slider("Число значений", [10_000, 100_000, 1_000_000], 100_000, key="c_rows",
                                    format_func=lambda v: f"{v:,}".replace(",", " "))
            a, b = st.columns(2)
            run = a.button("Выполнить расчёт", type="primary", width="stretch", key="c_run")
            if b.button("Сбросить кеш", width="stretch", key="c_clear"):
                slow_report.clear()
                st.session_state.pop("cache_last", None)
            if run:
                t0 = time.perf_counter()
                res = slow_report(rows)
                st.session_state.cache_last = (res, time.perf_counter() - t0)
            if "cache_last" in st.session_state:
                res, dt = st.session_state.cache_last
                m1, m2 = st.columns(2)
                m1.metric("Среднее", f"{res:.2f}")
                m2.metric("Время", f"{dt:.3f} с")
                (st.warning if dt > 0.5 else st.success)("Вычисление" if dt > 0.5 else "Из кеша")
            else:
                st.caption("Нажмите «Выполнить расчёт» дважды с одним и тем же числом значений.")


def card_html(num: str, head: str, body: str) -> str:
    return f'<div class="card"><div class="num">{num}</div><h4>{head}</h4><p>{body}</p></div>'


def s_deploy():
    title("Публикация", "Публикация и безопасность",
          "Локальный прототип выкладывается в сеть за несколько минут. Эта презентация опубликована именно так.")
    steps = [
        ("app.py + requirements.txt", "Код и список библиотек."),
        ("GitHub", "Загружаем репозиторий."),
        ("Community Cloud", "share.streamlit.io: репозиторий и главный файл."),
        ("Ссылка готова", "имя.streamlit.app, бесплатно."),
    ]
    parts = []
    for i, (h, b) in enumerate(steps, 1):
        if i > 1:
            parts.append('<div class="arrow">→</div>')
        parts.append(f'<div class="step">{card_html(f"0{i}", h, b)}</div>')
    html('<div class="panel-label"><span>Как опубликовать</span></div>'
         f'<div class="flow">{"".join(parts)}</div>')
    st.caption("Другие варианты: Docker, свой сервер с nginx, Hugging Face Spaces.")
    st.write("")
    risks = [
        ("Секреты", "Пароли и ключи — в secrets.toml, не в коде и не в GitHub."),
        ("Загружаемые файлы", "Проверять формат, размер и столбцы."),
        ("Нагрузка", "Каждое действие перезапускает скрипт: тяжёлое кешировать."),
        ("Доступ", "Публичная ссылка открыта всем. Для закрытых данных нужна авторизация."),
    ]
    html('<div class="panel-label"><span>Что учитывать</span></div><div class="grid g4">'
         + "".join(card_html(f"0{i}", h, b) for i, (h, b) in enumerate(risks, 1)) + "</div>")


def s_dashboard():
    title("Практика", "Практика: дашборд продаж",
          "Один экран: фильтры, вычисления Pandas, показатели, графики и исходные данные.")
    df = load_sales()
    f1, f2 = st.columns([2, 1])
    regions = f1.multiselect("Регионы", REGIONS, default=REGIONS[:3], key="d_regions")
    days = f2.select_slider("Последние дни", [7, 30, 90], 30, key="d_days")
    if not regions:
        st.warning("Выберите хотя бы один регион.")
        return
    sel = df[df.region.isin(regions)]
    end = sel.date.max()
    cur = sel[sel.date > end - pd.Timedelta(days=days)]
    prev = sel[(sel.date <= end - pd.Timedelta(days=days)) & (sel.date > end - pd.Timedelta(days=2 * days))]
    delta = (cur.sales.sum() / prev.sales.sum() - 1) * 100 if prev.sales.sum() else 0
    m1, m2, m3 = st.columns(3)
    m1.metric("Выручка", rub(cur.sales.sum()), f"{delta:+.1f}% к предыдущему периоду")
    m2.metric("Заказы", f"{cur.orders.sum():,}".replace(",", " "))
    m3.metric("Средний чек", rub(cur.sales.sum() / max(cur.orders.sum(), 1)))
    g1, g2 = st.columns([1.6, 1], gap="large")
    with g1:
        live_label("Продажи по дням")
        st.line_chart(cur.pivot_table(index="date", columns="region", values="sales"), height=260,
                      x_label="", y_label="Продажи, ₽")
    with g2:
        live_label("Продажи по регионам")
        st.bar_chart(cur.groupby("region")["sales"].sum(), horizontal=True, color=ACCENT, height=260,
                     x_label="", y_label="")
    with st.expander("Исходные данные"):
        st.dataframe(cur.sort_values("date", ascending=False), hide_index=True, height=220)
        st.download_button("Скачать CSV", cur.to_csv(index=False).encode("utf-8-sig"), "sales.csv", "text/csv")


PROS = [
    ("Только Python", "Без HTML, CSS и JavaScript."),
    ("Быстрая разработка", "Дашборд с фильтрами и графиками — примерно за час."),
    ("Готовые элементы", "Виджеты, таблицы, графики, формы, загрузка файлов."),
    ("Экосистема данных", "pandas, Plotly, Altair, scikit-learn, PyTorch."),
    ("Бесплатная публикация", "Community Cloud: ссылка из GitHub за пару минут."),
]
CONS = [
    ("Перезапуск всего скрипта", "Нужны Session State и кеш, иначе всё считается заново."),
    ("Ограниченный дизайн", "Нестандартный интерфейс — только через CSS вручную."),
    ("Нагрузка", "На тысячи одновременных пользователей не рассчитан."),
    ("Сложная логика и доступ", "Много экранов, роли и права делать неудобно."),
]


def pc_block(kind: str, head: str, items: list, mark: str) -> str:
    li = "".join(f'<li><div class="mk">{mark}</div><span class="t"><b>{h}</b><small>{b}</small></span></li>'
                 for h, b in items)
    return f'<div class="pc {kind}"><h3>{head}</h3><ul>{li}</ul></div>'


def s_summary():
    title("Итоги", "Плюсы и недостатки Streamlit")
    html('<div class="grid g2">' + pc_block("plus", "Плюсы", PROS, "+")
         + pc_block("minus", "Недостатки", CONS, "−") + "</div>")
    hint("<b>Вывод:</b> Streamlit идеален для дашбордов, прототипов и демо моделей. "
         "Для больших продуктов с высокой нагрузкой лучше классический веб-стек.")
    st.write("")
    st.button("Перейти к квизу · 5 вопросов", type="primary", on_click=go, args=(len(SLIDES) - 1,))


# ============================================================ НАВИГАЦИЯ
# (раздел, название, функция, минуты, заметка докладчика)
SLIDES = [
    ("Начало", "Web-приложения на базе Streamlit", s_intro, 0.75,
     "Начните с ползунка справа: сам доклад уже работает как приложение на Python."),
    ("Знакомство", "Что такое Streamlit", s_what, 1.0,
     "Покажите соответствие строк кода слева и интерфейса справа. Про области применения — одной фразой."),
    ("Знакомство", "Как устроено приложение", s_how, 1.0,
     "Подвигайте ползунок: счётчик выполнений растёт. Это главная идея — скрипт перезапускается целиком."),
    ("Первые шаги", "Первое приложение", s_first, 0.75,
     "Попросите кого-нибудь назвать имя и введите его."),
    ("Первые шаги", "Виджеты управляют расчётом", s_widgets, 1.0,
     "Смените город и период, включите таблицу. Значение виджета — обычная переменная Python."),
    ("Данные и графики", "Графики", s_charts, 0.75,
     "Переключите вид графика: данные те же, меняется одна команда."),
    ("Состояние и кеш", "Session State", s_state, 0.75,
     "Нажмите обе кнопки по несколько раз. Обычная переменная не растёт выше 1."),
    ("Состояние и кеш", "Кеширование", s_cache, 0.75,
     "Нажмите «Выполнить расчёт» дважды: 0,8 с, затем почти 0."),
    ("Публикация", "Публикация и ограничения", s_deploy, 1.0,
     "Пройдитесь быстро: слева как опубликовать, справа о чём помнить."),
    ("Практика", "Дашборд продаж", s_dashboard, 1.5,
     "Главное демо. Уберите регион, смените период, откройте исходные данные."),
    ("Итоги", "Плюсы и недостатки", s_summary, 0.75,
     "Слева плюсы, справа недостатки, внизу вывод. Затем переход к квизу."),
    ("Квиз", "Квиз · 5 вопросов", quiz_stage, 0.0,
     "Дайте аудитории время отсканировать QR. Нажмите «Старт», а после пяти вопросов обсудите распределение баллов."),
]


def go(i: int) -> None:
    st.query_params["slide"] = str(max(0, min(len(SLIDES) - 1, i)) + 1)


def theme_url(theme: str, index: int) -> str:
    # Смена темы перезагружает страницу. Личный билет и номер слайда остаются в адресе.
    params = {key: st.query_params[key] for key in ("ticket", "presenter") if key in st.query_params}
    params.update(embed="true", embed_options=theme, slide=str(index + 1))
    return "?" + escape(urlencode(params), quote=True)


def enter_presenter(index: int) -> None:
    go(index)
    st.query_params["presenter"] = "1"


def leave_presenter() -> None:
    st.session_state.pop("host_key", None)
    st.query_params.pop("presenter", None)


def main() -> None:
    store = get_store()
    host = is_presenter(store)
    if st.query_params.get("presenter") == "1" and not host:
        presenter_login(store)
        return

    room = store.current_round()
    token = None if host else ensure_participant(store, room)
    watch_round(store, room["id"], room["status"], token)
    joining = st.query_params.get("join") == "1" or st.query_params.get("quiz") == "1"
    if not host and (room["status"] != "waiting" or joining):
        audience_page(store, room, token)
        return

    try:
        requested = int(st.query_params.get("slide", len(SLIDES) if host else 1))
    except ValueError:
        requested = 1
    idx = max(0, min(len(SLIDES) - 1, requested - 1))

    with st.sidebar:
        html(f'<div style="font-size:1.5rem;font-weight:800">streamlit</div>'
             f'<div style="opacity:.75;font-size:.95rem;margin-bottom:1rem">доклад в действии</div>')
        html('<div class="panel-label"><span>Содержание</span></div>')
        sections = list(dict.fromkeys(s[0] for s in SLIDES))
        for n, sec in enumerate(sections, 1):
            first = next(i for i, s in enumerate(SLIDES) if s[0] == sec)
            st.button(f"{n:02d}  {sec}", key=f"sec{n}", on_click=go, args=(first,), width="stretch",
                      type="primary" if SLIDES[idx][0] == sec else "tertiary")
        st.divider()
        html('<div class="panel-label"><span>Тема</span></div><div class="theme-links">'
             f'<a href="{theme_url("light_theme", idx)}" target="_top">Светлая</a>'
             f'<a href="{theme_url("dark_theme", idx)}" target="_top">Тёмная</a></div>')
        st.write("")
        st.toggle("Показывать код", value=True, key="show_code")
        st.toggle("Заметки докладчика", value=False, key="show_notes")
        st.divider()
        if host:
            st.button("Выйти из режима ведущего", on_click=leave_presenter, type="tertiary")
        else:
            st.button("Вход ведущего", on_click=enter_presenter, args=(idx,), type="tertiary")

    section, name, fn, minutes, note = SLIDES[idx]
    html(f'<div class="topbar"><span>Web-приложения на базе Streamlit</span>'
         f'<span><span class="live">● live</span> / python &nbsp; {idx + 1:02d} / {len(SLIDES):02d}</span></div>')
    st.progress((idx + 1) / len(SLIDES))

    if fn is quiz_stage:
        quiz_stage(store, room, host)
    else:
        fn()

    if st.session_state.get("show_notes"):
        with st.expander("Заметка докладчика", expanded=True):
            st.write(note)

    st.write("")
    b1, b2, b3 = st.columns([1, 2, 1])
    b1.button("← Назад", on_click=go, args=(idx - 1,), disabled=idx == 0, width="stretch")
    b2.markdown(f"<div style='text-align:center;opacity:.6;padding-top:.5rem'>{idx + 1:02d} / {len(SLIDES):02d} · "
                f"{section}</div>", unsafe_allow_html=True)
    b3.button("Далее →", on_click=go, args=(idx + 1,), disabled=idx == len(SLIDES) - 1,
              type="primary", width="stretch")


if __name__ == "__main__":
    main()
