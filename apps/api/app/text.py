import re
import unicodedata


def normalize_vietnamese(value: str) -> str:
    value = value.replace("Đ", "D").replace("đ", "d")
    decomposed = unicodedata.normalize("NFD", value)
    without_marks = "".join(char for char in decomposed if unicodedata.category(char) != "Mn")
    return re.sub(r"[^a-z0-9]+", " ", without_marks.lower()).strip()
