"""Isolated PDF extraction worker; keep imports here independent of api.main."""

import io


def extract_pdf_worker(data: bytes, connection, max_pages: int) -> None:
    try:
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(data))
        if len(reader.pages) > max_pages:
            connection.send((False, "page_limit"))
            return
        connection.send((True, "\n".join(page.extract_text() or "" for page in reader.pages)))
    except Exception as exc:
        try:
            connection.send((False, f"{type(exc).__name__}: {exc}"))
        except (BrokenPipeError, EOFError, OSError):
            pass
    finally:
        connection.close()
