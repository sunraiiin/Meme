import unittest

from app.core.rag.image_describe import _parse, build_searchable_text


class ImageDescribeTests(unittest.TestCase):
    def test_parse_normalizes_metadata(self):
        info = _parse(
            '{"description":"一张技术文章截图","ocr_text":"Pass@k","objects":["文字", ""],"scene":"文档截图"}'
        )

        self.assertEqual(info["description"], "一张技术文章截图")
        self.assertEqual(info["ocr_text"], "Pass@k")
        self.assertEqual(info["objects"], ["文字"])
        self.assertEqual(info["scene"], "文档截图")

    def test_searchable_text_includes_objects(self):
        searchable = build_searchable_text(
            {
                "description": "技术文章截图",
                "ocr_text": "Pass@k",
                "objects": ["文字", "标题"],
                "scene": "文档截图",
            }
        )

        self.assertIn("技术文章截图", searchable)
        self.assertIn("Pass@k", searchable)
        self.assertIn("标题", searchable)
        self.assertIn("文档截图", searchable)

    def test_parse_keeps_bounded_fallback_for_empty_object(self):
        info = _parse('{"description":"", "ocr_text":"", "objects":[], "scene":""}')

        self.assertEqual(
            info["description"],
            '{"description":"", "ocr_text":"", "objects":[], "scene":""}',
        )
