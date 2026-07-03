from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class SourceRef:
    label: str
    type: str
    url: str = "#"


@dataclass(frozen=True)
class Measure:
    id: str
    title: str
    law_title: str
    article: str
    status: str
    summary: str
    changes: list[str]
    audiences: list[str]
    obligations: list[str]
    deadlines: list[str]
    expected_effects: list[str]
    sources: list[SourceRef] = field(default_factory=list)


@dataclass(frozen=True)
class PublicTrace:
    id: str
    measure_id: str
    trace_type: str
    institution: str
    date: str
    speaker: str
    title: str
    excerpt: str
    source_url: str
    argument_role: str
    category: str
    problem_type: str
    confidence: str


@dataclass(frozen=True)
class DebateCluster:
    role: str
    category: str
    label: str
    category_label: str
    traces: list[PublicTrace]


@dataclass(frozen=True)
class DebateTheme:
    key: str
    label: str
    description: str
    clusters: list[DebateCluster]


@dataclass(frozen=True)
class CivicChannel:
    key: str
    label: str
    url: str
    note: str


@dataclass(frozen=True)
class DraftResult:
    output_type: str
    output_label: str
    title: str
    draft: str
    channels: list[CivicChannel]
    privacy_notice: str
