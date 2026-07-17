"""Structured @font-face candidate selection for EPUB font encrypt/decrypt.

This module keeps the CSS subset intentionally small: family matching,
unicode-range coverage, font-style, font-weight, and later-declared
@ font-face precedence. It is not a full browser font engine.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable, Sequence


FONT_STYLE_NORMAL = "normal"
FONT_STYLE_ITALIC = "italic"
FONT_STYLE_OBLIQUE = "oblique"
DEFAULT_FONT_WEIGHT = 400
DEFAULT_FONT_STYLE = FONT_STYLE_NORMAL


@dataclass(slots=True)
class FontFaceCandidate:
    family: str
    font_file: str
    weight_min: int = DEFAULT_FONT_WEIGHT
    weight_max: int = DEFAULT_FONT_WEIGHT
    style: str = DEFAULT_FONT_STYLE
    unicode_ranges: tuple[tuple[int, int], ...] | None = None
    order: int = 0
    source_path: str | None = None

    @property
    def weight(self) -> int:
        return self.weight_min if self.weight_min == self.weight_max else self.weight_min


@dataclass(slots=True)
class FontSelectionRequest:
    families: Sequence[str] = field(default_factory=tuple)
    weight: int = DEFAULT_FONT_WEIGHT
    style: str = DEFAULT_FONT_STYLE


def normalize_font_family_name(name: str | None) -> str:
    return re.sub(r"\s+", " ", (name or "").strip().strip("'\"")).lower()


def parse_font_weight_value(value) -> tuple[int, int]:
    """Parse CSS font-weight into an inclusive [min, max] range."""
    if value is None:
        return DEFAULT_FONT_WEIGHT, DEFAULT_FONT_WEIGHT

    if isinstance(value, (list, tuple)):
        if not value:
            return DEFAULT_FONT_WEIGHT, DEFAULT_FONT_WEIGHT
        if len(value) == 1:
            return parse_font_weight_value(value[0])
        left = parse_font_weight_value(value[0])[0]
        right = parse_font_weight_value(value[1])[0]
        return (min(left, right), max(left, right))

    text = str(value).strip().lower()
    if not text:
        return DEFAULT_FONT_WEIGHT, DEFAULT_FONT_WEIGHT
    if text == "normal":
        return 400, 400
    if text == "bold":
        return 700, 700
    if text in {"lighter", "bolder"}:
        # Relative keywords need computed parent weight; treat as normal defaults.
        return DEFAULT_FONT_WEIGHT, DEFAULT_FONT_WEIGHT

    range_match = re.fullmatch(r"(\d{1,4})\s+(\d{1,4})", text)
    if range_match:
        left = _clamp_font_weight(int(range_match.group(1)))
        right = _clamp_font_weight(int(range_match.group(2)))
        return (min(left, right), max(left, right))

    number_match = re.fullmatch(r"\d{1,4}", text)
    if number_match:
        weight = _clamp_font_weight(int(text))
        return weight, weight

    return DEFAULT_FONT_WEIGHT, DEFAULT_FONT_WEIGHT


def parse_font_style_value(value) -> str:
    text = str(value or "").strip().lower()
    if not text:
        return DEFAULT_FONT_STYLE
    if text.startswith("oblique"):
        return FONT_STYLE_OBLIQUE
    if text == "italic":
        return FONT_STYLE_ITALIC
    if text == "normal":
        return FONT_STYLE_NORMAL
    return DEFAULT_FONT_STYLE


def parse_unicode_range_value(value) -> tuple[tuple[int, int], ...] | None:
    text = str(value or "").strip()
    if not text:
        return None

    ranges: list[tuple[int, int]] = []
    for part in text.split(","):
        token = part.strip().upper().replace(" ", "")
        if not token:
            continue
        if token.startswith("U+"):
            token = token[2:]
        if not token:
            continue

        if "-" in token:
            start_text, end_text = token.split("-", 1)
            start = _parse_unicode_codepoint(start_text)
            end = _parse_unicode_codepoint(end_text)
        elif "?" in token:
            start = _parse_unicode_codepoint(token.replace("?", "0"))
            end = _parse_unicode_codepoint(token.replace("?", "F"))
        else:
            start = end = _parse_unicode_codepoint(token)

        if start is None or end is None:
            continue
        if start > end:
            start, end = end, start
        ranges.append((start, end))

    if not ranges:
        return None
    return tuple(ranges)


def unicode_range_covers(ranges: Sequence[tuple[int, int]] | None, char: str) -> bool:
    if not ranges:
        return True
    if not char:
        return False
    codepoint = ord(char)
    return any(start <= codepoint <= end for start, end in ranges)


def style_match_distance(requested_style: str, face_style: str) -> int:
    requested = parse_font_style_value(requested_style)
    face = parse_font_style_value(face_style)
    if requested == face:
        return 0
    # italic and oblique are closer to each other than to normal.
    if {requested, face} == {FONT_STYLE_ITALIC, FONT_STYLE_OBLIQUE}:
        return 1
    if requested in {FONT_STYLE_ITALIC, FONT_STYLE_OBLIQUE} and face == FONT_STYLE_NORMAL:
        return 2
    if requested == FONT_STYLE_NORMAL and face in {FONT_STYLE_ITALIC, FONT_STYLE_OBLIQUE}:
        return 2
    return 3


def weight_match_distance(requested_weight: int, face: FontFaceCandidate) -> int:
    requested = _clamp_font_weight(int(requested_weight or DEFAULT_FONT_WEIGHT))
    if face.weight_min <= requested <= face.weight_max:
        return 0

    # CSS Fonts: prefer the nearest face; when equidistant, prefer the heavier face
    # for requests above the gap midpoint semantics used by common engines.
    if requested < face.weight_min:
        return face.weight_min - requested
    return requested - face.weight_max


def select_font_face_for_char(
    faces: Sequence[FontFaceCandidate],
    char: str,
    *,
    requested_weight: int = DEFAULT_FONT_WEIGHT,
    requested_style: str = DEFAULT_FONT_STYLE,
) -> FontFaceCandidate | None:
    """Pick the best @font-face for one character.

    Priority:
    1. unicode-range coverage
    2. font-style distance
    3. font-weight distance
    4. later CSS declaration order (higher order wins)
    """
    if not faces:
        return None

    # Only faces that cover the character are eligible. If none cover it,
    # return None so the caller can fall back to the next family/candidate
    # instead of polluting an uncovered face mapping.
    covering = [face for face in faces if unicode_range_covers(face.unicode_ranges, char)]
    if not covering:
        return None
    pool = covering

    def sort_key(face: FontFaceCandidate):
        return (
            style_match_distance(requested_style, face.style),
            weight_match_distance(requested_weight, face),
            -face.order,
        )

    return sorted(pool, key=sort_key)[0]


def select_font_file_for_char(
    faces_by_family: dict[str, Sequence[FontFaceCandidate]],
    families: Sequence[str],
    char: str,
    *,
    requested_weight: int = DEFAULT_FONT_WEIGHT,
    requested_style: str = DEFAULT_FONT_STYLE,
) -> str | None:
    for family in families:
        normalized = normalize_font_family_name(family)
        if not normalized:
            continue
        selected = select_font_face_for_char(
            faces_by_family.get(normalized) or (),
            char,
            requested_weight=requested_weight,
            requested_style=requested_style,
        )
        if selected is not None:
            return selected.font_file
    return None


def collapse_family_to_primary_file(
    faces: Sequence[FontFaceCandidate],
) -> str | None:
    """Backward-compatible single-file mapping used by list/target APIs."""
    if not faces:
        return None
    # Prefer the latest normal/400 face, else latest declared face.
    normal_faces = [
        face
        for face in faces
        if face.style == FONT_STYLE_NORMAL and face.weight_min <= 400 <= face.weight_max
    ]
    pool = normal_faces or list(faces)
    return sorted(pool, key=lambda face: face.order)[-1].font_file


def extract_font_weight_from_tokens(tokens) -> tuple[int, int] | None:
    tokens = list(tokens or [])
    if not tokens:
        return None
    # Support both "700" and "400 700".
    values = []
    for token in tokens:
        token_type = getattr(token, "type", None)
        if token_type in ("whitespace", "comment"):
            continue
        if token_type == "number":
            try:
                values.append(str(int(float(token.value))))
            except Exception:
                continue
        elif token_type == "ident":
            values.append(str(token.value))
        elif token_type == "dimension":
            # Ignore units; not valid for font-weight but keep defensive parsing.
            continue
        if len(values) >= 2:
            break
    if not values:
        return None
    return parse_font_weight_value(values if len(values) > 1 else values[0])


def extract_font_style_from_tokens(tokens) -> str | None:
    for token in tokens or []:
        if getattr(token, "type", None) in ("whitespace", "comment"):
            continue
        if getattr(token, "type", None) == "ident":
            return parse_font_style_value(token.value)
        if getattr(token, "type", None) == "function" and getattr(token, "lower_name", "") == "oblique":
            return FONT_STYLE_OBLIQUE
    return None


def extract_font_face_descriptor_values(declarations) -> dict:
    """Extract family/src/weight/style/unicode-range from @font-face declarations."""
    result = {
        "families": [],
        "weight": (DEFAULT_FONT_WEIGHT, DEFAULT_FONT_WEIGHT),
        "style": DEFAULT_FONT_STYLE,
        "unicode_ranges": None,
        "src_urls": [],
    }
    for declaration in declarations or []:
        if getattr(declaration, "type", None) != "declaration":
            continue
        name = getattr(declaration, "lower_name", "")
        value_tokens = getattr(declaration, "value", [])
        if name == "font-weight":
            parsed = extract_font_weight_from_tokens(value_tokens)
            if parsed is not None:
                result["weight"] = parsed
        elif name == "font-style":
            parsed = extract_font_style_from_tokens(value_tokens)
            if parsed is not None:
                result["style"] = parsed
        elif name == "unicode-range":
            # Prefer serialized text so wildcard/range syntax stays intact.
            try:
                from tinycss2 import serialize

                raw = serialize(value_tokens)
            except Exception:
                raw = " ".join(str(getattr(token, "value", token)) for token in value_tokens)
            result["unicode_ranges"] = parse_unicode_range_value(raw)
    return result


def append_font_face_candidate(
    faces_by_family: dict[str, list[FontFaceCandidate]],
    *,
    family: str,
    font_file: str,
    weight=None,
    style=None,
    unicode_ranges=None,
    order: int = 0,
    source_path: str | None = None,
) -> FontFaceCandidate | None:
    normalized = normalize_font_family_name(family)
    if not normalized or not font_file:
        return None
    weight_min, weight_max = parse_font_weight_value(weight)
    candidate = FontFaceCandidate(
        family=normalized,
        font_file=font_file,
        weight_min=weight_min,
        weight_max=weight_max,
        style=parse_font_style_value(style),
        unicode_ranges=tuple(unicode_ranges) if unicode_ranges else None,
        order=order,
        source_path=source_path,
    )
    faces_by_family.setdefault(normalized, []).append(candidate)
    return candidate


def build_primary_family_file_mapping(
    faces_by_family: dict[str, Sequence[FontFaceCandidate]],
) -> dict[str, str]:
    mapping = {}
    for family, faces in faces_by_family.items():
        primary = collapse_family_to_primary_file(faces)
        if primary:
            mapping[family] = primary
    return mapping


def iter_unique_font_files(faces_by_family: dict[str, Sequence[FontFaceCandidate]]) -> Iterable[str]:
    seen = set()
    for faces in faces_by_family.values():
        for face in faces:
            if face.font_file in seen:
                continue
            seen.add(face.font_file)
            yield face.font_file


def _clamp_font_weight(value: int) -> int:
    return max(1, min(1000, int(value)))


def _parse_unicode_codepoint(token: str) -> int | None:
    token = (token or "").strip().upper()
    if token.startswith("U+"):
        token = token[2:]
    if not token or any(char not in "0123456789ABCDEF" for char in token):
        return None
    try:
        return int(token, 16)
    except ValueError:
        return None
