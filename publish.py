#!/usr/bin/env python3
"""
RTF-to-blog-post publishing script.

Converts .rtf files in rtf_drafts/<channel>/ into HTML blog posts in the
corresponding posts directory, updating each channel's index.json automatically.

Channels:
    rtf_drafts/science/  ->  science_posts/   (science.html)
    rtf_drafts/coffee/   ->  coffee_posts/    (coffee.html)
    rtf_drafts/misc/     ->  blog_posts/      (misc_posts.html)

Usage:
    python3 publish.py              # convert new/changed RTF files (all channels)
    python3 publish.py --channel science   # only process one channel
    python3 publish.py --force      # re-process all RTF files
    python3 publish.py --dry-run    # preview without writing files

Only uses the Python standard library — no pip dependencies.
"""

import argparse
import hashlib
import json
import os
import re
import sys
from datetime import date


# ---------------------------------------------------------------------------
# RTF Parser
# ---------------------------------------------------------------------------

# Destinations whose content should be skipped entirely
_IGNORABLE_DESTINATIONS = frozenset([
    'fonttbl', 'colortbl', 'stylesheet', 'pict', 'info',
    'header', 'footer', 'headerl', 'headerr', 'headerf',
    'footerl', 'footerr', 'footerf', 'object', 'shp',
    'shpinst', 'shprslt', 'blipuid', 'fldinst', 'mmathPr',
    'generator', 'datastore', 'themedata', 'colorschememapping',
    'latentstyles', 'datafield', 'pntxta', 'pntxtb',
    'listtable', 'listoverridetable', 'revtbl', 'rsidtbl',
    'pgdsctbl', 'xmlnstbl',
])


class RTFParser:
    """Lightweight RTF-to-HTML converter using only the standard library."""

    def __init__(self, raw: bytes):
        self.raw = raw
        self.pos = 0
        self.text_runs: list[tuple[str, dict]] = []  # (text, formatting_state)
        self.encoding = 'cp1252'

    # -- tokeniser helpers --------------------------------------------------

    def _peek(self) -> int | None:
        if self.pos < len(self.raw):
            return self.raw[self.pos]
        return None

    def _read(self) -> int | None:
        if self.pos < len(self.raw):
            b = self.raw[self.pos]
            self.pos += 1
            return b
        return None

    def _read_control_word(self) -> tuple[str, int | None]:
        """Read a control word (after the backslash). Returns (word, param)."""
        word = []
        while self.pos < len(self.raw) and self.raw[self.pos:self.pos+1].isalpha():
            word.append(chr(self.raw[self.pos]))
            self.pos += 1
        name = ''.join(word)
        # optional numeric parameter (may be negative)
        param = None
        if self.pos < len(self.raw) and (self.raw[self.pos:self.pos+1].isdigit() or self.raw[self.pos:self.pos+1] == b'-'):
            digits = []
            if self.raw[self.pos:self.pos+1] == b'-':
                digits.append('-')
                self.pos += 1
            while self.pos < len(self.raw) and self.raw[self.pos:self.pos+1].isdigit():
                digits.append(chr(self.raw[self.pos]))
                self.pos += 1
            param = int(''.join(digits))
        # a space delimiter is consumed but not emitted
        if self.pos < len(self.raw) and self.raw[self.pos:self.pos+1] == b' ':
            self.pos += 1
        return name, param

    # -- main parse ---------------------------------------------------------

    def parse(self) -> str:
        """Parse the RTF and return body HTML."""
        fmt_stack: list[dict] = []
        fmt: dict = {'b': False, 'i': False, 'ul': False}
        skip_depth = 0  # > 0 means we are inside an ignorable destination
        group_depth = 0

        while self.pos < len(self.raw):
            ch = self._read()
            if ch is None:
                break

            # -- group open --
            if ch == ord('{'):
                group_depth += 1
                fmt_stack.append(dict(fmt))
                if skip_depth > 0:
                    skip_depth += 1
                continue

            # -- group close --
            if ch == ord('}'):
                group_depth -= 1
                if fmt_stack:
                    fmt = fmt_stack.pop()
                if skip_depth > 0:
                    skip_depth -= 1
                continue

            # skip content inside ignorable destinations
            if skip_depth > 0:
                continue

            # -- control sequence --
            if ch == ord('\\'):
                nxt = self._peek()
                if nxt is None:
                    continue

                # hex escape \'XX
                if nxt == ord("'"):
                    self.pos += 1  # consume '
                    hex_chars = self.raw[self.pos:self.pos+2]
                    self.pos += 2
                    try:
                        byte_val = bytes([int(hex_chars, 16)])
                        decoded = byte_val.decode(self.encoding, errors='replace')
                        self.text_runs.append((decoded, dict(fmt)))
                    except (ValueError, UnicodeDecodeError):
                        pass
                    continue

                # escaped literal: \{ \} \\
                if nxt in (ord('{'), ord('}'), ord('\\')):
                    self.pos += 1
                    self.text_runs.append((chr(nxt), dict(fmt)))
                    continue

                # \<cr> and \<lf> are paragraph breaks (equivalent to \par)
                if nxt in (ord('\r'), ord('\n')):
                    self.pos += 1
                    self.text_runs.append(('\n', dict(fmt)))
                    continue

                # control symbol (non-alpha after backslash)
                if not (nxt and chr(nxt).isalpha()):
                    self.pos += 1
                    # \* marks an ignorable destination
                    if nxt == ord('*'):
                        skip_depth = 1
                    # \~ = non-breaking space, \- = soft hyphen, \_ = non-breaking hyphen
                    elif nxt == ord('~'):
                        self.text_runs.append(('\u00A0', dict(fmt)))
                    elif nxt == ord('-'):
                        self.text_runs.append(('\u00AD', dict(fmt)))
                    elif nxt == ord('_'):
                        self.text_runs.append(('\u2011', dict(fmt)))
                    continue

                # control word
                word, param = self._read_control_word()

                # encoding
                if word == 'ansicpg' and param is not None:
                    try:
                        import codecs
                        codecs.lookup(f'cp{param}')
                        self.encoding = f'cp{param}'
                    except LookupError:
                        pass
                    continue

                # ignorable destinations
                if word in _IGNORABLE_DESTINATIONS:
                    skip_depth = 1
                    continue

                # paragraph / line break
                if word == 'par' or word == 'line':
                    self.text_runs.append(('\n', dict(fmt)))
                    continue

                # tab
                if word == 'tab':
                    self.text_runs.append(('\t', dict(fmt)))
                    continue

                # unicode escape \uN
                if word == 'u' and param is not None:
                    code_point = param if param >= 0 else param + 65536
                    try:
                        self.text_runs.append((chr(code_point), dict(fmt)))
                    except (ValueError, OverflowError):
                        pass
                    # skip the replacement character(s) — typically one byte
                    if self.pos < len(self.raw) and self.raw[self.pos:self.pos+1] == b'?':
                        self.pos += 1
                    continue

                # formatting toggles
                if word == 'b':
                    fmt['b'] = (param != 0) if param is not None else True
                elif word == 'i':
                    fmt['i'] = (param != 0) if param is not None else True
                elif word == 'ul':
                    fmt['ul'] = True
                elif word == 'ulnone':
                    fmt['ul'] = False
                elif word == 'plain':
                    fmt = {'b': False, 'i': False, 'ul': False}

                continue

            # -- plain text --
            # skip \r and \n in body (not significant in RTF)
            if ch in (0x0D, 0x0A):
                continue

            self.text_runs.append((chr(ch), dict(fmt)))

        return self._runs_to_html()

    def _runs_to_html(self) -> str:
        """Convert text runs into paragraph-wrapped HTML."""
        if not self.text_runs:
            return ''

        # merge runs into a single string, preserving formatting boundaries
        # first, group consecutive runs with same formatting
        merged: list[tuple[str, dict]] = []
        for text, fmt in self.text_runs:
            if merged and merged[-1][1] == fmt:
                merged[-1] = (merged[-1][0] + text, fmt)
            else:
                merged.append((text, fmt))

        # build paragraphs
        paragraphs: list[str] = []
        current_parts: list[str] = []

        for text, fmt in merged:
            # split on paragraph breaks
            segments = text.split('\n')
            for idx, seg in enumerate(segments):
                if seg:
                    escaped = _html_escape(seg)
                    wrapped = _wrap_formatting(escaped, fmt)
                    current_parts.append(wrapped)
                if idx < len(segments) - 1:
                    # paragraph break
                    para_text = ''.join(current_parts).strip()
                    if para_text:
                        paragraphs.append(para_text)
                    current_parts = []

        # flush remaining
        para_text = ''.join(current_parts).strip()
        if para_text:
            paragraphs.append(para_text)

        return '\n'.join(f'    <p>{p}</p>' for p in paragraphs)


def _html_escape(text: str) -> str:
    return (text
            .replace('&', '&amp;')
            .replace('<', '&lt;')
            .replace('>', '&gt;')
            .replace('"', '&quot;'))


def _wrap_formatting(html: str, fmt: dict) -> str:
    if fmt.get('b'):
        html = f'<strong>{html}</strong>'
    if fmt.get('i'):
        html = f'<em>{html}</em>'
    if fmt.get('ul'):
        html = f'<u>{html}</u>'
    return html


def _strip_html(html: str) -> str:
    """Remove HTML tags and collapse whitespace."""
    text = re.sub(r'<[^>]+>', '', html)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


# ---------------------------------------------------------------------------
# Blog Post Generator
# ---------------------------------------------------------------------------

_POST_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <style>
        body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; line-height: 1.7; padding: 20px; max-width: 800px; margin: 0 auto; }}
        a {{ color: #EE2835; text-decoration: none; }}
        a:hover {{ text-decoration: underline; }}
        h1 {{ color: #333; margin-bottom: 10px; }}
        .meta {{ color: #777; margin-bottom: 20px; }}
    </style>
</head>
<body>
    <a href="../{back_link}">&larr; Back to Posts</a>
    <h1>{title}</h1>
    <div class="meta">Published on {date_display}</div>
{body}
</body>
</html>
"""


class BlogPostGenerator:
    """Generates a blog post HTML file from a title and body HTML."""

    @staticmethod
    def generate(title: str, body_html: str, pub_date: date, back_link: str = 'posts.html') -> str:
        date_display = pub_date.strftime('%B %-d, %Y')
        return _POST_TEMPLATE.format(
            title=_html_escape(title),
            date_display=date_display,
            body=body_html,
            back_link=back_link,
        )


# ---------------------------------------------------------------------------
# Channel definitions
# ---------------------------------------------------------------------------

# Each channel maps an RTF drafts subfolder to a posts output directory
# and the listing page that links back from individual posts.
CHANNELS = [
    {'name': 'science', 'drafts_subdir': 'science', 'posts_dir': 'science_posts', 'listing_page': 'science.html'},
    {'name': 'coffee',  'drafts_subdir': 'coffee',  'posts_dir': 'coffee_posts',  'listing_page': 'coffee.html'},
    {'name': 'misc',    'drafts_subdir': 'misc',    'posts_dir': 'blog_posts',    'listing_page': 'misc_posts.html'},
]


# ---------------------------------------------------------------------------
# Publish Pipeline
# ---------------------------------------------------------------------------

class PublishPipeline:
    """Orchestrates RTF → HTML blog post conversion for a single channel."""

    def __init__(self, project_root: str, channel: dict, *, force: bool = False, dry_run: bool = False):
        self.project_root = project_root
        self.channel = channel
        self.drafts_dir = os.path.join(project_root, 'rtf_drafts', channel['drafts_subdir'])
        self.posts_dir = os.path.join(project_root, channel['posts_dir'])
        self.index_path = os.path.join(self.posts_dir, 'index.json')
        self.published_path = os.path.join(self.drafts_dir, '.published.json')
        self.force = force
        self.dry_run = dry_run

    def run(self) -> int:
        """Process RTF files for this channel. Returns number processed."""
        if not os.path.isdir(self.drafts_dir):
            print(f'  No directory found at {self.drafts_dir} — skipping')
            return 0

        rtf_files = sorted(
            f for f in os.listdir(self.drafts_dir)
            if f.lower().endswith('.rtf')
        )

        if not rtf_files:
            print(f'  No .rtf files found')
            return 0

        published = self._load_published()
        index = self._load_index()
        processed = 0

        for filename in rtf_files:
            filepath = os.path.join(self.drafts_dir, filename)
            raw = open(filepath, 'rb').read()
            content_hash = hashlib.sha256(raw).hexdigest()

            if not self.force and published.get(filename) == content_hash:
                print(f'    skip (unchanged): {filename}')
                continue

            print(f'    processing: {filename}')

            parser = RTFParser(raw)
            body_html = parser.parse()

            title = self._extract_title(filename)
            slug = self._slugify(title)
            html_filename = f'{slug}.html'
            pub_date = date.today()

            full_html = BlogPostGenerator.generate(
                title, body_html, pub_date,
                back_link=self.channel['listing_page'],
            )

            plain_text = _strip_html(body_html)
            excerpt = plain_text[:200].rsplit(' ', 1)[0] + '...' if len(plain_text) > 200 else plain_text

            posts_dir_name = self.channel['posts_dir']
            if self.dry_run:
                print(f'      [dry-run] would write: {posts_dir_name}/{html_filename}')
                print(f'      [dry-run] title: {title}')
                print(f'      [dry-run] excerpt: {excerpt[:80]}...')
            else:
                os.makedirs(self.posts_dir, exist_ok=True)
                out_path = os.path.join(self.posts_dir, html_filename)
                with open(out_path, 'w', encoding='utf-8') as f:
                    f.write(full_html)
                print(f'      wrote: {posts_dir_name}/{html_filename}')

                self._upsert_index(index, title, pub_date, excerpt, html_filename)
                published[filename] = content_hash

            processed += 1

        if not self.dry_run and processed > 0:
            self._save_index(index)
            self._save_published(published)

        return processed

    @staticmethod
    def _extract_title(filename: str) -> str:
        """Extract title from the RTF filename (minus extension)."""
        return os.path.splitext(filename)[0]

    @staticmethod
    def _slugify(title: str) -> str:
        slug = title.lower().strip()
        slug = re.sub(r'[^\w\s-]', '', slug)
        slug = re.sub(r'[\s_]+', '-', slug)
        slug = re.sub(r'-+', '-', slug)
        return slug.strip('-')[:80]

    def _load_published(self) -> dict:
        if os.path.exists(self.published_path):
            with open(self.published_path, 'r') as f:
                return json.load(f)
        return {}

    def _save_published(self, data: dict) -> None:
        with open(self.published_path, 'w') as f:
            json.dump(data, f, indent=2)

    def _load_index(self) -> dict:
        if os.path.exists(self.index_path):
            with open(self.index_path, 'r') as f:
                return json.load(f)
        return {'posts': []}

    def _save_index(self, index: dict) -> None:
        with open(self.index_path, 'w', encoding='utf-8') as f:
            json.dump(index, f, indent=2, ensure_ascii=False)
            f.write('\n')

    def _upsert_index(self, index: dict, title: str, pub_date: date, excerpt: str, html_filename: str) -> None:
        posts_dir_name = self.channel['posts_dir']
        url = f'{posts_dir_name}/{html_filename}'
        entry = {
            'title': title,
            'date': pub_date.isoformat(),
            'excerpt': excerpt,
            'url': url,
            'source': 'publish.py',
        }
        # replace existing entry for the same url, or append
        for i, post in enumerate(index['posts']):
            if post.get('url') == url:
                index['posts'][i] = entry
                return
        index['posts'].append(entry)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    channel_names = [ch['name'] for ch in CHANNELS]
    parser = argparse.ArgumentParser(
        description='Convert RTF drafts in rtf_drafts/<channel>/ to blog posts.'
    )
    parser.add_argument('--force', action='store_true',
                        help='Re-process all RTF files, even unchanged ones')
    parser.add_argument('--dry-run', action='store_true',
                        help='Preview what would happen without writing files')
    parser.add_argument('--channel', choices=channel_names, default=None,
                        help='Only process a specific channel (default: all)')
    args = parser.parse_args()

    project_root = os.path.dirname(os.path.abspath(__file__))

    channels_to_run = CHANNELS
    if args.channel:
        channels_to_run = [ch for ch in CHANNELS if ch['name'] == args.channel]

    total_processed = 0
    total_skipped = 0

    for channel in channels_to_run:
        print(f'\n[{channel["name"]}] rtf_drafts/{channel["drafts_subdir"]}/ -> {channel["posts_dir"]}/')
        pipeline = PublishPipeline(project_root, channel, force=args.force, dry_run=args.dry_run)
        processed = pipeline.run()
        total_processed += processed

    action = 'previewed' if args.dry_run else 'published'
    print(f'\nDone — {total_processed} post(s) {action}.')


if __name__ == '__main__':
    main()
