# Stage 4.2H local boundary workspace

Stage 4.2H-A stores inventory-boundary confirmations under
`private_data/company_workspaces/`. This directory is gitignored and must not be
treated as product source or checked into version control.

## Prototype guarantees

- Each company has a separate directory selected from its confirmed Taiwan UBN
  or stable legal-entity ID.
- Each reporting period has a separate directory.
- Wizard answers are written to one mutable `boundary-semantics-v2` package for
  the exact company and reporting period. The package can legitimately contain
  purpose reviews and registration reconciliations while containing zero
  inventory boundaries.
- A locally confirmed period package is written as a new append-only version.
- A small current pointer identifies the version currently shown by the
  product.
- Rollback changes the current pointer and adds an event; it does not delete or
  overwrite an earlier version.
- JSON files use a temporary file and atomic replacement to reduce partial
  writes during a normal local process interruption.

## Security and confirmation limits

This mechanism is a local prototype workspace, not an enterprise authorization
system or a compliance-grade record store.

- There is no authenticated identity.
- There is no role-based access control or separation of duties.
- There is no server-side access control.
- There is no multi-user concurrency control.
- There is no cloud backup.
- Data is local plaintext unless the operating system or storage volume
  protects it.
- A name and job title are required before a new locally confirmed version can
  be written. They are self-entered contact details and do not establish a
  verified identity.
- Atomic writes and version history improve local integrity but do not make the
  workspace an audit-grade confirmation system.

The confirmation method is fixed to `local_workspace_unverified`. Customer
screens must describe the result as confirmed in this local workspace and must
not imply authenticated identity or formal authorization.

The six-step wizard first reconciles every government factory-registration row
to a `CanonicalSite`. An official row is an
`OfficialRegistrationCandidate`, not a site, membership, or boundary. Multiple
rows can support one site, so operating facts are asked once per canonical site
and reporting period.

The wizard keeps reporting-period operating facts separate from
reporting-boundary membership. A site that starts, stops, is sold, or is
transferred during a reporting period can remain included, because activity
data may still be needed for part of that period. Stage 4.2H-A records the fact,
effective date, and supporting basis only; uploaded-data coverage and
calculation behavior remain outside this stage.

Stage 4.2H-A does not collect or gate completion on the six source categories.
Legacy category payloads remain readable in v1 history only. Source-category
coverage belongs to Stage 4.2H-B.

## V2 semantic packages

The package and record schemas are:

- `boundary-semantics-v2`
- `purpose-review-v1`
- `official-registration-candidate-v1`
- `canonical-site-v1`
- `registration-reconciliation-v1`
- `period-operating-fact-v1`
- `competent-authority-boundary-evidence-v1`
- `financial-statement-reporting-entity-evidence-v1`
- `inventory-boundary-v2`

Purposes are mapped only from the saved applicability assessment's obligation
status and exact applied rule IDs. Company listing status, UBN, factory count,
and registration rows do not create purposes.

MOENV boundaries are 0..N per purpose review and period. They are created only
from complete, effective `CompetentAuthorityBoundaryEvidence` with
`verification_state == verified_official_source`. Customer-supplied documents
remain `customer_supplied_pending_review`. Notes and professional-review
metadata cannot verify, merge, or define a MOENV boundary.

The IFRS adoption assessment creates an `ifrs_reporting_entity` purpose and
timing only. A boundary is not created until the relevant financial statement,
reporting entity, consolidation basis, and legal-entity composition are
supported by `FinancialStatementReportingEntityEvidence`.

## Explicit v1 migration

Migration is never triggered while rendering the page. The user first reviews
a read-only dry run and then explicitly activates migration:

`detect -> dry-run -> explicit migrate -> atomic pointer activation -> v2`

Migration is idempotent. V1 files are not overwritten. Append-only events record
activation and rollback. Rollback selects v1 without deleting v2 history.

The migration intentionally does not promote legacy assumptions:

- registration links become evidence candidates, not confirmed sites;
- old registration combinations become
  `customer_asserted_related_pending_review`, not verified authority evidence;
- legacy facility memberships do not become canonical-site memberships;
- legacy source categories remain in the legacy snapshot only;
- professional-review notes remain interpretation metadata and cannot become
  `verified_official_source`;
- legacy standalone composition and boundary IDs are not reused.

## Wizard layout contract

The active boundary wizard owns its width and renders four normal-flow regions
in order: stepper, reporting-scope context, one primary card, and footer
navigation. The primary card grows with its content; it does not use per-step
height caps or an internal vertical scrollbar. Review validation and the
completed local-confirmation summary remain inside that card. If the page is
taller than the viewport, the document scrolls normally to reach the footer.

## Operational notes

`CEL_COMPANY_WORKSPACE_DIR` can point tests or a local deployment at another
workspace root. Production-style deployment would require a separate security,
identity, access-control, concurrency, backup, retention, and migration design;
those capabilities are outside Stage 4.2H-A.
