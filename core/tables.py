"""Shared state for admin list tables: sort, pagination, URL-preserved filters.

Pages call `build_table` and keep writing their own rows. Sort keys are
whitelisted per page; a bad `sort`, `page` or filter value is ignored or
clamped, never an error (audit F10).
"""

from dataclasses import dataclass
from urllib.parse import urlencode

from django.core.paginator import Paginator

PER_PAGE = 25
_RESERVED = ("sort", "page")
_WINDOW = 2


@dataclass(frozen=True)
class Column:
    label: str
    key: str | None = None  # URL token; None = not sortable
    ordering: tuple = ()  # ascending ORM ordering
    descending: tuple | None = None  # override when a tiebreak must not flip
    action: bool = False  # blank-label action column

    @property
    def sortable(self):
        return bool(self.key and self.ordering)

    def order_by(self, desc):
        if not desc:
            return self.ordering
        if self.descending is not None:
            return self.descending
        return tuple(f[1:] if f.startswith("-") else f"-{f}" for f in self.ordering)


@dataclass(frozen=True)
class Header:
    label: str
    sortable: bool
    action: bool
    url: str
    aria_sort: str


@dataclass
class Table:
    page: object
    paginator: object
    headers: list
    count_text: str
    sorted_by: str
    filtered: bool
    clear_url: str
    prev_url: str
    next_url: str
    page_links: list


def parse_choice(request, name, choices):
    """The GET value if it is an allowed choice value, else ''."""
    value = request.GET.get(name, "")
    return value if value in {choice for choice, _ in choices} else ""


def _query(params, **extra):
    data = {**params, **{k: v for k, v in extra.items() if v not in (None, "")}}
    return "?" + urlencode(data)


def build_table(request, queryset, columns, default_sort, per_page=PER_PAGE):
    sortable = {column.key: column for column in columns if column.sortable}
    raw = request.GET.get("sort", "")
    desc = raw.startswith("-")
    key = raw[1:] if desc else raw
    if key not in sortable:
        desc = default_sort.startswith("-")
        key = default_sort[1:] if desc else default_sort
    active = sortable[key]
    token = f"-{key}" if desc else key

    params = {k: v for k, v in request.GET.items() if v and k not in _RESERVED}

    ordered = queryset.order_by(*active.order_by(desc), "pk")
    paginator = Paginator(ordered, per_page)
    page = paginator.get_page(request.GET.get("page"))

    headers = []
    for column in columns:
        if column.sortable:
            is_active = column.key == key
            next_token = f"-{column.key}" if is_active and not desc else column.key
            aria = ("descending" if desc else "ascending") if is_active else ""
            headers.append(
                Header(column.label, True, column.action, _query(params, sort=next_token), aria)
            )
        else:
            headers.append(Header(column.label, False, column.action, "", ""))

    total = paginator.count
    count_text = (
        f"Showing {page.start_index()}–{page.end_index()} of {total}" if total else "No results"
    )
    page_links = [
        {
            "number": number,
            "url": _query(params, sort=token, page=number),
            "current": number == page.number,
        }
        for number in paginator.page_range
        if abs(number - page.number) <= _WINDOW
    ]
    return Table(
        page=page,
        paginator=paginator,
        headers=headers,
        count_text=count_text,
        sorted_by=f"{active.label}, {'descending' if desc else 'ascending'}",
        filtered=bool(params),
        clear_url=request.path,
        prev_url=_query(params, sort=token, page=page.previous_page_number())
        if page.has_previous()
        else "",
        next_url=_query(params, sort=token, page=page.next_page_number())
        if page.has_next()
        else "",
        page_links=page_links,
    )
