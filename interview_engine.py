# interview_engine.py

QUESTION_BANK = {
    "python": [
        "What is Python and where is it used?",
        "Explain list vs tuple in Python.",
        "What is a dictionary?",
        "What are functions in Python?",
        "Explain OOP concepts in Python."
    ],

    "flask": [
        "What is Flask?",
        "Explain routing in Flask.",
        "What is Jinja2?",
        "Difference between Flask and Django.",
        "How does Flask handle requests?"
    ],

    "sql": [
        "What is SQL?",
        "What is a primary key?",
        "Difference between WHERE and HAVING.",
        "Explain JOINs.",
        "What is normalization?"
    ],

    "django": [
        "What is Django?",
        "Explain MTV architecture.",
        "What are models?",
        "What is ORM?",
        "Difference between Flask and Django."
    ],

    "machine learning": [
        "What is Machine Learning?",
        "Difference between supervised and unsupervised learning.",
        "What is overfitting?",
        "Explain train-test split."
    ]
}


def generate_questions(skills, max_questions=5):
    questions = []

    for skill in skills:
        if skill in QUESTION_BANK:
            questions.extend(QUESTION_BANK[skill])

    unique_questions = list(dict.fromkeys(questions))
    return unique_questions[:max_questions]


def evaluate_answers(questions, answers):
    total_score = 0
    weak_areas = []

    for q, a in zip(questions, answers):
        q_words = q.lower().split()
        a_text = a.lower()

        # remove very common words
        ignore = ["what", "is", "the", "explain", "difference", "between", "and"]
        keywords = [w for w in q_words if w not in ignore]

        relevance_score = 0
        for kw in keywords:
            if kw in a_text:
                relevance_score += 1

        length_score = len(a.strip())

        question_score = 0

        # relevance based scoring
        if relevance_score >= 2:
            question_score += 10
        elif relevance_score == 1:
            question_score += 5

        # length based scoring
        if length_score >= 40:
            question_score += 10
        elif length_score >= 20:
            question_score += 5

        if question_score < 10:
            weak_areas.append(q)

        total_score += question_score

    # normalize score to 100
    max_score = len(questions) * 20
    final_score = int((total_score / max_score) * 100)

    readiness = "Ready" if final_score >= 60 else "Needs Improvement"

    return final_score, weak_areas, readiness