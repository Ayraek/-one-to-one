from utils import detect_gpt_phrases

def test_detect_gpt_phrase():
    text = "Таким образом можно охарактеризовать ключевые моменты"
    assert detect_gpt_phrases(text) == True

def test_no_gpt_phrase():
    text = "Я думаю, продукт нужно улучшить с помощью опроса пользователей"
    assert detect_gpt_phrases(text) == False
