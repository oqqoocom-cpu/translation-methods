"""Known parser limits, using invented minimal pairs rather than private text."""
import unittest

from tools.check_translation import extract_numbers


class NumberBoundaryTests(unittest.TestCase):
    def test_supported_english_and_chinese_scale(self):
        self.assertEqual(extract_numbers("3.5 million", english_scales=True),
                         extract_numbers("350\u4e07", english_scales=True))

    def test_unsupported_equivalent_forms_remain_candidates(self):
        cases = [
            ("shared-scale-range", "5-10 million", "500\u4e07\u81f31000\u4e07"),
            ("chinese-thousand", "8,000", "8\u5343"),
            ("space-grouped-number", "12 000", "12000"),
            ("spelled-number", "six items", "6\u9879"),
            ("month-name", "17 September", "9\u670817\u65e5"),
            ("other-language-scale", "2 \u043c\u043b\u043d", "200\u4e07"),
        ]
        for name, source, target in cases:
            with self.subTest(case=name):
                self.assertNotEqual(extract_numbers(source, english_scales=True),
                                    extract_numbers(target, english_scales=True))

    def test_actual_numeric_change_still_detected(self):
        self.assertNotEqual(extract_numbers("3.5 million", english_scales=True),
                            extract_numbers("360\u4e07", english_scales=True))


if __name__ == "__main__":
    unittest.main()
