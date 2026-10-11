"""Simple text math: word counts, words per minute, filler words, and quote checking.

No AI here, so it's fast, free, and easy to test (BUILD_PROMPT.md section 8.8).
"""
import re

STRONG_FILLERS = re.compile(r"\b(u+m+|u+h+|e+r+|a+h+|hm+)\b", re.IGNORECASE)
SOFT_FILLERS = re.compile(r"\b(like|you know|basically|literally|i mean|kind of|sort of)\b", re.IGNORECASE)
EVIDENCE_HINTS = re.compile(
    r"\d|percent|%|for example|for instance|according to|study|studies|report|data|survey|research|"
    r"in \d{4}|million|billion|thousand|statistic", re.IGNORECASE)


def words(text):
    return re.findall(r"[A-Za-zÀ-ÿ0-9']+", text or "")


def word_count(text):
    return len(words(text))


def words_per_minute(text, speaking_seconds):
    if not speaking_seconds or speaking_seconds <= 0:
        return 0
    return round(word_count(text) / (speaking_seconds / 60))


def filler_counts(text):
    return {"strong": len(STRONG_FILLERS.findall(text or "")), "soft": len(SOFT_FILLERS.findall(text or ""))}


def fillers_per_minute(text, speaking_seconds):
    if not speaking_seconds or speaking_seconds <= 0:
        return 0.0
    c = filler_counts(text)
    return round((c["strong"] + c["soft"]) / (speaking_seconds / 60), 1)


def looks_like_evidence(text):
    return bool(EVIDENCE_HINTS.search(text or ""))


def sentences(text):
    parts = re.split(r"(?<=[.!?])\s+|\n+", (text or "").strip())
    return [p.strip() for p in parts if p.strip()]


def _norm(text):
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s']", " ", (text or "").lower())).strip()


def quote_appears(quote, student_texts):
    """True if the quote is really in what the student said (ignoring case, punctuation, extra spaces)."""
    q = _norm(quote)
    return bool(q) and any(q in _norm(t) for t in student_texts)


def best_overlap_sentence(quote, student_texts):
    """The student sentence that shares the most words with the quote (used when the AI misquotes)."""
    target = set(_norm(quote).split())
    best, best_score = "", -1
    for text in student_texts:
        for s in sentences(text):
            score = len(target & set(_norm(s).split()))
            if score > best_score or (score == best_score and len(s) > len(best)):
                best, best_score = s, score
    return best


def verify_quote(quote, student_texts):
    if quote_appears(quote, student_texts):
        return quote.strip()
    return best_overlap_sentence(quote, student_texts) or (student_texts[0].strip() if student_texts else "")


def limit_words(text, n):
    w = (text or "").split()
    return " ".join(w[:n]) + ("…" if len(w) > n else "")
