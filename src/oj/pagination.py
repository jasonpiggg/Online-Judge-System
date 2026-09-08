"""Translate arbitrary positive API page sizes to bounded SQLite integers."""


def page_window(page: int, size: int, total: int) -> tuple[int, int]:
    # An out-of-range page is empty, including values larger than SQLite int64.
    return min(size, total), min((page - 1) * size, total)
