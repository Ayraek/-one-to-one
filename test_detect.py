from utils import detect_gpt_phrases

# СТАРЫЕ ТЕСТЫ
def test_detect_gpt_phrase():
    text = "Таким образом можно охарактеризовать ключевые моменты"
    assert detect_gpt_phrases(text) == True

def test_no_gpt_phrase():
    text = "Я думаю, продукт нужно улучшить с помощью опроса пользователей"
    assert detect_gpt_phrases(text) == False

# НОВЫЕ ТЕСТЫ
def test_detect_gpt_phrases_detects_gpt_like():
    text = "Данный подход позволяет эффективно решать задачи"
    assert detect_gpt_phrases(text) is True

def test_detect_gpt_phrases_skips_human_text():
    text = "Я думаю, это можно улучшить с помощью простой таблицы"
    assert detect_gpt_phrases(text) is False
