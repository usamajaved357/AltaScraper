"""domain/sheets.py -- writing a spreadsheet a person is going to open and edit.

ONE CSV WRITER, because there are now two things that hand someone a sheet to
fill in -- supplier links for the repricer, and costs -- and a third would have
been the point at which they started disagreeing about quoting or the BOM.

It knows nothing about suppliers or costs. What goes IN a template belongs to
whichever module owns that subject (domain/source_bulk.py, domain/cogs.py); this
one only knows how to write it so Excel opens it correctly.
"""
import csv
import io


def to_csv(headers, rows):
    """A CSV string, with a leading BOM so Excel reads it as UTF-8.

    Without the BOM, double-clicking the file in Excel on Windows decodes it as
    the system codepage, and a product name carrying a pound sign or an accent
    comes out as mojibake -- then gets uploaded back that way.

    The BOM is written as the escape \\ufeff and never as the character itself. A
    literal byte-order mark sitting in the middle of a source file is invisible
    in an editor and breaks the next tool that reads it; test_encoding.js checks
    for exactly that, and caught this line when it was first written the other
    way round.

    Rows are written through csv.writer rather than joined with commas, so a
    product name containing a comma or a quote is quoted properly instead of
    silently becoming two columns.
    """
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(list(headers or []))
    for r in (rows or []):
        w.writerow(list(r))
    return "\ufeff" + buf.getvalue()


def pick(headers, wanted):
    """The index of the first column whose name looks like one of `wanted`, or -1.

    The matcher a template is checked against, so a template cannot ship with a
    header its own upload would fail to find. domain/source_bulk.py owns the
    canonical implementation and its own column-name lists; this delegates so
    there is one behaviour rather than two that drift.
    """
    from domain import source_bulk as _sb
    return _sb._pick(headers, wanted)
