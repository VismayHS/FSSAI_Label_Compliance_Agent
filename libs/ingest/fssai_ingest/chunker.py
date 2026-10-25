"""Clause-aware chunking of an FSSAI regulation compendium (decision 002).

Input: the page texts of one PDF. Output: Chunks that never cross a clause boundary.

How the text is read:
- Regulations open with "<n>. <Title>.-" and are numbered 1, 2, 3, ...; a number out of sequence
  is text, not a heading (tables inside clauses also start lines with numbers).
- Below a regulation, markers at the start of a line open sub-units: (1), (2A), (a), (i), (A).
  A marker counts only if it is the next one at some open level, or the first one of a new level.
  Anything else is ordinary text, which is why "(2), (3) and 1.9 of schedule II" or a "(vi)" printed
  out of order stays inside its clause. "(i)" after "(h)" is the letter i unless the line before
  ends in a lead-in (":" or "-"), in which case it starts a roman list.
- Schedules ("SCHEDULE – I", "Schedule-II") hold tables. A table header ("Sl. No ...") starts row
  numbering; each row ("11. Protein Source ...") is one unit, so a nutrient is never separated from
  its condition. Page-repeated headers are dropped. "Note"/"*"/"#" lines become a notes unit.
- The compendium prints amended text after the original, between "Substitution of highlighted
  provision" and "[Operationalized w.e.f. ...]". Units inside such a block replace the units with the
  same clause id (and their sub-clauses), which become `superseded`. "Omission of highlighted
  provision" supersedes the unit just before it. A block without markers ("Substitution of
  highlighted words") becomes a separate in-force `partial` unit on the same clause.

Units are then grouped into chunks: a clause whose whole subtree fits in max_chars is one chunk; a
bigger one is split into its sub-clauses, recursively; one oversized unit is split at sentence
boundaries into parts. Superseded and amended units are always chunks of their own.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from fssai_retrieval.index import Chunk

REG_NAMES = {
    "FSS-LD-2020": "Food Safety and Standards (Labelling and Display) Regulations, 2020",
    "FSS-AC-2018": "Food Safety and Standards (Advertising and Claims) Regulations, 2018",
}

_PAGE_HEADER = re.compile(r"^Version\s*[-–]+\s*[IVX]+\s*\(\d{2}\.\d{2}\.\d{4}\)\s*$", re.I)
_CHAPTER = re.compile(r"^CHAPTER\s*[-–]?\s*(\d+)\s*$", re.I)
_REGULATION = re.compile(r"^(?:\d\[)?(\d{1,2})\s*\.\s*(\S.*)?$")
_SCHEDULE = re.compile(r"^(?:\d\[)?\s*SCHEDULE\s*[-–]\s*([IVX]+A?)\s*()$", re.I)  # a heading line, not a reference
_SEE = re.compile(r"^[\[(]\s*See\s+regulation", re.I)
_TITLE_SPLIT = re.compile(
    r"^(?P<title>.{2,120}?)\s*(?:\.\s*[-–—]+|\s[-–—]+(?=\s|$)|[-–—](?=\s|$)|:-)\s*(?P<rest>.*)$")
_MARKER = re.compile(r"^\(\s*([0-9]{1,2}[A-Z]?|[ivxl]{1,6}|[a-z]|[A-Z])\s*\)")
_LEADING_JUNK = re.compile(r"^(?:\d\[|[“\"'‘])+")
_BLOCK_START = re.compile(
    r"^(?:Amendment\s+for\s+)?(Substitution|Omission|Insertion)\s+of\s+(?:the\s+)?(?:highlighted\s+)?"
    r"(?:provision|words)\b(?!.*w\.e\.f)", re.I)
_BLOCK_END = re.compile(r"^\[\s*(?:Re-)?operationali[sz]ed", re.I)
_TABLE_HEADER = re.compile(r"^(?:S\s*[IlL1]?\s*\.?\s*No\b|S\s*[IlL1]\s*\.?\s*$|(?:\(\d\)\s*){3,}$)", re.I)
# "11. Protein ...", "1 Calcium ..." or a bare "6"; never "3 g of fat per 100 g" (a condition line)
_ROW = re.compile(r"^(?:\d\[)?(\d{1,2})(?:\s*\.(?:\s+\S.*)?|\s+[A-Z(].*|\s*)$")
_SECTION = re.compile(r"^(?:\d\[)?(\d)\.\s+(\S.*)$")
_SUBSECTION = re.compile(r"^(?:\d\[)?(\d)\.(\d{1,2})\s+([A-Z].*)$")
_NOTE = re.compile(r"^(?:Note\b|\*|#\s)", re.I)
_NOTIFICATION = re.compile(r"^Note\s*:?\s*The principal regulations", re.I)
_LEAD_IN = re.compile(r"(?::|[-–—]|namely\s*,?)\s*$", re.I)
_VERBISH = re.compile(r"\b(shall|may|means|are|is)\b", re.I)

_ROMANS = ["i", "ii", "iii", "iv", "v", "vi", "vii", "viii", "ix", "x", "xi", "xii", "xiii", "xiv", "xv",
           "xvi", "xvii", "xviii", "xix", "xx", "xxi", "xxii", "xxiii", "xxiv", "xxv"]
_FIRST = {"num": "1", "letter": "a", "roman": "i", "upper": "A"}
MIN_HEADING_ONLY_CHARS = 40
_TABLE_KINDS = ("row", "notes")


def _kinds(token: str) -> list[str]:
    """Kinds a marker token can be, most specific first: (i) may be roman one or the letter i."""
    if token[0].isdigit():
        return ["num"]
    if len(token) == 1 and token.isupper():
        return ["upper"]
    kinds = ["roman"] if token in _ROMANS else []
    if len(token) == 1:
        kinds.append("letter")
    return kinds


def _follows(kind: str, current: str, token: str) -> bool:
    """True if `token` is the next marker after `current` at a level of `kind`. (2A) may follow (2)."""
    if kind == "num":
        base = re.match(r"\d+", current).group()
        return token == str(int(base) + 1) or token == f"{base}{token[-1]}" and token[-1].isalpha()
    if kind == "roman":
        i = _ROMANS.index(current) if current in _ROMANS else -2
        return 0 <= i + 1 < len(_ROMANS) and token == _ROMANS[i + 1]
    return len(current) == 1 and token == chr(ord(current) + 1)


@dataclass
class Level:
    kind: str     # special | reg | schedule | section | subsection | num | letter | roman | upper | row | notes
    value: str


@dataclass
class Unit:
    path: tuple[str, ...]
    clause_id: str
    headings: list[str]
    lines: list[str] = field(default_factory=list)
    page: int = 0
    order: int = 0
    status: str = "in_force"
    amendment: str | None = None   # substituted | inserted | partial
    effective: str | None = None
    block: int = 0

    @property
    def text(self) -> str:
        return re.sub(r"\s+", " ", " ".join(self.lines)).strip()


def _clause_id(stack: list[Level]) -> str:
    """5(3)(c)(i) for regulations; "Schedule II, 1(3), item 2" for schedules."""
    if not stack:
        return ""
    head = stack[0]
    if head.kind == "special":
        return head.value
    if head.kind == "reg":
        return head.value + "".join(f"({lv.value})" for lv in stack[1:])
    out, inner = head.value, ""
    for lv in stack[1:]:
        if lv.kind in ("section", "subsection"):
            inner = lv.value
        elif lv.kind == "row":
            out += (f", {inner}" if inner else "") + f", item {lv.value}"
            inner = ""
        elif lv.kind == "notes":
            out += (f", {inner}" if inner else "") + ", notes"
            inner = ""
        else:
            inner += f"({lv.value})"
    return out + (f", {inner}" if inner else "")


class _Parser:
    def __init__(self, regulation: str) -> None:
        self.regulation = regulation
        self.units: list[Unit] = []
        self.stack: list[Level] = [Level("special", "Title")]
        self.headings: dict[tuple, str] = {}
        self.chapter: str | None = None
        self.chapter_title_pending = False
        self.current: Unit | None = None
        self.prev_text = ""
        self.page = 1
        self.fresh_page = False
        self.mode = "regs"               # regs | schedule | notification
        self.expected_reg = 1
        # schedules and tables
        self.schedule_title_seen = False
        self.schedule_see_seen = False
        self.schedule_heading_open = False
        self.expected_section = 1
        self.table_open = False
        self.header_capture = False
        self.header_lines: list[str] = []
        self.table_header: set[str] = set()
        self.expected_row = 1
        self.last_row_unit: Unit | None = None
        self.saved_row_stack: list[Level] | None = None
        # amendment blocks
        self.block: str | None = None    # substitution | insertion | omission
        self.block_id = 0
        self.block_saved: dict | None = None
        self.effective_lines: list[str] | None = None
        self.continuation_parent: list[Level] | None = None

    # ------------------------------------------------------------ units

    def _key(self, stack: list[Level] | None = None) -> tuple[str, ...]:
        return tuple(f"{lv.kind}:{lv.value}" for lv in (self.stack if stack is None else stack))

    def _headings(self) -> list[str]:
        out = [self.chapter] if self.chapter and self.stack[0].kind == "reg" else []
        key = self._key()
        for i in range(1, len(key)):
            if key[:i] in self.headings:
                out.append(self.headings[key[:i]])
        return out

    def _open_unit(self, first_line: str = "") -> Unit:
        unit = Unit(path=self._key(), clause_id=_clause_id(self.stack), headings=self._headings(),
                    page=self.page, order=len(self.units))
        if self.block:
            unit.amendment = "substituted" if self.block == "substitution" else "inserted"
            unit.block = self.block_id
        self.units.append(unit)
        self.current = unit
        self.continuation_parent = None
        if first_line:
            self._add(first_line)
        return unit

    def _add(self, line: str) -> None:
        if self.current is None:
            saved = self.block_saved["current"] if self.block and self.block_saved else None
            if self.block and saved is not None:
                # words-only amendment: a separate in-force unit on the clause it amends
                self.current = Unit(path=saved.path, clause_id=saved.clause_id, headings=list(saved.headings),
                                    page=self.page, order=len(self.units), amendment="partial",
                                    block=self.block_id)
                self.units.append(self.current)
            elif self.continuation_parent is not None:
                # text after an amendment that replaced the unit it followed belongs to the parent clause;
                # the marker stack stays where it was, so the next sibling marker is still recognised
                parent = self.continuation_parent
                full, self.stack = self.stack, list(parent)
                self._open_unit()
                self.stack = full
            else:
                self._open_unit()
        self.current.lines.append(line)
        self.prev_text = line

    # ------------------------------------------------------------ regulations and schedules

    def _start_regulation(self, number: int, rest: str) -> None:
        self.stack = [Level("reg", str(number))]
        self.expected_reg = number + 1
        self.table_open = False
        m = _TITLE_SPLIT.match(rest)
        if m:
            title, body = m.group("title").strip(" .-–"), m.group("rest")
            head = rest[: len(rest) - len(body)].rstrip() if body else rest
        elif rest and len(rest.split()) <= 12 and not _VERBISH.search(rest):
            title, body, head = rest.strip(" .-–"), "", rest
        else:
            title, body, head = "", "", rest
        self.headings[self._key()] = f"Regulation {number}" + (f": {title}" if title else "")
        self._open_unit(f"{number}. {head}".strip())
        if body:
            self._line(body, inline=True)

    def _start_schedule(self, roman: str, rest: str, line: str) -> None:
        name = f"Schedule {roman.upper()}"
        self.mode = "schedule"
        self.stack = [Level("schedule", name)]
        self.table_open = self.header_capture = False
        self.expected_section = 1
        self.schedule_title_seen = self.schedule_see_seen = False
        self.schedule_heading_open = True
        self.headings[self._key()] = name
        self._open_unit(line)

    def _schedule_heading(self, line: str) -> bool:
        """The "[See regulation ...]" line and a short title right after a schedule heading."""
        if not self.schedule_heading_open:
            return False
        key = self._key(self.stack[:1])
        if _SEE.match(line):
            self.headings[key] += f" [{re.sub(r'^[\[(]\s*|\s*[\])]\s*$', '', line)}]"
            self.schedule_see_seen = True
            self.current.lines.append(line)
            if self.schedule_title_seen:
                self.schedule_heading_open = False
            return True
        if (not self.schedule_title_seen and len(line.split()) <= 10 and not _MARKER.match(line)
                and not _TABLE_HEADER.match(line) and not _SECTION.match(line) and not _ROW.match(line)):
            self.headings[key] += f": {line}"
            self.schedule_title_seen = True
            self.current.lines.append(line)
            if self.schedule_see_seen:
                self.schedule_heading_open = False
            return True
        self.schedule_heading_open = False
        return False

    # ------------------------------------------------------------ markers

    def _child_kind(self, token: str) -> str | None:
        deepest = self.stack[-1].kind if len(self.stack) > 1 else None
        for k in _kinds(token):
            if token == _FIRST[k] and deepest != k:
                return k
        return None

    def _match_marker(self, token: str, *, qualifier: bool, in_table: bool) -> tuple[int, str] | None:
        """Where `token` opens a unit: (stack depth, kind). None means it is plain text."""
        kinds = _kinds(token)
        if not kinds:
            return None
        if in_table:  # inside a table only a sibling of a level above the table closes it
            top = next((i for i, lv in enumerate(self.stack) if lv.kind in _TABLE_KINDS), len(self.stack))
            for d in range(top - 1, 0, -1):
                lv = self.stack[d]
                if lv.kind in kinds and _follows(lv.kind, lv.value, token):
                    return d, lv.kind
            return None
        if self.block or qualifier:
            # amended text re-declares existing units; "(1)" in "(1) (a)" names the unit we are in
            for d in range(len(self.stack) - 1, 0, -1):
                lv = self.stack[d]
                if lv.kind in kinds and (self.block or lv.value == token or _follows(lv.kind, lv.value, token)):
                    return d, lv.kind
        child = self._child_kind(token)
        if child and _LEAD_IN.search(self.prev_text):
            return len(self.stack), child
        for d in range(len(self.stack) - 1, 0, -1):
            lv = self.stack[d]
            if lv.kind in kinds and _follows(lv.kind, lv.value, token):
                return d, lv.kind
        if child:
            return len(self.stack), child
        return None

    def _try_markers(self, line: str) -> bool:
        """Consume leading markers such as "(3)", "(1) (a)" or "2[(1)(b)". True if the line opened a unit."""
        rest = _LEADING_JUNK.sub("", line).lstrip()
        tokens = []
        while (m := _MARKER.match(rest)):
            after = rest[m.end():]
            if after[:1] in (",", ")") or re.match(r"\s*(and|or|of)\b", after):
                break  # a cross-reference such as "(2), (3) and 1.9", not a marker
            tokens.append(m.group(1))
            rest = after.lstrip()
        placed = 0
        for n, token in enumerate(tokens):
            found = self._match_marker(token, qualifier=n < len(tokens) - 1,
                                       in_table=self.table_open and n == 0)
            if found is None:
                break
            depth, kind = found
            qualifier = n < len(tokens) - 1
            if not (qualifier and depth < len(self.stack) and self.stack[depth].value == token):
                self.stack = self.stack[:depth] + [Level(kind, token)]
            # else: "(1)" in "(1)(b)" only names the unit we are already in; keep its sub-levels
            placed += 1
        if not placed:
            return False
        if self.table_open:
            self.table_open = False
            self.last_row_unit = None
        self._open_unit(line)
        self.headings[self._key()] = line[:90]
        self._split_inline_title(line)
        return True

    def _split_inline_title(self, line: str) -> None:
        """"(1) Non-addition of sugars. - (a) Claims ..." holds a second marker after a short title."""
        m = re.match(r"^(.*?\S)\s*(?:\.\s*[-–—]+|:-)\s*(\(\s*[a-z0-9]{1,3}\s*\)\s+\S.*)$", line)
        if not m or len(m.group(1)) > 90:
            return
        self.current.lines[-1] = line[: m.start(2)].rstrip()
        self.prev_text = self.current.lines[-1]
        self._line(m.group(2), inline=True)

    # ------------------------------------------------------------ amendment blocks

    def _begin_block(self, kind: str) -> None:
        self.block = kind.lower()
        self.block_id += 1
        self.block_saved = {
            "stack": list(self.stack), "current": self.current, "mode": self.mode,
            "table_open": self.table_open, "last_row_unit": self.last_row_unit,
            "expected_row": self.expected_row, "expected_section": self.expected_section,
        }
        self.current = None

    def _end_block(self) -> None:
        saved, kind, block_id = self.block_saved, self.block, self.block_id
        effective = re.sub(r"\s+", " ", " ".join(self.effective_lines or [])).strip(" []") or None
        self.effective_lines = None
        unit = saved["current"]
        new_units = [u for u in self.units if u.block == block_id]
        superseded_current = False
        if kind == "substitution":
            for new in (u for u in new_units if u.amendment != "partial"):
                for old in self.units:
                    if (old.block != block_id and old.status == "in_force" and old.order < new.order
                            and old.path[: len(new.path)] == new.path):
                        old.status = "superseded"
                        old.effective = f"Replaced: {effective}" if effective else "Replaced by amendment"
                        superseded_current = superseded_current or old is unit
        elif kind == "omission" and unit is not None:
            unit.status = "superseded"
            unit.effective = f"Omitted: {effective}" if effective else "Omitted by amendment"
            superseded_current = True
        for u in new_units:
            u.effective = effective
        # back to where the original text was; later text continues there
        self.block = self.block_saved = None
        self.stack, self.mode = saved["stack"], saved["mode"]
        self.table_open, self.last_row_unit = saved["table_open"], saved["last_row_unit"]
        self.expected_row, self.expected_section = saved["expected_row"], saved["expected_section"]
        if superseded_current:
            self.current = None
            self.continuation_parent = self.stack[:-1] if len(self.stack) > 1 else list(self.stack)
        else:
            self.current = unit

    # ------------------------------------------------------------ tables

    def _row_start(self, line: str) -> int | None:
        m = _ROW.match(line)
        return int(m.group(1)) if m and int(m.group(1)) == self.expected_row else None

    def _pop_table_levels(self) -> None:
        while len(self.stack) > 1 and self.stack[-1].kind in _TABLE_KINDS:
            self.stack.pop()

    def _schedule_line(self, line: str) -> bool:
        norm = re.sub(r"\s+", " ", line).strip().lower()
        if self._schedule_heading(line):
            return True
        if self.header_capture:
            if self._row_start(line) is None:
                self.header_lines.append(line)
                self.table_header.add(norm)
                return True
            self.header_capture = False
            key = self._key([lv for lv in self.stack if lv.kind not in _TABLE_KINDS])
            cols = re.sub(r"\s+", " ", " ".join(self.header_lines))[:120]
            self.headings[key] = (self.headings.get(key, "") + f" | columns: {cols}").strip(" |")
        if self.table_open and self.fresh_page and norm in self.table_header:
            return True  # header repeated at the top of a new page
        if _TABLE_HEADER.match(line):
            self._pop_table_levels()
            self.table_open = self.header_capture = True
            self.header_lines, self.table_header = [line], {norm}
            self.expected_row = 1
            self.last_row_unit = None
            return True
        self.fresh_page = False
        if self.table_open:
            row = self._row_start(line)
            if row is not None:
                self._pop_table_levels()
                self.stack.append(Level("row", str(row)))
                self.expected_row = row + 1
                self._open_unit(line)
                self.last_row_unit = self.current
                return True
            if _NOTE.match(line):
                if self.stack[-1].kind == "notes":
                    self._add(line)
                else:
                    self._pop_table_levels()
                    self.stack.append(Level("notes", "notes"))
                    self._open_unit(line)
                return True
            if _MARKER.match(line):
                if self._try_markers(line):
                    return True
                if self.last_row_unit is not None and self.stack[-1].kind == "notes":
                    self.current = self.last_row_unit  # a row continued after a note (PDF reading order)
                    self._add(line)
                    return True
            return False
        m = _SUBSECTION.match(line)
        if m and any(lv.kind == "section" and lv.value == m.group(1) for lv in self.stack):
            depth = next(i for i, lv in enumerate(self.stack) if lv.kind == "section")
            self.stack = self.stack[: depth + 1] + [Level("subsection", f"{m.group(1)}.{m.group(2)}")]
            self.headings[self._key()] = line[:90]
            self._open_unit(line)
            return True
        m = _SECTION.match(line)
        if (m and int(m.group(1)) == self.expected_section and len(m.group(2).split()) <= 8
                and not _VERBISH.search(m.group(2))):
            self.stack = self.stack[:1] + [Level("section", m.group(1))]
            self.expected_section += 1
            self.headings[self._key()] = line[:90]
            self._open_unit(line)
            return True
        return False

    # ------------------------------------------------------------ lines

    def feed(self, page: int, line: str) -> None:
        if page != self.page:
            self.page, self.fresh_page = page, True
        line = line.strip()
        if line and not _PAGE_HEADER.match(line):
            self._line(line)

    def _line(self, line: str, inline: bool = False) -> None:
        if self.effective_lines is not None:  # the "[Operationalized ...]" note that closes a block
            self.effective_lines.append(line)
            if line.rstrip().endswith("]"):
                self._end_block()
            return
        if self.block and _BLOCK_END.match(line):
            self.effective_lines = [line]
            if line.rstrip().endswith("]"):
                self._end_block()
            return
        m = _BLOCK_START.match(line)
        if m and not self.block:
            self._begin_block(m.group(1))
            return

        if self.mode == "notification":
            if _MARKER.match(line) and self.last_row_unit is not None:
                self.mode, self.stack = "schedule", list(self.saved_row_stack or self.stack)
                self.current = self.last_row_unit  # table rows printed after the closing note
            self._add(line)
            return
        if _NOTIFICATION.match(line):
            self.saved_row_stack = list(self.stack)
            self.mode = "notification"
            self.stack = [Level("special", "Notification history")]
            self._open_unit(line)
            return

        m = _SCHEDULE.match(line)
        if m and not inline:
            self._start_schedule(m.group(1), m.group(2), line)
            return
        if self.mode == "regs":
            m = _CHAPTER.match(line)
            if m:
                self.chapter, self.chapter_title_pending = f"Chapter {m.group(1)}", True
                return
            if self.chapter_title_pending:
                self.chapter_title_pending = False
                if line.isupper() and not _REGULATION.match(line):
                    self.chapter += f": {line.title()}"
                    return
            m = _REGULATION.match(line)
            if m and not inline:
                number, rest = int(m.group(1)), m.group(2) or ""
                titled = _TITLE_SPLIT.match(rest)
                first = self.stack[0].kind == "special" and titled
                head = titled.group("title") if titled else rest
                tabular = len(re.findall(r"\b\d+(?:\.\d+)?\b", head)) >= 2  # a table row: "2. Above 100 to 500 4 3.5 8"
                if not tabular and (number == self.expected_reg or first
                                    or (self.block and self.stack[0].value == str(number))):
                    self._start_regulation(number, m.group(2) or "")
                    return
        elif self._schedule_line(line):
            return
        self.fresh_page = False
        if self._try_markers(line):
            return
        self._add(line)


def parse_units(regulation: str, pages: list[str]) -> list[Unit]:
    parser = _Parser(regulation)
    for page_no, text in enumerate(pages, start=1):
        for line in text.splitlines():
            parser.feed(page_no, line)
    if parser.block:  # an amendment block the PDF never closed: keep its text as amended text
        parser._end_block()
    return [u for u in parser.units if u.text]


# ------------------------------------------------------------------ units -> chunks

def _split_text(text: str, max_chars: int) -> list[str]:
    if len(text) <= max_chars:
        return [text]
    parts, buf = [], ""
    for piece in re.split(r"(?<=[;.:])\s+(?=\S)", text):
        while len(piece) > max_chars:  # one enormous sentence: cut at a space
            cut = piece.rfind(" ", 0, max_chars)
            cut = cut if cut > max_chars // 2 else max_chars
            if buf:
                parts.append(buf)
                buf = ""
            parts.append(piece[:cut])
            piece = piece[cut:].lstrip()
        if buf and len(buf) + 1 + len(piece) > max_chars:
            parts.append(buf)
            buf = piece
        else:
            buf = f"{buf} {piece}".strip()
    if buf:
        parts.append(buf)
    return parts


def _kind(u: Unit) -> tuple:
    """Units merge only with units of the same standing: original in force, superseded, or one amendment."""
    return u.status, u.amendment, u.block


def _group(units: list[Unit], depth: int, max_chars: int, out: list[list[Unit]]) -> None:
    """A same-standing subtree that fits is one chunk; otherwise recurse one level down."""
    if sum(len(u.text) + 1 for u in units) <= max_chars and len({_kind(u) for u in units}) == 1:
        out.append(units)
        return
    run: list[Unit] = []
    for u in units:
        if len(u.path) <= depth:
            if run:
                _group(run, depth + 1, max_chars, out)
                run = []
            out.append([u])
        elif run and u.path[depth] != run[-1].path[depth]:
            _group(run, depth + 1, max_chars, out)
            run = [u]
        else:
            run.append(u)
    if run:
        _group(run, depth + 1, max_chars, out)


def chunk_document(regulation: str, pages: list[str], *, doc_version: str, source_file: str = "",
                   max_chars: int = 1200) -> list[Chunk]:
    units = parse_units(regulation, pages)
    tops: dict[tuple, list[Unit]] = {}
    for u in units:
        tops.setdefault(u.path[:1], []).append(u)
    groups: list[list[Unit]] = []
    for members in tops.values():
        _group(members, 1, max_chars, groups)

    chunks: list[Chunk] = []
    seen: dict[str, int] = {}
    reg_name = REG_NAMES.get(regulation, regulation)
    for members in sorted(groups, key=lambda g: g[0].order):
        root = min(members, key=lambda u: (len(u.path), u.order))
        if len(members) == 1 and len(root.text) < MIN_HEADING_ONLY_CHARS and any(
                len(o.path) > len(root.path) and o.path[: len(root.path)] == root.path and _kind(o) == _kind(root)
                for o in units):
            continue  # a bare heading ("5. Nutrition claims.-"); it lives on in its sub-clauses' heading_path
        headings = list(root.headings)
        status_note = {"substituted": "Substituted text now in force", "inserted": "Inserted by amendment",
                       "partial": "Amendment to part of this clause"}.get(root.amendment or "")
        if root.status == "superseded":
            status_note = "Superseded original text (replaced or omitted by a later amendment)"
        if status_note:
            headings.append(status_note)
        parts = _split_text(" ".join(u.text for u in members), max_chars)
        extra = {"subclauses": _subclause_spans(members, root)} if len(members) > 1 else {}
        for n, part in enumerate(parts, start=1):
            base = f"{regulation}:{root.clause_id}"
            base += "~superseded" if root.status == "superseded" else (f"~{root.amendment}" if root.amendment else "")
            base += f"#p{n}" if len(parts) > 1 else ""
            seen[base] = seen.get(base, 0) + 1
            passage_id = base if seen[base] == 1 else f"{base}+{seen[base]}"
            label = root.clause_id + (f" (part {n} of {len(parts)})" if len(parts) > 1 else "")
            header = " › ".join([f"{reg_name} ({regulation})", *headings, label])
            chunks.append(Chunk(
                passage_id=passage_id, regulation=regulation, clause_id=root.clause_id, heading_path=headings,
                text=part, doc_version=doc_version, page=root.page, order=len(chunks), status=root.status,
                amendment=root.amendment, effective=root.effective, source_file=source_file,
                embed_text=f"{header}\n{part}", extra=extra))
    return chunks


def _subclause_spans(members: list[Unit], root: Unit) -> dict[str, list[int]]:
    """Where each merged sub-clause sits in the chunk text, so "9(2)" can be looked up inside chunk "9".
    A span runs to the start of the next unit that is not inside it, so it includes its own sub-clauses.
    Only multi-unit chunks have spans, and those are never split into parts (they fit max_chars)."""
    starts, pos = [], 0
    for u in members:
        starts.append(pos)
        pos += len(u.text) + 1
    total = pos - 1
    spans: dict[str, list[int]] = {}
    for i, u in enumerate(members):
        if u is root or u.clause_id == root.clause_id:
            continue
        end = next((starts[j] - 1 for j in range(i + 1, len(members))
                    if members[j].path[: len(u.path)] != u.path), total)
        spans.setdefault(u.clause_id, [starts[i], end])
    return spans
