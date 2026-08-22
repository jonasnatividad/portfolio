# All Jammed Up — Festival Site

Client project: a single-page site for **All Jammed Up**, a music festival + podcast based in Asheville, NC. Delivered as a static site with event details, an embedded venue map, a Spotify podcast episode embed, and social links — deployed via GitHub Pages on a custom domain.

The festival this page was built for has since passed and the domain is no longer active; the event section here reflects that (shown as a past event rather than a live countdown).

---

## Repo Structure

```
all_jammed_up_festival_site/
├── README.md
├── index.html            # Single-page site
└── all_jammed_up_logo.png
```

---

## Key Technical Decisions

**Single static HTML file, no build step** — For a small single-event site, plain HTML/CSS/JS deployed via GitHub Pages was the right scope: no framework overhead, fast to ship, trivial to hand off.

**Embeds over custom integrations** — The venue map (Google Maps) and podcast episode (Spotify) are iframe embeds rather than custom API integrations, keeping the site maintenance-free after launch.

**Countdown/ticket CTA removed post-event** — The original build included a live JS countdown timer and ticket purchase CTA tied to the event date; both were removed once the event passed rather than left showing stale/broken state.
