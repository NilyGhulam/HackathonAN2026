from __future__ import annotations

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.core.settings import STATIC_DIR, TEMPLATES_DIR
from app.core.taxonomy import load_taxonomy
from app.debate.map_builder import DebateMapBuilder
from app.repositories.demo_repository import DemoRepository
from app.repositories.official_channels import OfficialChannelsRepository
from app.civic.drafts import DraftService

app = FastAPI(
    title="AgoraLoi",
    description="Prototype de cartographie du débat public parlementaire et d'aide à la participation éclairée.",
    version="0.1.0",
)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
templates = Jinja2Templates(directory=TEMPLATES_DIR)

taxonomy = load_taxonomy()
repository = DemoRepository()
map_builder = DebateMapBuilder(taxonomy)
channels_repository = OfficialChannelsRepository()
draft_service = DraftService(taxonomy, channels_repository)


@app.get("/", response_class=HTMLResponse)
def index(request: Request) -> HTMLResponse:
    measures = repository.list_measures()
    all_traces = repository.list_traces()
    stats = map_builder.stats(all_traces)
    debate_subjects = repository.list_all_debate_subjects()
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "request": request,
            "measures": measures,
            "stats": stats,
            "taxonomy": taxonomy,
            "debate_subjects": debate_subjects,
        },
    )


@app.get("/sujets/{subject_id}", response_class=HTMLResponse)
def subject_detail(request: Request, subject_id: str) -> HTMLResponse:
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
def measure_detail(request: Request, measure_id: str) -> HTMLResponse:
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
def prepare_action(
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


@app.get("/principes", response_class=HTMLResponse)
def principles(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "principles.html", {"request": request})


@app.get("/api/measures")
def api_measures() -> list[dict]:
    return [m.__dict__ for m in repository.list_measures()]


@app.get("/api/measures/{measure_id}/debate-map")
def api_debate_map(measure_id: str) -> dict:
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
def architecture_doc() -> PlainTextResponse:
    return PlainTextResponse((BASE_DIR / "docs" / "architecture.md").read_text(encoding="utf-8"))
