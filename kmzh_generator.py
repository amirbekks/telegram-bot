"""Генератор ҚМЖ (қысқа мерзімді жоспар) на казахском языке.

Глубина зависит от тарифа:
  basic    — каркас ҚМЖ (шапка + ход урока + рефлексия)
  standard — + цели, критерии оценивания, дифференциация, ресурсы
  premium  — + межпредметная связь, план слайдов, доп. задания

Движок шаблонный (работает офлайн, без внешних API). Точкой расширения
для ИИ-генерации является функция build_sections(): её вывод можно заменить
ответом LLM, сохранив формат рендера (текст / .docx).
"""

from datetime import datetime

from curriculum import SUBJECTS, get_sections

LINE = "━━━━━━━━━━━━━━━━━━━━━"


def _find_section(subject: str, grade: int, topic: str) -> str:
    """Пытается найти раздел (ұзақ мерзімді жоспар бөлімі) по теме."""
    for section, topics in get_sections(subject, grade).items():
        if topic in topics:
            return section
    # если тема введена вручную — берём первый раздел класса как ориентир
    sections = list(get_sections(subject, grade).keys())
    return sections[0] if sections else "—"


def _lesson_flow(topic: str, depth: str) -> list:
    """Ход урока: список этапов (кезең, уақыт, педагог, оқушы, ресурс)."""
    middle_teacher = (
        f"«{topic}» тақырыбы бойынша жаңа материалды таныстырады. "
        "Негізгі ұғымдарды тақтаға жазады, слайд/карта/иллюстрация көрсетеді."
    )
    middle_student = (
        "Мұғалімді тыңдайды, дәптерге негізгі ұғымдарды жазады, "
        "сұрақтарға жауап береді."
    )
    if depth in ("standard", "premium"):
        middle_teacher += (
            "\n   Топтық тапсырма береді: мәтінмен/картамен жұмыс, "
            "«Венн диаграммасы» немесе «Кластер» құрастыру."
        )
        middle_student += (
            "\n   Топта жұмыс істейді, тапсырманы орындайды, нәтижені қорғайды."
        )

    return [
        {
            "stage": "Басы",
            "time": "0–5 мин",
            "teacher": (
                "Оқушылармен амандасады, сабаққа дайындығын тексереді. "
                "Психологиялық ахуал қалыптастырады. Үй тапсырмасын қайталайды "
                "және жаңа тақырыпқа қызығушылық ояту үшін проблемалық сұрақ қояды."
            ),
            "student": "Амандасады, сабаққа дайындалады, сұраққа болжам айтады.",
            "assess": "Ауызша мадақтау",
            "res": "Презентация, сұрақтар",
        },
        {
            "stage": "Ортасы",
            "time": "5–35 мин",
            "teacher": middle_teacher,
            "student": middle_student,
            "assess": "Қалыптастырушы бағалау, «Бас бармақ» әдісі",
            "res": "Оқулық, карта, слайдтар, тарату материалы",
        },
        {
            "stage": "Соңы",
            "time": "35–40 мин",
            "teacher": (
                "Сабақты қорытындылайды, оқушылардың меңгеру деңгейін бағалайды. "
                "Үй тапсырмасын береді және рефлексия жүргізеді."
            ),
            "student": "Қорытынды жасайды, рефлексия парағын толтырады.",
            "assess": "«Бағдаршам» рефлексиясы",
            "res": "Стикерлер, рефлексия парағы",
        },
    ]


def _slides(topic: str) -> list:
    """План слайдов презентации (только Премиум)."""
    return [
        f"1-слайд. Тақырып: «{topic}» (сынып, пән, күні)",
        "2-слайд. Сабақтың мақсаты мен күтілетін нәтиже",
        "3-слайд. Өмірмен байланыс: проблемалық сұрақ / қызықты дерек",
        f"4-слайд. Негізгі ұғымдар мен терминдер («{topic}» бойынша)",
        "5-слайд. Жаңа материал (1-бөлім): мәтін + иллюстрация/карта",
        "6-слайд. Жаңа материал (2-бөлім): хронология / кесте",
        "7-слайд. Топтық тапсырма (нұсқаулық)",
        "8-слайд. Бекіту сұрақтары / тест",
        "9-слайд. Рефлексия («Білдім – үйрендім – білгім келеді»)",
        "10-слайд. Үй тапсырмасы және дереккөздер",
    ]


def build_sections(subject: str, grade: int, topic: str, depth: str) -> dict:
    """Собирает структуру ҚМЖ в виде словаря (единый источник для рендера)."""
    section = _find_section(subject, grade, topic)
    data = {
        "subject": SUBJECTS.get(subject, subject),
        "grade": grade,
        "topic": topic,
        "section": section,
        "date": datetime.now().strftime("%d.%m.%Y"),
        "flow": _lesson_flow(topic, depth),
        "objectives": (
            f"«{topic}» тақырыбы бойынша негізгі оқиғалар мен ұғымдарды "
            "түсіндіру, себеп-салдарлық байланыстарды анықтау."
        ),
        "goal": (
            f"Барлық оқушы «{topic}» тақырыбының мазмұнын сипаттай алады; "
            "көпшілігі негізгі ұғымдарды салыстырады; кейбірі өз көзқарасын "
            "дәлелдеп баяндайды."
        ),
    }

    if depth in ("standard", "premium"):
        data["criteria"] = [
            "Тақырып бойынша негізгі фактілер мен ұғымдарды атайды",
            "Тарихи оқиғаларды хронологиялық ретпен орналастырады",
            "Себеп-салдарлық байланысты түсіндіреді",
            "Өз пікірін дәлелдермен негіздейді",
        ]
        data["values"] = (
            "«Мәңгілік Ел» құндылықтары: Отансүйгіштік, тарихи сана, "
            "ынтымақтастық пен өзара құрмет."
        )
        data["differentiation"] = (
            "Қолдауды қажет ететін оқушыларға — тірек сызбалар мен дайын "
            "ұғымдар тізімі беріледі. Қабілетті оқушыларға — қосымша "
            "талдау сұрақтары мен шығармашылық тапсырма ұсынылады."
        )
        data["assessment"] = (
            "Қалыптастырушы бағалау: ауызша сұрау, топтық жұмысты өзара "
            "бағалау, сабақ соңында шағын тест немесе кері байланыс."
        )
        data["resources"] = (
            "Оқулық, атлас/карта, интерактивті тақта, презентация, "
            "тарату материалы, бейнеүзінді."
        )

    if depth == "premium":
        data["cross"] = (
            "Пәнаралық байланыс: география (тарихи карта), әдебиет (дереккөз "
            "мәтіні), өзін-өзі тану (құндылықтар), қазақ тілі (терминдер)."
        )
        data["ict"] = "АКТ дағдылары: презентация, интерактивті карта, QR-тест, онлайн-сауалнама."
        data["slides"] = _slides(topic)
        data["extra"] = [
            "Шығармашылық тапсырма: «Егер сен сол дәуірде өмір сүрсең...» эссесі",
            "Хронологиялық кесте толтыру",
            "«Ыстық орындық» рөлдік ойыны",
            "Тарихи тұлғаға сұхбат жазу",
        ]

    return data


# ---------- Рендер в текст (для Telegram) ----------

def render_text(data: dict, depth: str) -> str:
    p = []
    p.append(f"📘 <b>ҚЫСҚА МЕРЗІМДІ ЖОСПАР (ҚМЖ)</b>\n{LINE}")
    p.append(f"<b>Пән:</b> {data['subject']}")
    p.append(f"<b>Сынып:</b> {data['grade']}-сынып")
    p.append(f"<b>Бөлім:</b> {data['section']}")
    p.append(f"<b>Сабақтың тақырыбы:</b> {data['topic']}")
    p.append(f"<b>Күні:</b> {data['date']}    <b>Мұғалім:</b> _______")
    p.append("")
    p.append(f"<b>🎯 Оқу мақсаттары:</b>\n{data['objectives']}")
    p.append(f"<b>🎯 Сабақтың мақсаты:</b>\n{data['goal']}")

    if "criteria" in data:
        crit = "\n".join(f"• {c}" for c in data["criteria"])
        p.append(f"<b>✅ Бағалау критерийлері:</b>\n{crit}")
    if "values" in data:
        p.append(f"<b>💎 Құндылықтарды дарыту:</b>\n{data['values']}")
    if "cross" in data:
        p.append(f"<b>🔗 {data['cross']}</b>")
    if "ict" in data:
        p.append(f"<b>💻 {data['ict']}</b>")

    p.append(f"\n<b>📋 САБАҚТЫҢ БАРЫСЫ</b>\n{LINE}")
    for st in data["flow"]:
        p.append(
            f"<b>▫️ {st['stage']} ({st['time']})</b>\n"
            f"👨‍🏫 <i>Педагог:</i> {st['teacher']}\n"
            f"👧 <i>Оқушы:</i> {st['student']}\n"
            f"📝 <i>Бағалау:</i> {st['assess']}\n"
            f"📎 <i>Ресурс:</i> {st['res']}"
        )

    if "differentiation" in data:
        p.append(f"\n<b>🧩 Саралау:</b>\n{data['differentiation']}")
    if "assessment" in data:
        p.append(f"<b>📊 Бағалау:</b>\n{data['assessment']}")
    if "resources" in data:
        p.append(f"<b>📎 Ресурстар:</b>\n{data['resources']}")

    if "slides" in data:
        slides = "\n".join(data["slides"])
        p.append(f"\n<b>🖥 ПРЕЗЕНТАЦИЯ СЛАЙДТАРЫ</b>\n{LINE}\n{slides}")
    if "extra" in data:
        extra = "\n".join(f"• {e}" for e in data["extra"])
        p.append(f"\n<b>✨ Қосымша тапсырмалар:</b>\n{extra}")

    p.append(
        f"\n<b>🔄 Рефлексия:</b>\n«Білдім – Үйрендім – Білгім келеді» әдісі "
        "арқылы оқушылар сабақтан алған әсерін жазады."
    )
    p.append(
        "\n<i>Денсаулық және қауіпсіздік техникасы сақталады.</i>"
    )
    return "\n".join(p)


# ---------- Рендер в .docx ----------

def render_docx(data: dict, path: str):
    """Сохраняет ҚМЖ в .docx. Требует python-docx."""
    from docx import Document
    from docx.shared import Pt
    from docx.enum.text import WD_ALIGN_PARAGRAPH

    doc = Document()

    title = doc.add_heading("Қысқа мерзімді жоспар (ҚМЖ)", level=0)
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER

    def field(label, value):
        pr = doc.add_paragraph()
        run = pr.add_run(f"{label} ")
        run.bold = True
        pr.add_run(str(value))

    field("Пән:", data["subject"])
    field("Сынып:", f"{data['grade']}-сынып")
    field("Бөлім:", data["section"])
    field("Сабақтың тақырыбы:", data["topic"])
    field("Күні:", data["date"])
    field("Мұғалімнің аты-жөні:", "____________________")

    doc.add_heading("Оқу мақсаттары", level=2)
    doc.add_paragraph(data["objectives"])
    doc.add_heading("Сабақтың мақсаты", level=2)
    doc.add_paragraph(data["goal"])

    if "criteria" in data:
        doc.add_heading("Бағалау критерийлері", level=2)
        for c in data["criteria"]:
            doc.add_paragraph(c, style="List Bullet")
    if "values" in data:
        doc.add_heading("Құндылықтарды дарыту", level=2)
        doc.add_paragraph(data["values"])
    if "cross" in data:
        doc.add_paragraph(data["cross"])
    if "ict" in data:
        doc.add_paragraph(data["ict"])

    doc.add_heading("Сабақтың барысы", level=1)
    table = doc.add_table(rows=1, cols=5)
    table.style = "Table Grid"
    hdr = table.rows[0].cells
    for i, h in enumerate(["Кезең / Уақыт", "Педагогтің әрекеті", "Оқушының әрекеті", "Бағалау", "Ресурстар"]):
        hdr[i].text = h
        hdr[i].paragraphs[0].runs[0].bold = True
    for st in data["flow"]:
        row = table.add_row().cells
        row[0].text = f"{st['stage']}\n{st['time']}"
        row[1].text = st["teacher"]
        row[2].text = st["student"]
        row[3].text = st["assess"]
        row[4].text = st["res"]

    if "differentiation" in data:
        doc.add_heading("Саралау", level=2)
        doc.add_paragraph(data["differentiation"])
    if "assessment" in data:
        doc.add_heading("Бағалау", level=2)
        doc.add_paragraph(data["assessment"])
    if "resources" in data:
        doc.add_heading("Ресурстар", level=2)
        doc.add_paragraph(data["resources"])

    if "slides" in data:
        doc.add_heading("Презентация слайдтарының жоспары", level=1)
        for s in data["slides"]:
            doc.add_paragraph(s, style="List Bullet")
    if "extra" in data:
        doc.add_heading("Қосымша тапсырмалар", level=2)
        for e in data["extra"]:
            doc.add_paragraph(e, style="List Bullet")

    doc.add_heading("Рефлексия", level=2)
    doc.add_paragraph(
        "«Білдім – Үйрендім – Білгім келеді» әдісі арқылы оқушылар сабақтан "
        "алған әсерін жазады."
    )
    doc.add_paragraph("Денсаулық және қауіпсіздік техникасы сақталады.")

    for p in doc.paragraphs:
        for run in p.runs:
            run.font.size = run.font.size or Pt(11)

    doc.save(path)
    return path


def generate(subject: str, grade: int, topic: str, depth: str) -> dict:
    """Главная точка входа: возвращает {'data': ..., 'text': ...}."""
    data = build_sections(subject, grade, topic, depth)
    return {"data": data, "text": render_text(data, depth)}
