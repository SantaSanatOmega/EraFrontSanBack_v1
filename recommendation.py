"""
Система рекомендаций на основе TF-IDF + Cosine Similarity
"""

import json
from typing import List, Dict, Any
from collections import Counter
import math


def load_programs(filepath: str = "programs.json") -> List[Dict[str, Any]]:
    """Загружает программы из JSON файла"""
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("programs", [])


def build_user_profile(answers: Dict[str, str]) -> List[str]:
    """
    Преобразует ответы пользователя в список тегов.
    
    Маппинг ответов на теги для алгоритма:
    - mood: настроение → активный/расслабленный
    - budget: бюджет → низкий_бюджет/средний_бюджет/высокий_бюджет
    - company: компания → один/пара/компания
    - time: время → утро/день/вечер/ночь
    - location: локация → в_помещении/на_улице
    - interests: интересы → спорт/творчество/еда/музыка/природа и т.д.
    """
    tags = []
    
    # Настроение
    mood_map = {
        "active": "активный",
        "relaxed": "расслабленный",
        "активный": "активный",
        "расслабленный": "расслабленный"
    }
    if answers.get("mood"):
        tags.append(mood_map.get(answers["mood"], answers["mood"]))
    
    # Бюджет
    budget_map = {
        "low": "низкий_бюджет",
        "medium": "средний_бюджет",
        "high": "высокий_бюджет",
        "низкий": "низкий_бюджет",
        "средний": "средний_бюджет",
        "высокий": "высокий_бюджет"
    }
    if answers.get("budget"):
        tags.append(budget_map.get(answers["budget"], answers["budget"]))
    
    # Компания
    company_map = {
        "alone": "один",
        "couple": "пара",
        "friends": "компания",
        "один": "один",
        "пара": "пара",
        "компания": "компания"
    }
    if answers.get("company"):
        tags.append(company_map.get(answers["company"], answers["company"]))
    
    # Время суток
    time_map = {
        "morning": "утро",
        "day": "день",
        "evening": "вечер",
        "night": "ночь",
        "утро": "утро",
        "день": "день",
        "вечер": "вечер",
        "ночь": "ночь"
    }
    if answers.get("time"):
        tags.append(time_map.get(answers["time"], answers["time"]))
    
    # Локация
    location_map = {
        "indoor": "в_помещении",
        "outdoor": "на_улице",
        "в_помещении": "в_помещении",
        "на_улице": "на_улице"
    }
    if answers.get("location"):
        tags.append(location_map.get(answers["location"], answers["location"]))
    
    # Интересы (может быть списком)
    interests = answers.get("interests", [])
    if isinstance(interests, str):
        interests = [interests]
    
    interest_map = {
        "sport": "спорт",
        "creative": "творчество",
        "food": "еда",
        "music": "музыка",
        "nature": "природа",
        "extreme": "экстрим",
        "romance": "романтика",
        "games": "игры",
        "spa": "спа",
        "movies": "кино"
    }
    for interest in interests:
        tags.append(interest_map.get(interest, interest))
    
    return tags


def cosine_similarity(vec1: Dict[str, float], vec2: Dict[str, float]) -> float:
    """Вычисляет косинусное сходство между двумя векторами"""
    # Находим общие ключи
    common_keys = set(vec1.keys()) & set(vec2.keys())
    
    if not common_keys:
        return 0.0
    
    # Скалярное произведение
    dot_product = sum(vec1[k] * vec2[k] for k in common_keys)
    
    # Нормы векторов
    norm1 = math.sqrt(sum(v ** 2 for v in vec1.values()))
    norm2 = math.sqrt(sum(v ** 2 for v in vec2.values()))
    
    if norm1 == 0 or norm2 == 0:
        return 0.0
    
    return dot_product / (norm1 * norm2)


def tags_to_vector(tags: List[str]) -> Dict[str, float]:
    """Преобразует список тегов в вектор (TF — Term Frequency)"""
    counter = Counter(tags)
    total = len(tags) if tags else 1
    return {tag: count / total for tag, count in counter.items()}


def build_idf(programs: List[Dict[str, Any]]) -> Dict[str, float]:
    """Вычисляет IDF (Inverse Document Frequency) для всех тегов"""
    num_programs = len(programs)
    tag_doc_count = Counter()
    
    for program in programs:
        unique_tags = set(program.get("tags", []))
        for tag in unique_tags:
            tag_doc_count[tag] += 1
    
    # IDF = log(N / df)
    idf = {}
    for tag, count in tag_doc_count.items():
        idf[tag] = math.log(num_programs / count) + 1  # +1 для сглаживания
    
    return idf


def apply_tfidf(tf_vector: Dict[str, float], idf: Dict[str, float]) -> Dict[str, float]:
    """Применяет TF-IDF к вектору"""
    return {tag: tf * idf.get(tag, 1.0) for tag, tf in tf_vector.items()}


def recommend(
    user_answers: Dict[str, str], 
    programs: List[Dict[str, Any]] = None,
    top_n: int = 3
) -> List[Dict[str, Any]]:
    """
    Основная функция рекомендаций.
    Возвращает top_n программ, отсортированных по релевантности.
    """
    if programs is None:
        programs = load_programs()
    
    # Строим профиль пользователя
    user_tags = build_user_profile(user_answers)
    
    if not user_tags:
        # Если нет тегов — возвращаем первые N программ
        return programs[:top_n]
    
    # Вычисляем IDF
    idf = build_idf(programs)
    
    # TF-IDF вектор пользователя
    user_tf = tags_to_vector(user_tags)
    user_tfidf = apply_tfidf(user_tf, idf)
    
    # Вычисляем сходство для каждой программы
    scored_programs = []
    for program in programs:
        if not program.get("visible", True):
            continue
            
        program_tags = program.get("tags", [])
        program_tf = tags_to_vector(program_tags)
        program_tfidf = apply_tfidf(program_tf, idf)
        
        score = cosine_similarity(user_tfidf, program_tfidf)
        scored_programs.append((score, program))
    
    # Сортируем по убыванию score
    scored_programs.sort(key=lambda x: x[0], reverse=True)
    
    # Возвращаем top_n программ (без score)
    result = []
    for score, program in scored_programs[:top_n]:
        result.append({
            "id": program["id"],
            "name": program["name"],
            "details": program["details"],
            "video_url": program["video_url"],
            "photo_url": program["photo_url"],
            "visible": program["visible"],
            "score": round(score, 3)  # Для отладки
        })
    
    return result


# Для тестирования
if __name__ == "__main__":
    test_answers = {
        "mood": "active",
        "budget": "medium",
        "company": "friends",
        "time": "evening",
        "location": "indoor"
    }
    
    results = recommend(test_answers, top_n=5)
    
    print("🎯 Рекомендации для:", test_answers)
    print("-" * 50)
    
    for i, program in enumerate(results, 1):
        print(f"{i}. {program['name']} (score: {program['score']})")
        print(f"   {program['details'][:80]}...")
        print()
