# Copyright (c) Moodle Pty Ltd. All rights reserved.
# Licensed under the Moodle Community License v1.3.
# See LICENSE.md in the repository root for full terms.
# Commercial use requires a separate written agreement with Moodle.
from __future__ import annotations

"""Public workflow-graph orchestration.

The heavy lifting lives in `workflow_support.py`. This module keeps the
top-level graph-building flow readable for maintainers and future agents.
"""

from moodle_sitemap.models import EdgeRelevance, EdgeWeight, PageRecord, WorkflowEdgeType, WorkflowGraph
from moodle_sitemap.workflow_support import (
    assign_next_steps,
    attach_background_clusters,
    augment_next_steps_with_background_clusters,
    build_edge,
    collect_edge_candidates,
    compress_low_value_edges,
    deduplicate_edges,
    preview_next_steps_by_page,
)


def derive_workflow_graph(pages: list[PageRecord], *, role_profile: str = "unlabeled") -> WorkflowGraph:
    """Build the workflow graph, next steps, and compression metadata."""

    page_by_url = {page.normalized_url: page for page in pages}
    candidate_edges = []

    for page in pages:
        for candidate in collect_edge_candidates(page):
            target_page = page_by_url.get(candidate.target_url)
            edge = build_edge(page, target_page, candidate)
            if edge is not None:
                candidate_edges.append(edge)

    before_next_steps = preview_next_steps_by_page(pages, candidate_edges)
    edges, deduplicated_pairs = deduplicate_edges(candidate_edges)
    suppressed_edge_count = max(len(candidate_edges) - len(edges), 0)
    edges, background_clusters, compressed_edge_count = compress_low_value_edges(pages, edges)

    attach_background_clusters(pages, background_clusters)
    changed_pages = assign_next_steps(pages, edges, before_next_steps=before_next_steps)
    augment_next_steps_with_background_clusters(pages)

    edge_type_counts = {edge_type.value: 0 for edge_type in WorkflowEdgeType}
    edge_weight_counts = {edge_weight.value: 0 for edge_weight in EdgeWeight}
    edge_relevance_counts = {edge_relevance.value: 0 for edge_relevance in EdgeRelevance}
    pre_dedup_edge_weight_counts = {edge_weight.value: 0 for edge_weight in EdgeWeight}
    pre_dedup_edge_relevance_counts = {edge_relevance.value: 0 for edge_relevance in EdgeRelevance}

    for edge in candidate_edges:
        pre_dedup_edge_weight_counts[edge.edge_weight.value] += 1
        pre_dedup_edge_relevance_counts[edge.edge_relevance.value] += 1
    for edge in edges:
        edge_type_counts[edge.edge_type.value] += 1
        edge_weight_counts[edge.edge_weight.value] += 1
        edge_relevance_counts[edge.edge_relevance.value] += 1

    return WorkflowGraph(
        role_profile=role_profile,
        candidate_edge_count=len(candidate_edges),
        suppressed_edge_count=suppressed_edge_count,
        deduplicated_pair_count=deduplicated_pairs,
        compressed_edge_count=compressed_edge_count,
        cluster_count=len(background_clusters),
        total_edges=len(edges),
        edge_type_counts=edge_type_counts,
        edge_weight_counts=edge_weight_counts,
        edge_relevance_counts=edge_relevance_counts,
        pre_dedup_edge_weight_counts=pre_dedup_edge_weight_counts,
        pre_dedup_edge_relevance_counts=pre_dedup_edge_relevance_counts,
        next_step_changed_pages=changed_pages,
        background_clusters=background_clusters,
        edges=sorted(edges, key=lambda item: (item.from_page_id, item.target_url, item.edge_type.value)),
    )
