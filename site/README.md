# Copyist website

Static public site for GitHub Pages: what Copyist is, its features, how to install it, and how to make music (`copyist serve`, write, build).

- Source: this folder (`site/`)
- Live URL: https://copyist.digitaldefiance.org/ (`site/CNAME`)
- Deploy: `.github/workflows/pages.yml` publishes `site/` on every push to `main` that touches these files

Open `index.html` in a browser to preview locally. Asset paths are relative.

Fonts are Instrument Serif / Instrument Sans (display and UI) with Source Serif 4 (body), all SIL OFL, bundled so the site never fetches from a CDN — same faces as `copyist serve`.
