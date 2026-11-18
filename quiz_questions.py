"""Пять вопросов из исходной презентации группы."""

QUIZ = [
    {
        "question": "На каком языке обычно пишут Streamlit-приложения?",
        "options": ["Python", "Java", "C++"],
        "answer": 0,
        "explanation": "Интерфейс и обработку данных в Streamlit описывают на Python. Библиотека создаёт веб-интерфейс по этому коду.",
    },
    {
        "question": "Как запускают файл app.py?",
        "options": ["python server.py", "streamlit run app.py", "npm start"],
        "answer": 1,
        "explanation": "streamlit run app.py запускает сервер Streamlit. Эквивалентная команда: python -m streamlit run app.py.",
    },
    {
        "question": "Какая команда создаёт ползунок?",
        "options": ["st.slider()", "st.title()", "st.write()"],
        "answer": 0,
        "explanation": "st.slider() показывает ползунок и возвращает выбранное значение в Python.",
    },
    {
        "question": "Зачем нужен st.session_state?",
        "options": ["Установить библиотеку", "Создать HTML-файл", "Сохранить состояние сессии"],
        "answer": 2,
        "explanation": "Session State сохраняет значения между повторными выполнениями скрипта внутри пользовательской сессии.",
    },
    {
        "question": "Что делает @st.cache_data?",
        "options": ["Кеширует результат функции", "Меняет оформление", "Публикует приложение"],
        "answer": 0,
        "explanation": "Декоратор сохраняет результат функции. При тех же аргументах и коде функции Streamlit может вернуть его из кеша.",
    },
]
