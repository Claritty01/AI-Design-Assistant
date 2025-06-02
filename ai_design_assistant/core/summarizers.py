from __future__ import annotations

import nltk
from typing import List
from sumy.parsers.plaintext import PlaintextParser
from sumy.nlp.tokenizers import Tokenizer
from sumy.summarizers.text_rank import TextRankSummarizer

# Максимум слов в итоговом заголовке
_MAX_WORDS = 10


def _ensure_punkt() -> None:
    """
    Проверяем оба варианта токенизатора:
      • старый — «punkt»
      • новый — «punkt_tab» (начиная с nltk-3.8).
    Докачаем только те, которых нет.
    """
    for res in ("punkt", "punkt_tab"):          # порядок важен!
        try:
            nltk.data.find(f"tokenizers/{res}")
        except LookupError:
            nltk.download(res, quiet=True)


def textrank_title(sentences: List[str]) -> str:
    """
    Принимает список строк (обычно 1–2 первых пользовательских реплики)
    и возвращает короткий (до 10 слов) заголовок диалога.
    """
    _ensure_punkt()  # ← важная строка

    text = "\n".join(sentences)
    parser = PlaintextParser.from_string(text, Tokenizer("russian"))
    summarizer = TextRankSummarizer()

    # одной фразы достаточно — возьмём первую
    summary_sentences = summarizer(parser.document, sentences_count=1)
    summary = str(summary_sentences[0]).strip()

    # ограничиваем длину
    words = summary.split()
    if len(words) > _MAX_WORDS:
        summary = " ".join(words[:_MAX_WORDS])

    return summary
