from supermarket_linkage.pipeline.consts import STATUS_NO_MATCH
from supermarket_linkage.schemas.line_result_table import LineResultColumns

__all__ = ["CSV_COLUMNS", "STATUS_NO_MATCH"]

CSV_COLUMNS: tuple[str, ...] = (
    LineResultColumns.QUERY,
    LineResultColumns.STATUS,
    LineResultColumns.PRODUCT_ID,
    LineResultColumns.NAME,
    LineResultColumns.BRAND,
    LineResultColumns.UNITS_NEEDED,
    LineResultColumns.PACK_SIZE_MISSING,
    LineResultColumns.EFFECTIVE_PRICE_EUR,
    LineResultColumns.LINE_TOTAL_PRICE_EUR,
    LineResultColumns.PRICE_PER_KG,
    LineResultColumns.PRODUCT_URL,
)
