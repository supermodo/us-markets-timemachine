# Governance

`us-markets-timemachine` is BDFL-governed. The BDFL is @supermac.

## What this means in practice

- All PRs require BDFL review and approval.
- All issues are triaged by the BDFL.
- All releases are tagged by the BDFL.
- The mission scope (`docs/SPEC.md` section 3.4) is set by the BDFL and changes
  only by deliberate amendment of the SPEC, not by precedent.

The BDFL model is a deliberate choice for a project with real legal
exposure per integrated source: each new source's NOTICE.md is a public
legal posture statement, and the operator (the BDFL) is the one who would
hear from a publisher's lawyers if one of those statements is wrong. A
single accountable maintainer makes that exposure tractable.

## What can be done without BDFL involvement

- **Discussion.** Open issues, propose ideas, comment on PRs.
- **Bug reports.** Concrete reproductions are always welcome and rarely
  controversial.
- **Documentation typo fixes.** Open a PR; if it's purely a doc-typo
  change, it'll be merged quickly.

## What needs BDFL approval (i.e., everything substantive)

- Adding a new source (see [`ADDING-A-SOURCE.md`](ADDING-A-SOURCE.md)).
- Modifying any source's NOTICE.md.
- Changing the Source protocol or any shared core module
  (`http.py`, `io.py`, `paths.py`, `manifest.py`, `notify.py`, `cli.py`,
  `dates.py`).
- Changing the CI workflow.
- Renaming directories under `data/`.

## How to escalate

If a PR has been sitting without BDFL response for more than 14 days, it
is reasonable to:

- Tag @supermac in a comment.
- If still no response after another 7 days, the PR is effectively
  un-merged. The BDFL apologises in advance for any stalled work.

## Future evolution

If the project grows to multiple actively-developed sources contributed by
multiple sustained maintainers, the BDFL may add per-source CODEOWNERS so
each source's contributor has merge authority over their own subdirectory.
This isn't planned for any specific timeline; it'll happen when the load
makes the BDFL the bottleneck.

The BDFL model is also reversible: it can be amended into a more formal
governance structure (small core team with voting, etc.) by a SPEC
amendment.
