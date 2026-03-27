from fastapi import APIRouter

from app.api.routes import admin_routes, ai_routes, alerts, assets, auth, community, groups, indices, keyword_groups, macro, market, portfolios, reports, research, schedules

api_router = APIRouter(prefix="/api")
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(admin_routes.router, prefix="/admin", tags=["admin"])
api_router.include_router(assets.router, prefix="/assets", tags=["assets"])
api_router.include_router(macro.router, prefix="/macro", tags=["macro"])
api_router.include_router(research.router, prefix="/research", tags=["research"])
api_router.include_router(keyword_groups.router, prefix="/keyword-groups", tags=["keyword-groups"])
api_router.include_router(portfolios.router, tags=["portfolios"])
api_router.include_router(ai_routes.router, prefix="/ai", tags=["ai"])
api_router.include_router(groups.router, prefix="/groups", tags=["groups"])
api_router.include_router(indices.router, prefix="/indices", tags=["indices"])
api_router.include_router(market.router, prefix="/market", tags=["market"])
api_router.include_router(reports.router, prefix="/reports", tags=["reports"])
api_router.include_router(schedules.router, prefix="/schedules", tags=["schedules"])
api_router.include_router(alerts.router, prefix="/alerts", tags=["alerts"])
api_router.include_router(community.router, prefix="/community", tags=["community"])

