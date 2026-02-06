# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Static personal website and blog for Dexter Crowley. Built with plain HTML5, CSS3, and vanilla JavaScript — no frameworks, no build tools, no external dependencies.

## Running Locally

Open `index.html` directly in a browser, or use a local server for proper JSON fetch behavior:

```bash
python3 -m http.server 8000
```

Jekyll is also configured but optional:

```bash
bundle exec jekyll serve   # serves at localhost:4000
```

## Architecture

**Pages:** `index.html` (homepage), `posts.html` (blog listing), `blog_posts/*.html` (individual posts)

**Blog system:** `posts.html` fetches `blog_posts/index.json` at runtime and renders post cards client-side with JavaScript. Posts are standalone HTML files in `blog_posts/`. The JSON manifest drives the listing — posts won't appear unless registered there.

**Adding a blog post:**
1. Create an HTML file in `blog_posts/` (use `post-template.html` as a starting point)
2. Add an entry to `blog_posts/index.json` with title, date, excerpt, and url
3. Posts sort by date automatically (newest first)

**Styling:** All CSS is embedded in `<style>` tags within each HTML file (no external stylesheets). The design uses a blue-to-teal gradient (`#04529D` → `#3A6963`) with glassmorphism effects (backdrop-filter blur). Red `#EE2835` for headings/CTAs, coral `#ED8171` for accents.

**Assets:** Static images live in `assets/images/` (e.g., profile headshot). This directory is served correctly by both Jekyll/GitHub Pages and simple HTTP servers.

**RTF publishing:** Drop `.rtf` files into `rtf_drafts/` and run `python3 publish.py` to auto-convert them into blog posts. The script generates HTML in `blog_posts/` and updates `index.json`. Supports `--dry-run` (preview) and `--force` (re-process all). Uses only the Python standard library. Processed files are tracked via `rtf_drafts/.published.json` (gitignored).

**Configuration:** `_data/main_info.yaml` holds site metadata, contact info, social links, and navigation structure. `_config.yml` is for Jekyll if used.

## Key Patterns

- CSS-in-HTML: each page is self-contained with embedded styles
- Client-side rendering: posts.html uses fetch() with multiple path fallbacks for different hosting environments
- Responsive breakpoint at 768px
- No build step — files are served as-is
