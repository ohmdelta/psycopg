"""
psycopg row factories
"""

# Copyright (C) 2021 The Psycopg Team

import re
import functools
from typing import Any, Dict, NamedTuple, NoReturn, Sequence, Tuple
from typing import TYPE_CHECKING, Type, TypeVar
from collections import namedtuple

from . import errors as e
from .compat import Protocol

if TYPE_CHECKING:
    from .cursor import BaseCursor, Cursor, AsyncCursor

T = TypeVar("T")

# Row factories

Row = TypeVar("Row")
Row_co = TypeVar("Row_co", covariant=True)


class RowMaker(Protocol[Row_co]):
    """
    Callable protocol taking a sequence of value and returning an object.

    The sequence of value is what is returned from a database query, already
    adapted to the right Python types. The return value is the object that your
    program would like to receive: by default (`tuple_row()`) it is a simple
    tuple, but it may be any type of object.

    Typically, `!RowMaker` functions are returned by `RowFactory`.
    """

    def __call__(self, __values: Sequence[Any]) -> Row_co:
        ...


class RowFactory(Protocol[Row]):
    """
    Callable protocol taking a `~psycopg.Cursor` and returning a `RowMaker`.

    A `!RowFactory` is typically called when a `!Cursor` receives a result.
    This way it can inspect the cursor state (for instance the
    `~psycopg.Cursor.description` attribute) and help a `!RowMaker` to create
    a complete object.

    For instance the `dict_row()` `!RowFactory` uses the names of the column to
    define the dictionary key and returns a `!RowMaker` function which would
    use the values to create a dictionary for each record.
    """

    def __call__(self, __cursor: "Cursor[Row]") -> RowMaker[Row]:
        ...


class AsyncRowFactory(Protocol[Row]):
    """
    Callable protocol taking an `~psycopg.AsyncCursor` and returning a `RowMaker`.
    """

    def __call__(self, __cursor: "AsyncCursor[Row]") -> RowMaker[Row]:
        ...


TupleRow = Tuple[Any, ...]
"""
An alias for the type returned by `tuple_row()` (i.e. a tuple of any content).
"""


DictRow = Dict[str, Any]
"""
An alias for the type returned by `dict_row()`

A `!DictRow` is a dictionary with keys as string and any value returned by the
database.
"""


def tuple_row(cursor: "BaseCursor[Any, TupleRow]") -> RowMaker[TupleRow]:
    r"""Row factory to represent rows as simple tuples.

    This is the default factory.
    """
    # Implementation detail: make sure this is the tuple type itself, not an
    # equivalent function, because the C code fast-paths on it.
    return tuple


def dict_row(cursor: "BaseCursor[Any, DictRow]") -> RowMaker[DictRow]:
    """Row factory to represent rows as dicts.

    Note that this is not compatible with the DBAPI, which expects the records
    to be sequences.
    """
    desc = cursor.description
    if desc is not None:
        titles = [c.name for c in desc]

        def dict_row_(values: Sequence[Any]) -> Dict[str, Any]:
            return dict(zip(titles, values))

        return dict_row_

    else:
        return no_result


def namedtuple_row(
    cursor: "BaseCursor[Any, NamedTuple]",
) -> RowMaker[NamedTuple]:
    """Row factory to represent rows as `~collections.namedtuple`."""
    desc = cursor.description
    if desc is not None:
        nt = _make_nt(*(c.name for c in desc))
        return nt._make

    else:
        return no_result


# ascii except alnum and underscore
_re_clean = re.compile(
    "[" + re.escape(" !\"#$%&'()*+,-./:;<=>?@[\\]^`{|}~") + "]"
)


@functools.lru_cache(512)
def _make_nt(*key: str) -> Type[NamedTuple]:
    fields = []
    for s in key:
        s = _re_clean.sub("_", s)
        # Python identifier cannot start with numbers, namedtuple fields
        # cannot start with underscore. So...
        if s[0] == "_" or "0" <= s[0] <= "9":
            s = "f" + s
        fields.append(s)
    return namedtuple("Row", fields)  # type: ignore[return-value]


def no_result(values: Sequence[Any]) -> NoReturn:
    """A `RowMaker` that always fail.

    It can be used as return value for a `RowFactory` called with no result.
    Note that the `!RowFactory` *will* be called with no result, but the
    resulting `!RowMaker` never should.
    """
    raise e.InterfaceError("the cursor doesn't have a result")
