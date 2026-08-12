import re

__all__ = ["strip_markdown"]

_RE_FENCED_CODE = re.compile(r"```[\s\S]*?```", re.MULTILINE)
_RE_INLINE_CODE = re.compile(r"`[^`]*`")
_RE_TABLE_LINE = re.compile(r"^\s*\|.*\|\s*$", re.MULTILINE)
_RE_HRULE = re.compile(r"^\s*[-=*_]{3,}\s*$", re.MULTILINE)
_RE_HEADER = re.compile(r"^\s*#{1,6}\s+", re.MULTILINE)
_RE_BOLD_AST = re.compile(r"\*\*(.+?)\*\*")
_RE_BOLD_UND = re.compile(r"__(.+?)__")
_RE_ITAL_AST = re.compile(r"\*([^*\n]+?)\*")
_RE_ITAL_UND = re.compile(r"_([^_\n]+?)_")
_RE_LIST_BULLET = re.compile(r"^\s*[-*+]\s+", re.MULTILINE)
_RE_LIST_NUMBER = re.compile(r"^\s*\d+\.\s+", re.MULTILINE)
_RE_LINK = re.compile(r"\[([^\]]+)\]\([^)]+\)")
_RE_HTML_TAG = re.compile(r"<[^>]+>")
_RE_BLANKLINES = re.compile(r"\n{3,}")


def strip_markdown(text: str) -> str:
    text = _RE_FENCED_CODE.sub("", text)
    text = _RE_INLINE_CODE.sub("", text)
    text = _RE_TABLE_LINE.sub("", text)
    text = _RE_HRULE.sub("", text)
    text = _RE_HEADER.sub("", text)
    text = _RE_LINK.sub(r"\1", text)
    text = _RE_BOLD_AST.sub(r"\1", text)
    text = _RE_BOLD_UND.sub(r"\1", text)
    text = _RE_ITAL_AST.sub(r"\1", text)
    text = _RE_ITAL_UND.sub(r"\1", text)
    text = _RE_LIST_BULLET.sub("", text)
    text = _RE_LIST_NUMBER.sub("", text)
    text = _RE_HTML_TAG.sub("", text)
    text = _RE_BLANKLINES.sub("\n\n", text)
    return text.strip()
