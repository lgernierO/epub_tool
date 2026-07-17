import unittest

from python_backend.services.font_face_resolve import (
    FontFaceCandidate,
    append_font_face_candidate,
    build_primary_family_file_mapping,
    parse_font_style_value,
    parse_font_weight_value,
    parse_unicode_range_value,
    select_font_face_for_char,
    select_font_file_for_char,
    unicode_range_covers,
)


class FontFaceResolveTest(unittest.TestCase):
    def test_parse_font_weight_keywords_and_ranges(self):
        self.assertEqual(parse_font_weight_value("normal"), (400, 400))
        self.assertEqual(parse_font_weight_value("bold"), (700, 700))
        self.assertEqual(parse_font_weight_value("500"), (500, 500))
        self.assertEqual(parse_font_weight_value("400 700"), (400, 700))

    def test_parse_font_style_values(self):
        self.assertEqual(parse_font_style_value("italic"), "italic")
        self.assertEqual(parse_font_style_value("oblique 10deg"), "oblique")
        self.assertEqual(parse_font_style_value("normal"), "normal")

    def test_parse_unicode_range_variants(self):
        ranges = parse_unicode_range_value("U+4E00-9FFF, U+00??, U+0041")
        self.assertEqual(ranges, ((0x4E00, 0x9FFF), (0x0000, 0x00FF), (0x0041, 0x0041)))
        self.assertTrue(unicode_range_covers(ranges, "中"))
        self.assertTrue(unicode_range_covers(ranges, "A"))
        self.assertFalse(unicode_range_covers(ranges, "Я"))

    def test_select_bold_and_italic_faces_within_same_family(self):
        faces = [
            FontFaceCandidate(
                family="story",
                font_file="regular.ttf",
                weight_min=400,
                weight_max=400,
                style="normal",
                order=1,
            ),
            FontFaceCandidate(
                family="story",
                font_file="bold.ttf",
                weight_min=700,
                weight_max=700,
                style="normal",
                order=2,
            ),
            FontFaceCandidate(
                family="story",
                font_file="italic.ttf",
                weight_min=400,
                weight_max=400,
                style="italic",
                order=3,
            ),
        ]

        bold = select_font_face_for_char(faces, "甲", requested_weight=700, requested_style="normal")
        italic = select_font_face_for_char(
            faces, "甲", requested_weight=400, requested_style="italic"
        )
        regular = select_font_face_for_char(
            faces, "甲", requested_weight=400, requested_style="normal"
        )

        self.assertEqual(bold.font_file, "bold.ttf")
        self.assertEqual(italic.font_file, "italic.ttf")
        self.assertEqual(regular.font_file, "regular.ttf")

    def test_unicode_range_splits_latin_and_cjk(self):
        faces = [
            FontFaceCandidate(
                family="mixed",
                font_file="latin.ttf",
                unicode_ranges=((0x0000, 0x00FF),),
                order=1,
            ),
            FontFaceCandidate(
                family="mixed",
                font_file="cjk.ttf",
                unicode_ranges=((0x4E00, 0x9FFF),),
                order=2,
            ),
        ]

        self.assertEqual(
            select_font_face_for_char(faces, "A").font_file,
            "latin.ttf",
        )
        self.assertEqual(
            select_font_face_for_char(faces, "中").font_file,
            "cjk.ttf",
        )

    def test_unicode_range_miss_does_not_pollute_uncovered_face(self):
        faces_by_family = {
            "mixed": [
                FontFaceCandidate(
                    family="mixed",
                    font_file="latin.ttf",
                    unicode_ranges=((0x0000, 0x00FF),),
                    order=1,
                ),
                FontFaceCandidate(
                    family="mixed",
                    font_file="cjk.ttf",
                    unicode_ranges=((0x4E00, 0x9FFF),),
                    order=2,
                ),
            ],
            "fallback": [
                FontFaceCandidate(
                    family="fallback",
                    font_file="fallback.ttf",
                    order=3,
                )
            ],
        }

        # Cyrillic is outside both unicode-ranges; fallback family should win.
        selected = select_font_file_for_char(
            faces_by_family,
            ["Mixed", "Fallback"],
            "Я",
        )
        self.assertEqual(selected, "fallback.ttf")

    def test_later_declared_face_wins_when_scores_tie(self):
        faces = [
            FontFaceCandidate(
                family="story",
                font_file="old.ttf",
                order=1,
            ),
            FontFaceCandidate(
                family="story",
                font_file="new.ttf",
                order=2,
            ),
        ]
        selected = select_font_face_for_char(faces, "甲")
        self.assertEqual(selected.font_file, "new.ttf")

    def test_primary_family_mapping_prefers_normal_400(self):
        faces_by_family = {}
        append_font_face_candidate(
            faces_by_family,
            family="Story",
            font_file="bold.ttf",
            weight=700,
            order=1,
        )
        append_font_face_candidate(
            faces_by_family,
            family="Story",
            font_file="regular.ttf",
            weight=400,
            order=2,
        )
        mapping = build_primary_family_file_mapping(faces_by_family)
        self.assertEqual(mapping["story"], "regular.ttf")


if __name__ == "__main__":
    unittest.main()
