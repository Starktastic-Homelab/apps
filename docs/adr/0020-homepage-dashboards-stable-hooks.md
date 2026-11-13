# ADR 0020: Homepage dashboards on stable hooks with a render check

- **Status:** Proposed
- **Date:** 2026-11-13

## Context

Sub-project 4 replaces both Homepage pages with the design Ben picked on 2026-11-07: "Liquid glass" with an
alarm mode, an admin Pulse board (an alert list and health cards) and a phone-first household page. Both pages
are rendered from `homepage/catalog.yaml` (ADR 0019). Three things were open: how much of the prototype's
content ships at the cut-over, how its CSS survives Homepage upgrades, and what the alarm colours mean. Homepage
bumps are merged by hand since #1552, and nothing in CI rendered either page. Design:
[docs/superpowers/specs/2026-11-13-homepage-new-dashboards-design.md](../superpowers/specs/2026-11-13-homepage-new-dashboards-design.md).

## Decision

1. **Content at the cut-over.** Both pages take the prototype's tabs and groups. Admin keeps every host and
   widget it has today, merges readout-and-launcher twins into one tile per app, and gains the Pulse board and
   four header chips. A new query ships only if Git proves its metric: a rule, probe or tile in the repo
   already uses it, or it is a core metric of a component `kube-prometheus-stack/values.yaml` scrapes. Household
   keeps its 21 tiles, shows the calendar as an agenda and gains an Internet chip (a fixed-query `customapi` on
   Prometheus, no credential). Everything else in the research arrives afterwards in small PRs.
2. **Household credentials plug in.** A household widget appears when its `_HOUSEHOLD` credential is sealed
   (ADR 0018): first Calibre-Web's user and a non-admin Jellyfin user's token. The Jellyfin lists are tiles of
   their own, shown on both pages on that token. No credential blocks the cut-over.
3. **Hook rule.** `custom.css` selects Homepage's ids, its named classes (`service-card`, `service-block`,
   `services-group`, `information-widget-<type>`, ...), its data and ARIA attributes, and catalog tile ids. No
   Tailwind utility class. No selector carries meaning by position. Where Homepage offers no hook (rows inside
   list widgets, the calendar agenda, the phone search button), structural selectors live in one block marked
   `/* no-hook */`. Per-tab rules select through a common ancestor, not a sibling combinator. The generator
   enforces the static half of this rule. No `custom.js`.
4. **Render check.** `scripts/homepage/rendercheck/`, as the `homepage-render` job in `validate-and-diff.yml`, runs
   the deployed Homepage image digest on the generated pages against a mock upstream, calm and alarm, phone and
   desktop. It fails when an `--inventory` tile, tab or group is missing from the DOM, a widget or page shows an
   error, a CSS selector matches nothing, an image fails to load, or a household phone target is under 44 px.
   It is a required status check and passes without running when its paths are untouched.
5. **Alarm colours.** On admin a block is red exactly where a critical alert rule in Git would fire and amber
   where a warning rule would; the spec lists the few thresholds no rule covers. Red appears nowhere else.
   Household has no alarm mode.
6. **Cut-over.** Three PRs: content and the render check (removing `--compare`, which freezes both live pages
   until their cut-over), then household, then admin. During the freeze a PR that adds an app edits the live
   page and the catalog, because the coverage check reads the live pages.

## Rationale

- The picked prototype is a board with content. Today's tiles in glass would ship the material without the
  page; every research widget at once would put about a hundred unproven endpoints into one cut-over. Git-proven
  data gives the Pulse board at the cut-over with bounded risk.
- The prototype's CSS has no Tailwind-class selectors, and four fifths of its selectors already sit on stable
  hooks (105 of 130 on household, 150 of 174 on admin), so it is kept and repaired, not rewritten.
- A selector that matches nothing is how a CSS break shows, so "every selector matches in some run" is a cheap
  general test. It cannot see a positional selector that still matches the wrong thing, which is why those are
  banned outright and the no-hook block is limited to cosmetic damage.
- Ben chose "stable hooks + CI check" on 2026-11-07 and accepted the marked no-hook block on 2026-11-13: losing
  it would drop the phone list rows and search button.
- A page that turns red while ntfy says "warning" teaches its reader to ignore red. Mirroring the alert rules
  keeps the two in step and gives every threshold an owner.
- The prototype kit already renders both pages on the Homepage image's own Node, so the check promotes it
  instead of building a second mock.
- Three PRs keep each cut-over's diff preview reviewable on its own (Ben, 2026-11-13).

## Consequences

- A Homepage bump that changes a widget's routes or markup fails the render check until the mock or the CSS is
  updated in the bump PR.
- The mock proves rendering, not live data: a Git-proven query can still read `-` live and is fixed forward.
- A change to an alert rule's threshold should change the matching highlight in the catalog.
- Ben adds `homepage-render` to branch protection's required checks.
- From the content PR's merge until each cut-over, that live page is frozen: fixes go into the catalog.
- ADR 0018's credential table gains `JELLYFIN_HOUSEHOLD_TOKEN` (also sealed on admin, for the same lists) and
  the Calibre rows become live; the name `homepage-household` is reserved (ADR 0015).
- A cut-over diff can exceed the diff preview's 64 KB cap; the generated ConfigMap's own diff in the PR is
  complete, and the PR body adds the Deployment mount diff.
- The generator checks a cut-over page's `values.yaml` mounts against the ConfigMap's keys, because a mount of a
  missing key stops the pod.
