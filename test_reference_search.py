import unittest

from reference_search import (
    MATCH_DIRECT,
    classify_query,
    format_reference_answer,
    search_reference,
)


TXT = {
    "ecocode.txt": (
        "Статья 1. Основные понятия\n"
        "Отходы производства и потребления образуются в результате деятельности предприятия.\n\n"
        "Статья 320. Управление отходами\n"
        "Образователь отходов обеспечивает раздельное накопление и учет отходов."
    ),
    "koap_final.txt": (
        "Статья 344. Нарушение экологических требований\n"
        "Нарушение требований по управлению отходами влечет административную ответственность."
    ),
}

ARTICLES = [{
    "law": "Кодекс Республики Казахстан об административных правонарушениях",
    "number": "344",
    "title": "Статья 344. Нарушение экологических требований",
    "text": "Нарушение требований по управлению отходами влечет ответственность.",
    "url": "https://adilet.test/344",
    "tags": ["отходы", "экологические требования"],
}]


class QueryClassificationTests(unittest.TestCase):
    def test_required_reference_queries(self):
        for query in (
            "отходы производства",
            "где встречается нефтешлам",
            "покажи статью 344 КоАП",
        ):
            with self.subTest(query=query):
                self.assertEqual(classify_query(query), "reference")

    def test_required_situation_query(self):
        self.assertEqual(
            classify_query("на грунте лежат масляные фильтры без тары"),
            "situation",
        )


class ReferenceSearchTests(unittest.TestCase):
    def test_exact_phrase_has_highest_priority(self):
        hits = search_reference("отходы производства", TXT, ARTICLES)
        self.assertTrue(hits)
        self.assertEqual(hits[0].match_type, MATCH_DIRECT)
        self.assertIn("Отходы производства", hits[0].entry.text)

    def test_article_and_document_lookup(self):
        hits = search_reference("покажи статью 344 КоАП", TXT, ARTICLES)
        self.assertTrue(hits)
        self.assertEqual(hits[0].entry.locator, "Статья 344")
        self.assertIn("административных правонарушениях", hits[0].entry.document)

    def test_answer_contains_only_stored_url(self):
        answer = format_reference_answer(
            "статья 344 КоАП",
            search_reference("статья 344 КоАП", TXT, ARTICLES),
        )
        self.assertIn("https://adilet.test/344", answer)


if __name__ == "__main__":
    unittest.main()
