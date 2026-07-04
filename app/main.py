from __future__ import annotations

from fastapi import FastAPI, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.core.settings import STATIC_DIR, TEMPLATES_DIR
from app.core.taxonomy import load_taxonomy
from app.debate.map_builder import DebateMapBuilder
from app.repositories.repository_factory import create_repository
from app.repositories.official_channels import OfficialChannelsRepository
from app.civic.drafts import DraftService
from app.observability.data_inventory import build_data_inventory

app = FastAPI(
    title="AgorIA",
    description="Prototype de cartographie du débat public parlementaire et d'aide à la participation éclairée.",
    version="0.1.0",
)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
templates = Jinja2Templates(directory=TEMPLATES_DIR)

taxonomy = load_taxonomy()
repository = create_repository()
map_builder = DebateMapBuilder(taxonomy)
channels_repository = OfficialChannelsRepository()
draft_service = DraftService(taxonomy, channels_repository)
ENTRY_MAP_RING_LIMIT = 12


@app.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "request": request,
            "taxonomy": taxonomy,
        },
    )


@app.get("/sujets/{subject_id}", response_class=HTMLResponse)
async def subject_detail(request: Request, subject_id: str) -> HTMLResponse:
    subject_bundle = repository.get_subject(subject_id)
    if subject_bundle is None:
        raise HTTPException(status_code=404, detail="Sujet introuvable")
    return templates.TemplateResponse(
        request,
        "subject.html",
        {
            "request": request,
            **subject_bundle,
        },
    )


@app.get("/mesures/{measure_id}", response_class=HTMLResponse)
async def measure_detail(request: Request, measure_id: str) -> HTMLResponse:
    measure = repository.get_measure(measure_id)
    if measure is None:
        raise HTTPException(status_code=404, detail="Mesure introuvable")
    traces = repository.list_traces(measure_id)
    clusters = map_builder.build(traces)
    themes = map_builder.build_by_theme(traces)
    debate_subjects = repository.list_debate_subjects(measure_id)
    stats = map_builder.stats(traces)
    return templates.TemplateResponse(
        request,
        "measure.html",
        {
            "request": request,
            "measure": measure,
            "traces": traces,
            "clusters": clusters,
            "themes": themes,
            "debate_subjects": debate_subjects,
            "stats": stats,
            "taxonomy": taxonomy,
            "participation_outputs": taxonomy.participation_outputs,
        },
    )


@app.post("/mesures/{measure_id}/preparer", response_class=HTMLResponse)
async def prepare_action(
    request: Request,
    measure_id: str,
    user_text: str = Form(...),
    selected_intent: str = Form("auto"),
) -> HTMLResponse:
    measure = repository.get_measure(measure_id)
    if measure is None:
        raise HTTPException(status_code=404, detail="Mesure introuvable")
    traces = repository.list_traces(measure_id)
    clusters = map_builder.build(traces)
    themes = map_builder.build_by_theme(traces)
    debate_subjects = repository.list_debate_subjects(measure_id)
    draft = draft_service.prepare(
        measure=measure,
        user_text=user_text,
        selected_intent=selected_intent,
    )
    return templates.TemplateResponse(
        request,
        "measure.html",
        {
            "request": request,
            "measure": measure,
            "traces": traces,
            "clusters": clusters,
            "themes": themes,
            "debate_subjects": debate_subjects,
            "stats": map_builder.stats(traces),
            "taxonomy": taxonomy,
            "participation_outputs": taxonomy.participation_outputs,
            "draft": draft,
            "user_text": user_text,
            "selected_intent": selected_intent,
        },
    )


@app.get("/sources", response_class=HTMLResponse)
async def sources(request: Request) -> HTMLResponse:
    inventory = build_data_inventory()
    return templates.TemplateResponse(
        request,
        "sources.html",
        {
            "request": request,
            "inventory": inventory,
        },
    )


@app.get("/principes", response_class=HTMLResponse)
async def principles(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "principles.html", {"request": request})


@app.get("/api/measures")
async def api_measures() -> list[dict]:
    return [m.__dict__ for m in repository.list_measures()]


@app.get("/api/entry-map")
async def api_entry_map() -> dict:
    categories = repository.list_all_debate_subjects()
    if len(categories) > ENTRY_MAP_RING_LIMIT:
        return {
            "mode": "groups",
            "items": _entry_range_groups(categories, kind="category_group"),
        }
    return {
        "mode": "categories",
        "items": [_entry_category(category) for category in categories],
    }


@app.get("/api/entry-map/category-groups/{group_id}")
async def api_entry_map_category_group(group_id: str) -> dict:
    categories = repository.list_all_debate_subjects()
    group_range = _parse_group_id(group_id)
    if group_range is None:
        raise HTTPException(status_code=404, detail="Groupe introuvable")
    start, end = group_range
    categories_in_group = categories[start:end]
    if len(categories_in_group) > ENTRY_MAP_RING_LIMIT:
        return {
            "mode": "groups",
            "group": next((item for item in _entry_range_groups(categories, kind="category_group") if item.get("id") == group_id), {}),
            "items": _entry_range_groups(categories_in_group, kind="category_group", offset=start),
        }
    return {
        "mode": "categories",
        "group": next((item for item in _entry_range_groups(categories, kind="category_group") if item.get("id") == group_id), {}),
        "items": [_entry_category(category) for category in categories_in_group],
    }


@app.get("/api/entry-map/categories/{category_id}")
async def api_entry_map_category(category_id: str) -> dict:
    category = _find_category(category_id)
    if category is None:
        raise HTTPException(status_code=404, detail="Catégorie introuvable")
    subthemes = category.get("subthemes", [])
    if len(subthemes) > ENTRY_MAP_RING_LIMIT:
        return {
            "mode": "groups",
            "category": _entry_category(category),
            "items": [
                {**group, "category_id": category_id}
                for group in _entry_range_groups(subthemes, kind="subtheme_group")
            ],
        }
    return {
        "mode": "subthemes",
        "category": _entry_category(category),
        "items": [_entry_subtheme(category, subtheme) for subtheme in subthemes],
    }


@app.get("/api/entry-map/categories/{category_id}/subtheme-groups/{group_id}")
async def api_entry_map_subtheme_group(category_id: str, group_id: str) -> dict:
    category = _find_category(category_id)
    group_range = _parse_group_id(group_id)
    if category is None or group_range is None:
        raise HTTPException(status_code=404, detail="Groupe introuvable")
    subthemes = category.get("subthemes", [])
    start, end = group_range
    if end > len(subthemes):
        raise HTTPException(status_code=404, detail="Groupe introuvable")
    subthemes_in_group = subthemes[start:end]
    if len(subthemes_in_group) > ENTRY_MAP_RING_LIMIT:
        return {
            "mode": "groups",
            "category": _entry_category(category),
            "group": next((item for item in _entry_range_groups(subthemes, kind="subtheme_group") if item.get("id") == group_id), {}),
            "items": [
                {**group, "category_id": category_id}
                for group in _entry_range_groups(subthemes_in_group, kind="subtheme_group", offset=start)
            ],
        }
    return {
        "mode": "subthemes",
        "category": _entry_category(category),
        "group": next((item for item in _entry_range_groups(subthemes, kind="subtheme_group") if item.get("id") == group_id), {}),
        "items": [_entry_subtheme(category, subtheme) for subtheme in subthemes_in_group],
    }


@app.get("/api/entry-map/categories/{category_id}/subthemes/{subtheme_id}")
async def api_entry_map_subtheme(category_id: str, subtheme_id: str) -> dict:
    category = _find_category(category_id)
    subtheme = _find_subtheme(category, subtheme_id)
    if category is None or subtheme is None:
        raise HTTPException(status_code=404, detail="Sous-catégorie introuvable")
    subjects = _sorted_subjects(subtheme)
    if len(subjects) > ENTRY_MAP_RING_LIMIT:
        items = _entry_subject_groups(category_id, subtheme_id, subjects)
        mode = "groups"
    else:
        items = [_entry_subject(subject) for subject in subjects]
        mode = "subjects"
    return {
        "category": _entry_category(category),
        "subtheme": _entry_subtheme(category, subtheme),
        "mode": mode,
        "items": items,
    }


@app.get("/api/entry-map/categories/{category_id}/subthemes/{subtheme_id}/groups/{group_id}")
async def api_entry_map_group(category_id: str, subtheme_id: str, group_id: str) -> dict:
    category = _find_category(category_id)
    subtheme = _find_subtheme(category, subtheme_id)
    if category is None or subtheme is None:
        raise HTTPException(status_code=404, detail="Groupe introuvable")
    group_range = _parse_group_id(group_id)
    if group_range is None:
        raise HTTPException(status_code=404, detail="Groupe introuvable")
    subjects = _sorted_subjects(subtheme)
    groups = _entry_subject_groups(category_id, subtheme_id, subjects)
    group = next((item for item in groups if item.get("id") == group_id), None)
    start, end = group_range
    if end > len(subjects):
        raise HTTPException(status_code=404, detail="Groupe introuvable")
    group_subjects = subjects[start:end]
    if group is None:
        group = {
            **_entry_range_groups(group_subjects, kind="group", offset=start)[0],
            "category_id": category_id,
            "subtheme_id": subtheme_id,
        }
    if len(group_subjects) > ENTRY_MAP_RING_LIMIT:
        return {
            "category": _entry_category(category),
            "subtheme": _entry_subtheme(category, subtheme),
            "group": group,
            "mode": "groups",
            "items": _entry_subject_groups(category_id, subtheme_id, group_subjects, offset=start),
        }
    return {
        "category": _entry_category(category),
        "subtheme": _entry_subtheme(category, subtheme),
        "group": group,
        "mode": "subjects",
        "items": [_entry_subject(subject) for subject in group_subjects],
    }


@app.get("/api/entry-map/search")
async def api_entry_map_search(q: str = Query(..., min_length=2), limit: int = Query(80, ge=1, le=120)) -> dict:
    query = q.strip().lower()
    matches = []
    for category in repository.list_all_debate_subjects():
        for subtheme in category.get("subthemes", []):
            for subject in subtheme.get("subjects", []):
                haystack = " ".join(
                    [
                        category.get("label", ""),
                        subtheme.get("label", ""),
                        subject.get("title", ""),
                        subject.get("summary", ""),
                        subject.get("context", ""),
                    ]
                ).lower()
                if query in haystack:
                    matches.append(
                        {
                            "category": _entry_category(category),
                            "subtheme": _entry_subtheme(category, subtheme),
                            "subject": _entry_subject(subject),
                        }
                    )
    return {"items": matches[:limit], "total": len(matches), "limit": limit}


@app.get("/api/measures/{measure_id}/debate-map")
async def api_debate_map(measure_id: str) -> dict:
    measure = repository.get_measure(measure_id)
    if measure is None:
        raise HTTPException(status_code=404, detail="Mesure introuvable")
    traces = repository.list_traces(measure_id)
    clusters = map_builder.build(traces)
    themes = map_builder.build_by_theme(traces)
    debate_subjects = repository.list_debate_subjects(measure_id)
    return {
        "measure": {"id": measure.id, "title": measure.title},
        "stats": map_builder.stats(traces),
        "debate_subjects": debate_subjects,
        "themes": [
            {
                "key": theme.key,
                "label": theme.label,
                "description": theme.description,
                "clusters": [
                    {
                        "role": c.role,
                        "label": c.label,
                        "category": c.category,
                        "category_label": c.category_label,
                        "traces": [t.__dict__ for t in c.traces],
                    }
                    for c in theme.clusters
                ],
            }
            for theme in themes
        ],
        "clusters": [
            {
                "role": c.role,
                "label": c.label,
                "category": c.category,
                "category_label": c.category_label,
                "traces": [t.__dict__ for t in c.traces],
            }
            for c in clusters
        ],
    }

from fastapi.responses import PlainTextResponse
from app.core.settings import BASE_DIR


@app.get("/docs/architecture", response_class=PlainTextResponse)
async def architecture_doc() -> PlainTextResponse:
    return PlainTextResponse((BASE_DIR / "docs" / "architecture.md").read_text(encoding="utf-8"))


def _find_category(category_id: str) -> dict | None:
    return next((category for category in repository.list_all_debate_subjects() if category.get("id") == category_id), None)


def _find_subtheme(category: dict | None, subtheme_id: str) -> dict | None:
    if category is None:
        return None
    return next((subtheme for subtheme in category.get("subthemes", []) if subtheme.get("id") == subtheme_id), None)


def _entry_category(category: dict) -> dict:
    return {
        "id": category.get("id"),
        "label": category.get("label"),
        "summary": category.get("summary", ""),
        "count": sum(len(subtheme.get("subjects", [])) for subtheme in category.get("subthemes", [])),
        "kind": "category",
    }


def _entry_subtheme(category: dict, subtheme: dict) -> dict:
    return {
        "id": subtheme.get("id"),
        "category_id": category.get("id"),
        "label": subtheme.get("label"),
        "count": len(subtheme.get("subjects", [])),
        "kind": "subtheme",
    }


def _entry_subject(subject: dict) -> dict:
    return {
        "id": subject.get("id"),
        "title": subject.get("title"),
        "summary": subject.get("summary", ""),
        "context": subject.get("context", ""),
        "kind": "subject",
    }


def _sorted_subjects(subtheme: dict) -> list[dict]:
    return sorted(subtheme.get("subjects", []), key=lambda item: item.get("title", ""))


def _entry_range_groups(items: list[dict], *, kind: str, offset: int = 0) -> list[dict]:
    if not items:
        return []
    chunk_size = max(1, -(-len(items) // ENTRY_MAP_RING_LIMIT))
    groups = []
    for index in range(0, len(items), chunk_size):
        chunk = items[index : index + chunk_size]
        start = offset + index
        end = offset + index + len(chunk)
        groups.append(
            {
                "id": f"{start}-{end}",
                "label": f"Groupe {len(groups) + 1}",
                "count": len(chunk),
                "kind": kind,
            }
        )
    return groups


def _entry_subject_groups(category_id: str, subtheme_id: str, subjects: list[dict], *, offset: int = 0) -> list[dict]:
    groups = []
    for group in _entry_range_groups(subjects, kind="group", offset=offset):
        groups.append(
            {
                **group,
                "category_id": category_id,
                "subtheme_id": subtheme_id,
            }
        )
    return groups


def _parse_group_id(group_id: str) -> tuple[int, int] | None:
    parts = group_id.split("-", 1)
    if len(parts) != 2:
        return None
    try:
        start = int(parts[0])
        end = int(parts[1])
    except ValueError:
        return None
    if start < 0 or end <= start:
        return None
    return start, end
