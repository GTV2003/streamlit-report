"""Вход ведущего, экран старта, участник и обновляемая общая доска."""

import hashlib
from html import escape
from io import BytesIO
import os
from pathlib import Path

import altair as alt
import pandas as pd
import qrcode
import streamlit as st

from quiz_questions import QUIZ
from quiz_store import QuizError, QuizStore


ACCENT = "#E5483D"


@st.cache_resource(show_spinner=False)
def _store_at(directory: str) -> QuizStore:
    return QuizStore(directory)


def get_store() -> QuizStore:
    directory = os.environ.get("QUIZ_DATA_DIR", str(Path(__file__).parent / "runtime"))
    return _store_at(str(Path(directory).resolve()))


def is_presenter(store: QuizStore) -> bool:
    return store.authenticate(st.session_state.get("host_key", ""))


def presenter_login(store: QuizStore) -> None:
    st.title("Вход ведущего")
    st.caption("Режим ведущего управляет общим стартом и показывает результаты аудитории.")
    with st.form("host_login"):
        key = st.text_input("Код ведущего", type="password", key="host_login_code")
        submitted = st.form_submit_button("Войти", type="primary")
    if submitted:
        if store.authenticate(key):
            token = st.query_params.get("ticket")
            if token:
                store.exclude_presenter(key, token)
                st.query_params.pop("ticket", None)
            st.session_state.host_key = key
            st.query_params.pop("join", None)
            st.query_params.pop("quiz", None)
            st.query_params["presenter"] = "1"
            st.rerun()
        else:
            st.error("Неверный код ведущего.")
    st.link_button("Открыть страницу участника", store.join_url(st.context.url), type="tertiary")


def ensure_participant(store: QuizStore, room: dict) -> str:
    previous = st.session_state.get("live_round")
    token = st.query_params.get("ticket") if previous in (None, room["id"]) else None
    if previous != room["id"] or token != st.session_state.get("live_token"):
        try:
            token = store.connect(room["id"], token)
        except QuizError:
            # Ведущий мог сменить раунд после того, как страница прочитала его состояние.
            if store.current_round()["id"] != room["id"]:
                st.rerun()
            raise
        st.session_state.live_round = room["id"]
        st.session_state.live_token = token
        st.query_params["ticket"] = token
    return st.session_state.live_token


@st.fragment(run_every="2s")
def watch_round(store: QuizStore, observed_id: str, observed_status: str, token: str | None = None) -> None:
    current = store.current_round()
    if current["id"] != observed_id or current["status"] != observed_status:
        st.rerun(scope="app")
    if token:
        store.heartbeat(observed_id, token)


@st.cache_data(show_spinner=False, max_entries=16)
def qr_png(url: str) -> bytes:
    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=10, border=4)
    qr.add_data(url)
    qr.make(fit=True)
    output = BytesIO()
    qr.make_image(fill_color="black", back_color="white").save(output, format="PNG")
    return output.getvalue()


def show_qr(store: QuizStore, width: int = 310) -> None:
    url = store.join_url(st.context.url)
    st.image(qr_png(url), width=width)
    st.code(url, language=None, wrap_lines=True)
    st.link_button("Открыть страницу участника", url)
    if "localhost" in url or "127.0.0.1" in url:
        st.caption("Сейчас QR ведёт на локальный адрес этого компьютера. Для телефонов укажите адрес доступного сервера после подключения домена.")


@st.fragment(run_every="2s")
def lobby_presence(store: QuizStore, host_key: str) -> None:
    board = store.board(host_key)
    left, right = st.columns(2)
    left.metric("Подключились", board["connected"])
    right.metric("На связи сейчас", board["online"])


def host_settings(store: QuizStore, host_key: str) -> None:
    with st.expander("Адрес для QR и управление раундом"):
        with st.form("public_url_settings"):
            url = st.text_input("Адрес приложения", value=store.public_url(st.context.url), placeholder="https://example.ru", key="public_base_url")
            submitted = st.form_submit_button("Обновить QR")
        if submitted:
            try:
                store.set_public_url(host_key, url)
                st.rerun()
            except QuizError as exc:
                st.error(str(exc))
        st.caption("Если телефоны подключаются по другому адресу, укажите его здесь. Общий QR действует и в следующем раунде.")
        st.button("Новый раунд", key="new_live_round", help="Текущий раунд завершится, результаты сохранятся в базе. Участники снова увидят ожидание старта.", on_click=store.new_round, args=(host_key,))


def quiz_stage(store: QuizStore, room: dict, host: bool) -> None:
    if room["status"] == "waiting":
        left, right = st.columns([1.25, 1], gap="large")
        with left:
            st.html('<div class="quiz-stage"><div class="kicker">Пять вопросов по Streamlit</div><h1>Квиз<br><span>начинается!</span></h1></div>')
            st.write("Отсканируйте QR. Когда ведущий нажмёт «Старт», введите ФИО и ответьте на пять вопросов.")
            if host:
                if st.button("Старт", icon=":material/play_arrow:", type="primary", key="live_start", width="stretch"):
                    store.start_round(st.session_state.host_key)
                    st.rerun()
                st.caption("Старт закроет материалы презентации у участников и откроет ввод ФИО. Здесь появится доска результатов.")
                lobby_presence(store, st.session_state.host_key)
            else:
                st.info("Ждём, когда ведущий нажмёт «Старт». Страница переключится автоматически.")
        with right, st.container(border=True):
            show_qr(store)
        if host:
            host_settings(store, st.session_state.host_key)
    elif host:
        if room["status"] == "running":
            st.caption("Участники отвечают на своих устройствах. Доска обновляется каждые 2 секунды.")
            if st.button("Завершить приём ответов", key="live_close", type="secondary"):
                store.close_round(st.session_state.host_key)
                st.rerun()
        else:
            st.success("Приём ответов завершён. Можно обсудить результаты.")
        render_board(store, st.session_state.host_key, room["id"])
        with st.expander("QR для подключения"):
            show_qr(store, width=220)
        host_settings(store, st.session_state.host_key)


def cloud_html(finished: list[dict]) -> str:
    if not finished:
        return '<div class="finish-cloud empty-cloud"><div><strong>Первое имя появится здесь</strong><p>когда участник ответит на все пять вопросов</p></div></div>'
    tags = []
    for person in finished:
        digest = hashlib.sha256(person["name"].encode("utf-8")).digest()
        size = 18 + digest[0] % 15
        color = f"color-mix(in srgb, currentColor {45 + digest[1] % 55}%, {ACCENT})"
        tags.append(f'<span class="cloud-name" style="font-size:{size}px;color:{color}">{escape(person["name"])}</span>')
    return '<div class="finish-cloud">' + "".join(tags) + '</div>'


def roster_frame(people: list[dict]) -> pd.DataFrame:
    return pd.DataFrame([
        {"ФИО": person["name"], "Прогресс": f"{person['answered']} / {len(QUIZ)}", "Статус": "Завершил" if person["completed_at"] is not None else "Отвечает", "Баллы": f"{person['score']} / {len(QUIZ)}" if person["score"] is not None else "—"}
        for person in people
    ], columns=["ФИО", "Прогресс", "Статус", "Баллы"])


@st.fragment(run_every="2s")
def render_board(store: QuizStore, host_key: str, observed_id: str) -> None:
    board = store.board(host_key)
    if board["round"]["id"] != observed_id:
        st.rerun(scope="app")
    people, finished = board["people"], board["finished"]
    a, b, c, d = st.columns(4)
    a.metric("Подключились", board["connected"])
    b.metric("Указали ФИО", len(people))
    c.metric("Завершили", len(finished))
    average = sum(person["score"] for person in finished) / len(finished) if finished else None
    d.metric("Средний балл", f"{average:.1f} / 5" if average is not None else "—")
    left, right = st.columns([1.25, 1], gap="large")
    with left:
        st.subheader("Уже финишировали")
        st.html(cloud_html(finished))
        st.caption("Облако заполняется по мере завершения. Размер имён декоративный.")
    with right:
        st.subheader("Распределение баллов")
        scores = pd.DataFrame({"Балл": list(range(6)), "Участники": board["distribution"]})
        base = alt.Chart(scores).encode(
            x=alt.X("Балл:O", title="Правильных ответов из 5"),
            y=alt.Y("Участники:Q", title="Участников", scale=alt.Scale(domainMin=0), axis=alt.Axis(tickMinStep=1)),
            tooltip=["Балл:O", "Участники:Q"],
        )
        chart = base.mark_bar(color=ACCENT, cornerRadiusTopLeft=4, cornerRadiusTopRight=4)
        st.altair_chart(chart.properties(height=235).configure_view(stroke=None), width="stretch")
        st.caption("Учитываются только участники, завершившие все пять вопросов.")
    st.subheader("Участники")
    if people:
        st.dataframe(roster_frame(people), hide_index=True, width="stretch", height=min(390, 40 + 35 * len(people)))
    else:
        st.info("Здесь появятся ФИО участников после регистрации.")
    st.caption(f"Сейчас на связи: {board['online']}. Ещё без ФИО: {board['anonymous']}.")
    with st.expander("Правильность по вопросам и выгрузка"):
        stats = pd.DataFrame([{"Вопрос": str(item["question"]), "Верно, %": round(100 * item["correct"] / item["total"], 1) if item["total"] else 0, "Верных ответов": item["correct"], "Завершивших": item["total"]} for item in board["questions"]])
        chart = alt.Chart(stats).mark_bar(color=ACCENT).encode(x=alt.X("Вопрос:O", title="Вопрос"), y=alt.Y("Верно, %:Q", scale=alt.Scale(domain=[0, 100])), tooltip=["Вопрос", "Верно, %", "Верных ответов", "Завершивших"]).properties(height=180)
        st.altair_chart(chart.configure_view(stroke=None), width="stretch")
        st.download_button("Скачать результаты CSV", roster_frame(people).to_csv(index=False).encode("utf-8-sig"), file_name="quiz_results.csv", mime="text/csv", key="live_export", on_click="ignore")
    if board["round"]["status"] == "closed":
        answer_review()


def answer_review(person: dict | None = None) -> None:
    with st.expander("Ответы и обсуждение"):
        for i, question in enumerate(QUIZ):
            answer = question["options"][question["answer"]]
            st.markdown(f"**{i + 1}. {question['question']}**")
            st.write(f"Правильный ответ: {answer}.")
            if person is not None and i in person["answers"]:
                st.caption("Ваш ответ: " + question["options"][person["answers"][i]])
            st.caption(question["explanation"])


def audience_page(store: QuizStore, room: dict, token: str) -> None:
    st.html('<style>[data-testid="stSidebar"], [data-testid="stSidebarCollapsedControl"] {display:none!important;} [data-testid="stMainBlockContainer"] {max-width:920px;}</style>')
    st.html('<div class="topbar"><span class="label">Streamlit / квиз</span><span class="live"><i></i> ВЫ НА СВЯЗИ</span></div>')
    if room["status"] == "waiting":
        st.title("Скоро начинаем")
        st.write("Пять вопросов по Streamlit. После старта ведущего здесь появится ввод ФИО.")
        st.info("Оставьте эту страницу открытой. Переход произойдёт автоматически.")
        if st.button("Посмотреть презентацию", key="return_to_deck"):
            st.query_params.pop("join", None)
            st.query_params.pop("quiz", None)
            st.query_params["slide"] = "1"
            st.rerun()
        return
    person = store.participant(room["id"], token)
    if person["completed_at"] is not None:
        st.html('<div class="kicker">Ответы сохранены</div>')
        st.title("Готово. Вы в облаке!")
        st.write(person["name"])
        st.metric("Ваш результат", f"{person['score']} / {len(QUIZ)}")
        st.success("Ваше имя и результат уже появились на общей доске.")
        if room["status"] == "closed":
            answer_review(person)
        else:
            st.caption("Разбор ответов откроется после завершения приёма ответов ведущим.")
        return
    if room["status"] == "closed":
        st.title("Приём ответов завершён")
        st.write(f"Сохранено ответов: {len(person['answers'])} из {len(QUIZ)}.")
        st.caption("Незавершённые попытки отображаются у ведущего, но не входят в распределение баллов.")
        answer_review(person)
        return
    if not person["name"]:
        st.html('<div class="kicker">Квиз начался</div>')
        st.title("Представьтесь")
        with st.form("participant_name_form"):
            name = st.text_input("Ваше ФИО", placeholder="Иванов Иван Иванович", max_chars=120, key="participant_name")
            st.caption("Фамилия, имя и отчество, если оно есть. ФИО, прогресс и результат появятся на общем экране доклада.")
            submitted = st.form_submit_button("Начать отвечать", type="primary", width="stretch")
        if submitted:
            try:
                store.register_name(room["id"], token, name)
                st.rerun()
            except QuizError as exc:
                st.error(str(exc))
        return
    index = len(person["answers"])
    question = QUIZ[index]
    st.caption(person["name"])
    st.progress(index / len(QUIZ), text=f"Вопрос {index + 1} из {len(QUIZ)}")
    st.title(question["question"])
    with st.container(key="quiz_options"):
        selected = st.radio("Варианты ответа", [0, 1, 2], index=None, format_func=lambda i: f"{'ABC'[i]}   {question['options'][i]}", key=f"live_answer_{room['id']}_{index}", label_visibility="collapsed")
    label = "Завершить квиз" if index == len(QUIZ) - 1 else "Сохранить и дальше"
    if st.button(label, type="primary", key=f"save_live_answer_{index}", disabled=selected is None, width="stretch"):
        try:
            store.save_answer(room["id"], token, index, selected)
            st.rerun()
        except QuizError as exc:
            st.error(str(exc))
    st.caption("Ответ фиксируется после нажатия кнопки. Результат появится после пятого вопроса.")
