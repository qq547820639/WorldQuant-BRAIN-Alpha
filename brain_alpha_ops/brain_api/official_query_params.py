"""WQB-compatible query parameter builders for official BRAIN endpoints."""

from __future__ import annotations

from typing import Any

from .official_filtering import build_filter_params


def apply_market_discovery_filters(
    params: dict[str, Any],
    *,
    category: str = "",
    universe: str = "",
    delay: int | None = None,
    coverage: Any = None,
    value_score: Any = None,
    alpha_count: Any = None,
    user_count: Any = None,
    order: str = "",
) -> None:
    if category:
        params["category"] = category
    if universe:
        params["universe"] = universe
    if delay is not None:
        params["delay"] = int(delay)
    if order:
        params["order"] = order
    for field_name, value in (
        ("coverage", coverage),
        ("valueScore", value_score),
        ("alphaCount", alpha_count),
        ("userCount", user_count),
    ):
        params.update(build_filter_params(field_name, value))


def alpha_filter_params(
    *,
    name: str = "",
    competition: str = "",
    alpha_type: str = "",
    type: str = "",
    status: str = "",
    date_created: Any = None,
    instrument_type: str = "",
    region: str = "",
    universe: str = "",
    delay: int | None = None,
    sharpe: Any = None,
    fitness: Any = None,
    turnover: Any = None,
    prod_correlation: Any = None,
    self_correlation: Any = None,
    returns: Any = None,
    pnl: Any = None,
    drawdown: Any = None,
    margin: Any = None,
    book_size: Any = None,
    long_count: Any = None,
    short_count: Any = None,
    os_sharpe: Any = None,
    os_fitness: Any = None,
    os_turnover: Any = None,
    os_returns: Any = None,
    os_pnl: Any = None,
    os_drawdown: Any = None,
    os_margin: Any = None,
    os_long_count: Any = None,
    os_short_count: Any = None,
    date_submitted: Any = None,
    start_date: Any = None,
    language: str = "",
    decay: int | None = None,
    neutralization: str = "",
    pasteurization: str = "",
    truncation: Any = None,
    unit_handling: str = "",
    nan_handling: str = "",
    hidden: bool | None = None,
    favorite: bool | None = None,
    category: str = "",
    color: str = "",
    tag: str = "",
    stage: str = "",
    order: str = "",
    limit: int = 100,
    offset: int = 0,
) -> dict[str, Any]:
    params: dict[str, Any] = {"limit": int(limit), "offset": int(offset)}
    if name:
        params["name"] = name
    if competition:
        params["competition"] = competition
    query_alpha_type = alpha_type or type
    if query_alpha_type:
        params["type"] = query_alpha_type
    if status:
        params["status"] = status
    if instrument_type:
        params["settings.instrumentType"] = instrument_type
    if region:
        params["settings.region"] = region
    if universe:
        params["settings.universe"] = universe
    if delay is not None:
        params["settings.delay"] = int(delay)
    if decay is not None:
        params["settings.decay"] = int(decay)
    if language:
        params["settings.language"] = language
    if neutralization:
        params["settings.neutralization"] = neutralization
    if pasteurization:
        params["settings.pasteurization"] = pasteurization
    if unit_handling:
        params["settings.unitHandling"] = unit_handling
    if nan_handling:
        params["settings.nanHandling"] = nan_handling
    params.update(build_filter_params("settings.truncation", truncation))
    if order:
        params["order"] = order
    if hidden is not None:
        params["hidden"] = str(bool(hidden)).lower()
    if favorite is not None:
        params["favorite"] = str(bool(favorite)).lower()
    if category:
        params["category"] = category
    if color:
        params["color"] = color
    if tag:
        params["tag"] = tag
    if stage:
        params["stage"] = stage
    for field_name, value in (
        ("dateCreated", date_created),
        ("dateSubmitted", date_submitted),
        ("startDate", start_date),
        ("is.sharpe", sharpe),
        ("is.fitness", fitness),
        ("is.turnover", turnover),
        ("is.prodCorrelation", prod_correlation),
        ("is.selfCorrelation", self_correlation),
        ("is.returns", returns),
        ("is.pnl", pnl),
        ("is.drawdown", drawdown),
        ("is.margin", margin),
        ("is.bookSize", book_size),
        ("is.longCount", long_count),
        ("is.shortCount", short_count),
        ("os.sharpe", os_sharpe),
        ("os.fitness", os_fitness),
        ("os.turnover", os_turnover),
        ("os.returns", os_returns),
        ("os.pnl", os_pnl),
        ("os.drawdown", os_drawdown),
        ("os.margin", os_margin),
        ("os.longCount", os_long_count),
        ("os.shortCount", os_short_count),
    ):
        params.update(build_filter_params(field_name, value))
    return params
