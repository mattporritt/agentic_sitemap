"""Stable runtime-facing contract builders for `agentic_sitemap`.

The runtime contract is intentionally narrower than the human-oriented
artifact workflows. It wraps a small set of saved-run lookups in a consistent
outer envelope aligned with the broader toolchain.
"""

from __future__ import annotations

from hashlib import sha1
from pathlib import Path
from urllib.parse import urlparse
import re

from moodle_sitemap.models import (
    EdgeRelevance,
    PageRecord,
    PageType,
    RuntimeConfidence,
    RuntimeContractEnvelope,
    RuntimeContractIntent,
    RuntimeContractResult,
    RuntimeContractSource,
    RuntimeLookupMode,
    SiteManifest,
    TaskValidationSummary,
)
from moodle_sitemap.task_validation_support import (
    find_best_path,
    load_manifest,
    load_workflow_graph,
)

WHITESPACE_PATTERN = re.compile(r"\s+")


def normalize_runtime_query(query: str) -> str:
    """Normalize a runtime query string for stable contract output."""

    return WHITESPACE_PATTERN.sub(" ", query.strip().lower())


def stable_runtime_id(*parts: str) -> str:
    """Build a deterministic short identifier for runtime results."""

    normalized = "||".join(part.strip() for part in parts)
    return sha1(normalized.encode("utf-8")).hexdigest()[:16]


def build_page_lookup_contract(
    *,
    run_dir: str | Path,
    query: str,
    lookup_mode: RuntimeLookupMode,
    top_k: int = 5,
) -> RuntimeContractEnvelope:
    """Build a runtime contract for page or page-type lookups."""

    manifest = load_manifest(Path(run_dir) / "sitemap.json")
    matches = resolve_page_matches(manifest.pages, query=query, lookup_mode=lookup_mode)[:top_k]
    results: list[RuntimeContractResult] = []
    for rank, match in enumerate(matches, start=1):
        page = match["page"]
        results.append(
            RuntimeContractResult(
                id=stable_runtime_id("page", page.normalized_url, page.page_type.value),
                type="page_context",
                rank=rank,
                confidence=match["confidence"],
                source=build_page_source(page),
                content=build_page_content(page),
                diagnostics={
                    "lookup_mode": lookup_mode.value,
                    "matched_on": match["matched_on"],
                    "artifact_run": str(run_dir),
                },
            )
        )
    return RuntimeContractEnvelope(
        query=query,
        normalized_query=normalize_runtime_query(query),
        intent=RuntimeContractIntent(
            query_intent="page_lookup" if lookup_mode == RuntimeLookupMode.PAGE else "page_type_lookup",
            lookup_mode=lookup_mode.value,
            role_profile=manifest.role_profile,
            filters=[],
        ),
        results=results,
    )


def build_path_lookup_contract(
    *,
    run_dir: str | Path,
    from_selector: str,
    to_selector: str,
    top_k: int = 3,
) -> RuntimeContractEnvelope:
    """Build a runtime contract for workflow/path lookup over a saved run."""

    manifest = load_manifest(Path(run_dir) / "sitemap.json")
    workflow_graph = load_workflow_graph(Path(run_dir) / "workflow-edges.json")
    source_matches = resolve_selector_pages(manifest.pages, from_selector)
    target_matches = resolve_selector_pages(manifest.pages, to_selector)

    path_results: list[tuple[int, int, int, PageRecord, PageRecord, list]] = []
    for source_page in source_matches:
        path_edges = find_best_path(
            workflow_graph=workflow_graph,
            start_page_id=source_page.page_id,
            target_page_ids={page.page_id for page in target_matches},
        )
        if not path_edges:
            continue
        target_page = next(
            (page for page in manifest.pages if page.page_id == path_edges[-1].to_page_id),
            None,
        )
        if target_page is None:
            continue
        path_results.append(
            (
                len(path_edges),
                relevance_score(path_edges),
                target_priority(target_page),
                source_page,
                target_page,
                path_edges,
            )
        )

    path_results.sort(key=lambda item: (item[0], -item[1], -item[2], item[4].normalized_url))

    results: list[RuntimeContractResult] = []
    for rank, (_, _, _, source_page, target_page, path_edges) in enumerate(path_results[:top_k], start=1):
        result_type = "site_path"
        diagnostics = {
            "lookup_mode": RuntimeLookupMode.PATH.value,
            "artifact_run": str(run_dir),
            "path_strategy": "workflow_graph_bfs",
            "edge_count": len(path_edges),
        }
        results.append(
            RuntimeContractResult(
                id=stable_runtime_id("path", source_page.normalized_url, target_page.normalized_url),
                type=result_type,
                rank=rank,
                confidence=path_confidence(path_edges),
                source=build_page_source(source_page),
                content={
                    "from_page_id": source_page.page_id,
                    "from_page_type": source_page.page_type.value,
                    "to_page_id": target_page.page_id,
                    "to_page_type": target_page.page_type.value,
                    "path_length": len(path_edges),
                    "page_ids": [source_page.page_id, *[edge.to_page_id for edge in path_edges if edge.to_page_id]],
                    "page_types": [source_page.page_type.value, *[edge.target_page_type.value if edge.target_page_type else "unknown" for edge in path_edges]],
                    "hops": [
                        {
                            "id": stable_runtime_id("hop", source_page.page_id if index == 0 else path_edges[index - 1].to_page_id or "", edge.target_url),
                            "target_page_id": edge.to_page_id,
                            "target_page_type": edge.target_page_type.value if edge.target_page_type else None,
                            "target_url": edge.target_url,
                            "edge_type": edge.edge_type.value,
                            "edge_weight": edge.edge_weight.value,
                            "edge_relevance": edge.edge_relevance.value,
                            "label": edge.source_affordance_label,
                        }
                        for index, edge in enumerate(path_edges)
                    ],
                },
                diagnostics=diagnostics,
            )
        )

    query = f"{from_selector} -> {to_selector}"
    return RuntimeContractEnvelope(
        query=query,
        normalized_query=normalize_runtime_query(query),
        intent=RuntimeContractIntent(
            query_intent="path_lookup",
            lookup_mode=RuntimeLookupMode.PATH.value,
            role_profile=manifest.role_profile,
            filters=[from_selector, to_selector],
        ),
        results=results,
    )


def build_task_validation_contract(summary: TaskValidationSummary) -> RuntimeContractEnvelope:
    """Map a task-validation summary into the shared runtime contract."""

    manifest = load_manifest(Path(summary.run_dir) / "sitemap.json")
    pages_by_id = {page.page_id: page for page in manifest.pages}
    results: list[RuntimeContractResult] = []
    for rank, task in enumerate(sorted(summary.results, key=task_sort_key), start=1):
        source_page = first_existing_page(task.target_page_ids, pages_by_id) or (
            pages_by_id.get(task.starting_page_id) if task.starting_page_id else None
        )
        results.append(
            RuntimeContractResult(
                id=stable_runtime_id("task", summary.role_profile, task.task_id),
                type="task_validation",
                rank=rank,
                confidence=task_confidence(task),
                source=build_page_source(source_page),
                content={
                    "task_id": task.task_id,
                    "status": task.status.value,
                    "starting_page_id": task.starting_page_id,
                    "target_page_ids": list(task.target_page_ids),
                    "target_page_types": list(task.target_page_types),
                    "candidate_path_page_ids": list(task.candidate_path_page_ids),
                    "candidate_path_page_types": list(task.candidate_path_page_types),
                    "path_length": task.path_length,
                    "best_path_confidence": task.best_path_confidence,
                    "first_hop_quality": task.first_hop_quality,
                    "next_steps_helpful": task.next_steps_helpful,
                    "key_affordances": list(task.key_affordances),
                    "safety_notes": list(task.safety_notes),
                },
                diagnostics={
                    "lookup_mode": RuntimeLookupMode.TASK_VALIDATION.value,
                    "artifact_run": summary.run_dir,
                    "tasks_file": summary.tasks_file,
                    "status": task.status.value,
                    "path_quality_score": task.path_quality_score,
                },
            )
        )
    query = f"task validation for {summary.role_profile}"
    return RuntimeContractEnvelope(
        query=query,
        normalized_query=normalize_runtime_query(query),
        intent=RuntimeContractIntent(
            query_intent="task_validation",
            lookup_mode=RuntimeLookupMode.TASK_VALIDATION.value,
            role_profile=summary.role_profile,
            filters=[],
        ),
        results=results,
    )


def resolve_page_matches(
    pages: list[PageRecord],
    *,
    query: str,
    lookup_mode: RuntimeLookupMode,
) -> list[dict[str, object]]:
    """Return ranked page matches for a runtime page lookup."""

    if lookup_mode == RuntimeLookupMode.PAGE_TYPE:
        try:
            page_type = PageType(query.strip().lower())
        except ValueError:
            return []
        matches = [
            {"page": page, "matched_on": "page_type", "confidence": page_result_confidence(rank)}
            for rank, page in enumerate(sorted((page for page in pages if page.page_type == page_type), key=lambda item: item.normalized_url), start=1)
        ]
        return matches

    selector = query.strip()
    exact_matches: list[dict[str, object]] = []
    route_matches: list[dict[str, object]] = []
    for page in pages:
        if selector == page.page_id:
            exact_matches.append({"page": page, "matched_on": "page_id", "confidence": RuntimeConfidence.HIGH})
            continue
        if selector.startswith("http") and selector in {page.url, page.final_url, page.normalized_url}:
            exact_matches.append({"page": page, "matched_on": "page_url", "confidence": RuntimeConfidence.HIGH})
            continue
        parsed = urlparse(page.normalized_url)
        if selector.startswith("/") and selector in {parsed.path, f"{parsed.path}?{parsed.query}".rstrip("?")}:
            route_matches.append({"page": page, "matched_on": "route", "confidence": RuntimeConfidence.MEDIUM})
    ranked = sorted(exact_matches, key=lambda item: item["page"].normalized_url) + sorted(route_matches, key=lambda item: item["page"].normalized_url)
    for rank, item in enumerate(ranked, start=1):
        item["confidence"] = page_result_confidence(rank if item["matched_on"] != "route" else max(rank, 2))
    return ranked


def resolve_selector_pages(pages: list[PageRecord], selector: str) -> list[PageRecord]:
    """Resolve a path/source selector to one or more pages."""

    stripped = selector.strip()
    try:
        page_type = PageType(stripped.lower())
    except ValueError:
        page_type = None
    if page_type is not None:
        return sorted([page for page in pages if page.page_type == page_type], key=lambda item: item.normalized_url)
    matches = resolve_page_matches(pages, query=stripped, lookup_mode=RuntimeLookupMode.PAGE)
    return [item["page"] for item in matches]


def build_page_source(page: PageRecord | None) -> RuntimeContractSource:
    """Build consistent provenance for page-derived runtime results."""

    if page is None:
        return RuntimeContractSource(
            name="moodle_site",
            type="site_crawl",
            url=None,
            canonical_url=None,
            path=None,
            document_title=None,
            section_title=None,
            heading_path=[],
        )
    parsed = urlparse(page.normalized_url)
    path = parsed.path or None
    if parsed.query:
        path = f"{parsed.path}?{parsed.query}"
    return RuntimeContractSource(
        name="moodle_site",
        type="site_crawl",
        url=page.url,
        canonical_url=page.normalized_url,
        path=path,
        document_title=page.title,
        section_title=None,
        heading_path=[],
    )


def build_page_content(page: PageRecord) -> dict[str, object]:
    """Build a compact runtime-facing content payload for one page."""

    return {
        "page_id": page.page_id,
        "page_type": page.page_type.value,
        "title": page.title,
        "primary_page_intent": page.primary_page_intent.value,
        "primary_actions": list(page.primary_actions),
        "breadcrumbs": list(page.breadcrumbs),
        "next_steps": [
            {
                "id": stable_runtime_id("next-step", page.page_id, step.target_url),
                "page_id": step.page_id,
                "target_page_type": step.target_page_type.value if step.target_page_type else None,
                "target_url": step.target_url,
                "edge_type": step.edge_type.value,
                "edge_weight": step.edge_weight.value,
                "edge_relevance": step.edge_relevance.value,
                "label": step.label,
            }
            for step in page.next_steps[:4]
        ],
        "affordance_summary": {
            "action_count": len(page.affordances.actions),
            "form_count": len(page.affordances.forms),
            "navigation_count": len(page.affordances.navigation),
            "top_actions": [action.label for action in page.affordances.actions[:5]],
        },
        "safety": {
            "page_risk_level": page.safety.page_risk_level.value,
            "contains_mutating_actions": page.safety.contains_mutating_actions,
            "contains_destructive_actions": page.safety.contains_destructive_actions,
            "likely_requires_confirmation": page.safety.likely_requires_confirmation,
        },
    }


def path_confidence(path_edges: list) -> RuntimeConfidence:
    """Map path strength into coarse runtime confidence."""

    if not path_edges:
        return RuntimeConfidence.LOW
    if len(path_edges) == 1 and path_edges[0].edge_relevance in {EdgeRelevance.TASK, EdgeRelevance.SUPPORT}:
        return RuntimeConfidence.HIGH
    if all(edge.edge_relevance != EdgeRelevance.CONTEXTUAL for edge in path_edges):
        return RuntimeConfidence.MEDIUM
    return RuntimeConfidence.LOW


def page_result_confidence(rank: int) -> RuntimeConfidence:
    if rank == 1:
        return RuntimeConfidence.HIGH
    if rank <= 3:
        return RuntimeConfidence.MEDIUM
    return RuntimeConfidence.LOW


def task_confidence(task) -> RuntimeConfidence:
    if task.status.value == "pass":
        return RuntimeConfidence.HIGH
    if task.status.value == "partial":
        return RuntimeConfidence.MEDIUM
    return RuntimeConfidence.LOW


def task_sort_key(task) -> tuple[int, int, str]:
    """Sort task-validation results with strongest outcomes first."""

    status_rank = {"pass": 0, "partial": 1, "fail": 2}[task.status.value]
    return (status_rank, -(task.best_path_confidence or 0), task.task_id)


def relevance_score(path_edges: list) -> int:
    return sum(
        {
            EdgeRelevance.TASK: 4,
            EdgeRelevance.SUPPORT: 3,
            EdgeRelevance.NAVIGATION: 2,
            EdgeRelevance.CONTEXTUAL: 1,
        }[edge.edge_relevance]
        for edge in path_edges
    )


def target_priority(page: PageRecord) -> int:
    return 2 if page.page_type in {PageType.COURSE_VIEW, PageType.MESSAGE_PREFERENCES, PageType.CALENDAR} else 1


def first_existing_page(page_ids: list[str], pages_by_id: dict[str, PageRecord]) -> PageRecord | None:
    for page_id in page_ids:
        if page_id in pages_by_id:
            return pages_by_id[page_id]
    return None


def load_task_validation_summary(path: Path) -> TaskValidationSummary:
    """Load a saved task-validation summary artifact."""

    return TaskValidationSummary.model_validate_json(path.read_text(encoding="utf-8"))
