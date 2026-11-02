# ADR 0001 — Development governance

Date: 2026-11-02
Status: proposed in bootstrap PR

MotionPack uses a human-governed repository with one coordinating Codex main agent and eleven on-demand specialist subagents. Decisions, issue scope, specifications, tests and release evidence are tracked in GitHub. Implementation agents do not approve their own changes; security, quality and code review are independent checks. No role description grants additional machine permissions. Public release, security-policy relaxation, license selection and merge decisions remain with the human maintainer.

Consequences: more traceability and quality gates, but some overhead. Keep the number of simultaneously active subagents small. Deliver the real runtime and examples in a separate import PR.
