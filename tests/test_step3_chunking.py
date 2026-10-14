import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.ingestion.chunker import TextChunker


def test_sentence_splitting_all_languages():
    # 1. English
    en_text = "Dr. Watson observed that 3.14 was the ratio. He visited the U.S. embassy! Was he welcomed? Absolutely..."
    en_sents = TextChunker.split_sentences(en_text)
    assert len(en_sents) == 4, f"English expected 4 sentences, got {len(en_sents)}: {en_sents}"
    assert "3.14" in en_sents[0]
    assert "Dr. Watson" in en_sents[0]
    assert "U.S." in en_sents[1]
    print("[OK] English sentence splitting passed")

    # 2. Hindi
    hi_text = "कृत्रिम बुद्धिमत्ता आधुनिक युग की अद्भुत देन है। क्या आप इससे सहमत हैं? यह तकनीक बहुत शक्तिशाली है॥"
    hi_sents = TextChunker.split_sentences(hi_text)
    assert len(hi_sents) == 3, f"Hindi expected 3 sentences, got {len(hi_sents)}: {hi_sents}"
    assert hi_sents[0].endswith("।")
    assert hi_sents[1].endswith("?")
    assert hi_sents[2].endswith("॥")
    print("[OK] Hindi sentence splitting passed")

    # 3. Spanish
    es_text = "El Dr. García pagó 15.50 euros por el billete. ¡Qué sorpresa tan agradable! ¿Cuándo saldrá el tren?"
    es_sents = TextChunker.split_sentences(es_text)
    assert len(es_sents) == 3, f"Spanish expected 3 sentences, got {len(es_sents)}: {es_sents}"
    assert "15.50" in es_sents[0]
    assert "Dr. García" in es_sents[0]
    print("[OK] Spanish sentence splitting passed")

    # 4. Arabic
    ar_text = "هل يمكن للذكاء الاصطناعي تحسين الإنتاجية؟ نعم، بالتأكيد۔ يعمل النظام بسرعة ودقة."
    ar_sents = TextChunker.split_sentences(ar_text)
    assert len(ar_sents) == 3, f"Arabic expected 3 sentences, got {len(ar_sents)}: {ar_sents}"
    assert ar_sents[0].endswith("؟")
    assert ar_sents[1].endswith("۔")
    assert ar_sents[2].endswith(".")
    print("[OK] Arabic sentence splitting passed")

    # 5. Chinese
    zh_text = "人工智能正在深刻改变世界。机器学习模型正在帮助科学家发现新药物！自然语言处理是否让机器理解情感？这很令人惊叹。"
    zh_sents = TextChunker.split_sentences(zh_text)
    assert len(zh_sents) == 4, f"Chinese expected 4 sentences, got {len(zh_sents)}: {zh_sents}"
    assert zh_sents[0].endswith("。")
    assert zh_sents[1].endswith("！")
    assert zh_sents[2].endswith("？")
    assert zh_sents[3].endswith("。")
    print("[OK] Chinese sentence splitting passed")

    # 6. Japanese
    ja_text = "機械学習はデータ分析に革新をもたらしています。本当に素晴らしい！あなたも使ってみますか？"
    ja_sents = TextChunker.split_sentences(ja_text)
    assert len(ja_sents) == 3, f"Japanese expected 3 sentences, got {len(ja_sents)}: {ja_sents}"
    assert ja_sents[0].endswith("。")
    assert ja_sents[1].endswith("！")
    assert ja_sents[2].endswith("？")
    print("[OK] Japanese sentence splitting passed")


def test_chunking_with_overlap_and_metadata():
    pages = [
        {
            "page_number": 1,
            "text": "First sentence on page one. Second sentence on page one. Third sentence on page one. Fourth sentence on page one."
        },
        {
            "page_number": 2,
            "text": "पहला वाक्य पृष्ठ दो पर है। दूसरा वाक्य पृष्ठ दो पर है। तीसरा वाक्य पृष्ठ दो पर है। चौथा वाक्य पृष्ठ दो पर है।"
        },
        {
            "page_number": 3,
            "text": "Primera oración en la página tres. Segunda oración en la página tres. Tercera oración en la página tres. Cuarta oración en la página tres."
        },
        {
            "page_number": 4,
            "text": "الجملة الأولى في الصفحة الرابعة. الجملة الثانية في الصفحة الرابعة. الجملة الثالثة في الصفحة الرابعة. الجملة الرابعة في الصفحة الرابعة."
        },
        {
            "page_number": 5,
            "text": "这是第五页的第一句话。这是第五页的第二句话。这是第五页的第三句话。这是第五页的第四句话。"
        },
        {
            "page_number": 6,
            "text": "これは6ページの最初の文です。これは6ページの2番目の文です。これは6ページの3番目の文です。これは6ページの4番目の文です。"
        }
    ]

    # Chunk with small budget to test chunk splits and overlap
    chunks = TextChunker.chunk_pages(pages, chunk_size=20, overlap=8)
    assert len(chunks) >= 6, f"Expected at least 6 chunks, got {len(chunks)}"

    # Check monotonic chunk_index and page preservation
    for i, c in enumerate(chunks):
        assert c["chunk_index"] == i
        assert "content" in c and len(c["content"]) > 0
        assert "token_count" in c and c["token_count"] > 0
        assert 1 <= c["page_number"] <= 6

    # Verify Chinese & Japanese character-based budget
    cjk_chunks = [c for c in chunks if c["page_number"] in (5, 6)]
    assert len(cjk_chunks) >= 2
    for c in cjk_chunks:
        assert c["token_count"] > 0
    print("[OK] test_chunking_with_overlap_and_metadata passed")


def test_decimals_and_abbreviations_no_split():
    text = "Prof. Xavier tested 0.001 mg of compound with Dr. Grey in Jan. 2024. The results were 99.9% accurate."
    sents = TextChunker.split_sentences(text)
    assert len(sents) == 2, f"Expected 2 sentences, got {len(sents)}: {sents}"
    assert "0.001" in sents[0]
    assert "Prof. Xavier" in sents[0]
    assert "Dr. Grey" in sents[0]
    assert "Jan." in sents[0]
    assert "99.9%" in sents[1]
    print("[OK] test_decimals_and_abbreviations_no_split passed")


if __name__ == "__main__":
    test_sentence_splitting_all_languages()
    test_chunking_with_overlap_and_metadata()
    test_decimals_and_abbreviations_no_split()
    print("\nALL STEP 3 MULTILINGUAL CHUNKING TESTS PASSED SUCCESSFULLY!")
