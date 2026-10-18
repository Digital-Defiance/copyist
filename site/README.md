# Copyist website

Static public site for GitHub Pages: what Copyist is, its features, and how to install it.

- Source: this folder (`site/`)
- Live URL: https://copyist.digitaldefiance.org/ (`site/CNAME`)
- Deploy: `.github/workflows/pages.yml` publishes `site/` on every push to `main` that touches these files

Open `index.html` in a browser to preview locally. Asset paths are relative.

Fonts match the local app (Source Serif 4 and Shantell Sans, SIL OFL) and are bundled here so the site never fetches from a CDN.
