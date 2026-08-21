"""preprocessors package."""

from supermarket_linkage.preprocessors.base_preprocessor import BasePreprocessor

__all__ = [
    "BasePreprocessor",
    "PriceNormalizer",
    "QuantityResolver",
    "TextNormalizer",
]


def __getattr__(name: str):
    if name == "PriceNormalizer":
        from supermarket_linkage.preprocessors.price_normalizer import PriceNormalizer

        return PriceNormalizer
    if name == "QuantityResolver":
        from supermarket_linkage.preprocessors.quantity_resolver import QuantityResolver

        return QuantityResolver
    if name == "TextNormalizer":
        from supermarket_linkage.preprocessors.text_normalizer import TextNormalizer

        return TextNormalizer
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
