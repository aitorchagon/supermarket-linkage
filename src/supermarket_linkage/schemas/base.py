"""Base column enum and Polars table schema helpers."""

from abc import ABC, abstractmethod
from enum import StrEnum
from typing import Any, Dict, List, Type, Union

import polars as pl


class ColumnsEnumBase(StrEnum):
    """Base StrEnum for table column names."""

    @classmethod
    def list(cls) -> List[str]:
        return [col.value for col in cls]  # type: ignore[misc]


class TableSchemaBase(ABC):
    """Abstract Polars table schema: columns enum + dtypes + enforce helpers."""

    @classmethod
    @abstractmethod
    def get_columns_enum(cls) -> Type[ColumnsEnumBase]:
        """Return the Columns StrEnum for this table."""
        pass

    @classmethod
    def columns(cls) -> List[str]:
        """Column names as strings, in enum order."""
        return cls.get_columns_enum().list()

    @classmethod
    @abstractmethod
    def dtypes(cls) -> Dict[str, Any]:
        """Map column name → Polars dtype (DataFrame schema)."""
        pass

    @classmethod
    def as_empty_dataframe(cls) -> pl.DataFrame:
        """Empty DataFrame with this schema."""
        return pl.DataFrame(schema=cls.dtypes())

    @classmethod
    def get_column_index(cls, column: Union[str, ColumnsEnumBase]) -> int:
        """Index of a column name or enum member. Raises ValueError if missing."""
        cols = cls.columns()
        enum_cls = cls.get_columns_enum()

        if isinstance(column, enum_cls):
            column = column.value

        try:
            return cols.index(column)  # type: ignore[arg-type]
        except ValueError as exc:
            raise ValueError(f"Column '{column}' not found in schema.") from exc

    @classmethod
    def enforce_schema(cls, df: pl.DataFrame) -> pl.DataFrame:
        """Cast/add/drop columns to match dtypes() order exactly."""
        # Bare ``pl.DataFrame()`` + ``pl.lit`` would yield one null row.
        if df.height == 0 and df.width == 0:
            return cls.as_empty_dataframe()

        target_schema = cls.dtypes()
        expressions = []

        for col_name, dtype in target_schema.items():
            if col_name in df.columns:
                expressions.append(pl.col(col_name).cast(dtype))
            else:
                expressions.append(pl.lit(None).cast(dtype).alias(col_name))

        return df.select(expressions)
