"""Cleanup helpers for entity lifecycle across loosely-coupled JSON layouts."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.research import ResearchProject


def remove_entity_from_research_layouts(db: Session, user_id: uuid.UUID, entity_id: uuid.UUID) -> int:
    """
    Remove deleted entity references from research project layout_config:
    - tabs[].setup.entity_id/entity_name
    - root setup.entity_id/entity_name (legacy)
    - tabs[].panels[].entity_id if present
    """
    eid = str(entity_id)
    changed = 0
    projects = db.scalars(select(ResearchProject).where(ResearchProject.user_id == user_id)).all()
    for p in projects:
        cfg = dict(p.layout_config or {})
        touched = False
        tabs = cfg.get("tabs")
        if isinstance(tabs, list):
            new_tabs: list[dict] = []
            for t in tabs:
                if not isinstance(t, dict):
                    new_tabs.append(t)
                    continue
                t2 = dict(t)
                setup = t2.get("setup")
                if isinstance(setup, dict) and str(setup.get("entity_id") or "") == eid:
                    setup2 = dict(setup)
                    setup2.pop("entity_id", None)
                    setup2.pop("entity_name", None)
                    t2["setup"] = setup2
                    touched = True
                panels = t2.get("panels")
                if isinstance(panels, list):
                    new_panels: list = []
                    for panel in panels:
                        if isinstance(panel, dict) and str(panel.get("entity_id") or "") == eid:
                            panel2 = dict(panel)
                            panel2.pop("entity_id", None)
                            new_panels.append(panel2)
                            touched = True
                        else:
                            new_panels.append(panel)
                    t2["panels"] = new_panels
                new_tabs.append(t2)
            cfg["tabs"] = new_tabs
        setup_root = cfg.get("setup")
        if isinstance(setup_root, dict) and str(setup_root.get("entity_id") or "") == eid:
            s2 = dict(setup_root)
            s2.pop("entity_id", None)
            s2.pop("entity_name", None)
            cfg["setup"] = s2
            touched = True
        if touched:
            p.layout_config = cfg
            changed += 1
    return changed

