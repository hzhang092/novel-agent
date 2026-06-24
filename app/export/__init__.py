"""Export pipeline — Markdown concatenation and EPUB generation."""

from __future__ import annotations

import re
from pathlib import Path

from app.storage.project_files import load_all_volumes, load_scene_prose


def export_markdown(project_dir: Path, title: str) -> Path:
    """Concatenate all approved scenes in outline order into a single Markdown file.

    Returns the path to the exported file.
    """
    volumes = load_all_volumes(project_dir)
    if not volumes:
        raise ValueError("No outline data found — create at least one volume with scenes")

    exports_dir = project_dir / "exports"
    exports_dir.mkdir(parents=True, exist_ok=True)

    lines: list[str] = []
    lines.append(f"# {title}")
    lines.append("")

    for vol in volumes:
        for ch in vol.chapters:
            if ch.scenes:
                lines.append(f"## {ch.title}")
                lines.append("")
                for sc in ch.scenes:
                    lines.append(f"### {sc.title}")
                    lines.append("")
                    prose = load_scene_prose(project_dir, ch.id, sc.id)
                    if prose.strip():
                        lines.append(prose.strip())
                    else:
                        lines.append("*（此场景尚未生成）*")
                    lines.append("")
                lines.append("")

    output_path = exports_dir / f"{title}.md"
    output_path.write_text("\n".join(lines), encoding="utf-8")
    return output_path


def export_epub(project_dir: Path, title: str, author: str = "") -> Path:
    """Generate an EPUB file from all approved scenes.

    Requires ``ebooklib`` (pip install ebooklib).

    Returns the path to the exported file.
    """
    from ebooklib import epub

    volumes = load_all_volumes(project_dir)
    if not volumes:
        raise ValueError("No outline data found")

    exports_dir = project_dir / "exports"
    exports_dir.mkdir(parents=True, exist_ok=True)

    book = epub.EpubBook()
    book.set_identifier(f"novelforge-{title}")
    book.set_title(title)
    book.set_language("zh")
    if author:
        book.add_author(author)

    # Minimal CSS for Chinese readability
    css = epub.EpubItem(
        uid="style",
        file_name="style/default.css",
        media_type="text/css",
        content=(
            "body { font-family: serif; line-height: 1.8; margin: 2em; }\n"
            "h1 { text-align: center; font-size: 1.6em; margin-bottom: 2em; }\n"
            "h2 { font-size: 1.3em; margin-top: 2em; }\n"
            "h3 { font-size: 1.1em; margin-top: 1.5em; }\n"
            "p { text-indent: 2em; margin: 0.5em 0; }\n"
        ),
    )
    book.add_item(css)

    # Title page
    title_page = epub.EpubHtml(
        title="扉页", file_name="title.xhtml", lang="zh"
    )
    title_page.content = (
        f"<html><body>"
        f"<h1>{title}</h1>"
        f"{'<p style=\"text-align:center;\">' + author + '</p>' if author else ''}"
        f"</body></html>"
    )
    book.add_item(title_page)

    spine = ["nav"]
    toc = []

    chapter_items = []
    for vol in volumes:
        for ch in vol.chapters:
            if not ch.scenes:
                continue

            ch_lines: list[str] = []
            ch_lines.append(f"<h2>{ch.title}</h2>")

            for sc in ch.scenes:
                prose = load_scene_prose(project_dir, ch.id, sc.id)
                if not prose.strip():
                    continue
                ch_lines.append(f"<h3>{sc.title}</h3>")
                for para in prose.strip().split("\n"):
                    para = para.strip()
                    if para:
                        ch_lines.append(f"<p>{para}</p>")

            if len(ch_lines) <= 1:
                continue

            ch_id = f"chapter_{ch.id}"
            ch_item = epub.EpubHtml(
                title=ch.title, file_name=f"{ch_id}.xhtml", lang="zh"
            )
            ch_item.content = (
                "<html><body>\n" + "\n".join(ch_lines) + "\n</body></html>"
            )
            ch_item.add_item(css)
            book.add_item(ch_item)
            chapter_items.append(ch_item)
            spine.append(ch_item)
            toc.append(epub.Link(f"{ch_id}.xhtml", ch.title, ch_id))

    if not chapter_items:
        raise ValueError("No generated scene prose found — generate at least one scene first")

    book.toc = toc
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    book.spine = ["nav"] + spine

    safe_title = re.sub(r"[^\w\s-]", "", title).strip()
    output_path = exports_dir / f"{safe_title}.epub"
    epub.write_epub(str(output_path), book)
    return output_path
