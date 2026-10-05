"""Validated, pure transformations used by both the UI and AI assistant."""

from __future__ import annotations

import math
from typing import Any, Callable, Literal

import pandas as pd
from pandas.api.types import (
    is_bool_dtype,
    is_datetime64_any_dtype,
    is_numeric_dtype,
)
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from app.models.schemas import Transformation
from app.utils.errors import DataFlowError


class Parameters(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)


class NoParameters(Parameters):
    pass


class OptionalColumns(Parameters):
    columns: list[str] | None = None


class RemoveDuplicates(Parameters):
    subset: list[str] | None = None


class Columns(Parameters):
    columns: list[str] = Field(min_length=1)


class Column(Parameters):
    column: str = Field(min_length=1)


Scalar = str | int | float | bool


class FillMissing(Column):
    method: Literal["mean", "median", "zero", "custom"]
    value: Scalar | None = None

    @model_validator(mode="after")
    def validate_custom_value(self) -> "FillMissing":
        if self.method == "custom" and self.value is None:
            raise ValueError("A non-null value is required for custom filling.")
        if self.method != "custom" and "value" in self.model_fields_set:
            raise ValueError("value is only accepted with method custom.")
        return self


class RenameColumn(Column):
    new_name: str = Field(min_length=1, max_length=200)


class Filter(Column):
    operator: Literal[
        ">", ">=", "<", "<=", "==", "!=", "contains", "not_contains", "is_missing", "not_missing"
    ]
    value: Scalar | None = None

    @model_validator(mode="after")
    def validate_filter_value(self) -> "Filter":
        if self.operator in ("is_missing", "not_missing"):
            if "value" in self.model_fields_set:
                raise ValueError("Missing-value filters do not take a value.")
        elif self.value is None:
            raise ValueError("This filter requires a non-null value.")
        return self


class Sort(Column):
    ascending: bool = True


class ConvertType(Column):
    type: Literal["numeric", "text", "boolean", "datetime"]


class ChangeCase(Column):
    case: Literal["upper", "lower"]


class DetectOutliers(Column):
    method: Literal["iqr"] = "iqr"


def fail(message: str) -> None:
    raise DataFlowError(message, status_code=400, code="invalid_transformation")


def require_columns(df: pd.DataFrame, columns: list[str]) -> None:
    if not columns:
        fail("Choose at least one column.")
    if len(columns) != len(set(columns)):
        fail("Column selections cannot contain duplicate names.")
    missing = [name for name in columns if name not in df.columns]
    if missing:
        fail(f"Unknown column: {missing[0]}.")


def numeric(series: pd.Series) -> bool:
    return is_numeric_dtype(series.dtype) and not is_bool_dtype(series.dtype)


def require_numeric(series: pd.Series, column: str) -> None:
    if not numeric(series):
        fail(f"Column '{column}' must be numeric for this operation.")
    if not series.dropna().map(lambda value: math.isfinite(float(value))).all():
        fail(f"Column '{column}' contains non-finite numeric values.")


def require_text(series: pd.Series, column: str) -> None:
    if numeric(series) or is_bool_dtype(series.dtype) or is_datetime64_any_dtype(series.dtype):
        fail(f"Column '{column}' must contain text for this operation.")
    if not series.dropna().map(lambda value: isinstance(value, str)).all():
        fail(f"Column '{column}' contains mixed values; convert it to text first.")


def remove_duplicates(df: pd.DataFrame, params: RemoveDuplicates) -> pd.DataFrame:
    if params.subset is not None:
        require_columns(df, params.subset)
    return df.drop_duplicates(subset=params.subset)


def drop_missing(df: pd.DataFrame, params: OptionalColumns) -> pd.DataFrame:
    if params.columns is not None:
        require_columns(df, params.columns)
    return df.dropna(subset=params.columns)


def fill_missing(df: pd.DataFrame, params: FillMissing) -> pd.DataFrame:
    series = df[params.column]
    value = params.value
    if params.method != "custom":
        require_numeric(series, params.column)
        value = 0 if params.method == "zero" else getattr(series, params.method)()
        if pd.isna(value):
            fail(f"Column '{params.column}' has no numeric values to calculate {params.method}.")
        if not math.isfinite(float(value)):
            fail("The calculated fill value is not a finite number.")
    elif numeric(series):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            fail("A numeric column requires a numeric custom value.")
        if not math.isfinite(float(value)):
            fail("The custom value must be a finite number.")
    elif is_bool_dtype(series.dtype):
        if not isinstance(value, bool):
            fail("A boolean column requires a boolean custom value.")
    else:
        require_text(series, params.column)
        if not isinstance(value, str):
            fail("A text column requires a text custom value.")
    # Nullable integer columns need widening when the mean or custom value is fractional.
    if numeric(series) and value is not None and float(value) % 1:
        series = series.astype("Float64")
    df[params.column] = series.fillna(value)
    return df


def rename_column(df: pd.DataFrame, params: RenameColumn) -> pd.DataFrame:
    if not params.new_name.strip():
        fail("The new column name cannot be blank.")
    if params.new_name != params.column and params.new_name in df.columns:
        fail(f"Column '{params.new_name}' already exists.")
    return df.rename(columns={params.column: params.new_name})


def delete_columns(df: pd.DataFrame, params: Columns) -> pd.DataFrame:
    require_columns(df, params.columns)
    if len(params.columns) == len(df.columns):
        fail("A dataset must keep at least one column.")
    return df.drop(columns=params.columns)


def filter_rows(df: pd.DataFrame, params: Filter) -> pd.DataFrame:
    series = df[params.column]
    value = params.value
    if params.operator == "is_missing":
        mask = series.isna()
    elif params.operator == "not_missing":
        mask = series.notna()
    elif params.operator in ("contains", "not_contains"):
        require_text(series, params.column)
        if not isinstance(value, str):
            fail("Text containment filters require a text value.")
        mask = series.astype("string").str.contains(value, regex=False, na=False)
        if params.operator == "not_contains":
            mask = ~mask & series.notna()
    else:
        if numeric(series):
            require_numeric(series, params.column)
            if isinstance(value, bool) or not isinstance(value, (float, int)):
                fail("Numeric filters require a numeric value.")
        elif is_bool_dtype(series.dtype):
            if params.operator not in ("==", "!=") or not isinstance(value, bool):
                fail("Boolean filters require == or != and a boolean value.")
        elif is_datetime64_any_dtype(series.dtype):
            if not isinstance(value, str):
                fail("Datetime filters require an ISO date or timestamp string.")
            value = pd.to_datetime(value, errors="coerce", utc=True)
            if pd.isna(value):
                fail("The filter value is not a valid date or timestamp.")
            if series.dt.tz is None:
                value = value.tz_localize(None)
        else:
            require_text(series, params.column)
            if not isinstance(value, str):
                fail("Text filters require a text value.")
        comparators: dict[str, Callable[[Any], pd.Series]] = {
            ">": series.gt, ">=": series.ge, "<": series.lt, "<=": series.le,
            "==": series.eq, "!=": series.ne,
        }
        mask = comparators[params.operator](value) & series.notna()
    return df.loc[mask.fillna(False)]


def sort_rows(df: pd.DataFrame, params: Sort) -> pd.DataFrame:
    return df.sort_values(params.column, ascending=params.ascending, kind="stable", na_position="last")


def convert_type(df: pd.DataFrame, params: ConvertType) -> pd.DataFrame:
    series = df[params.column]
    if params.type == "text":
        converted = series.astype("string")
    elif params.type == "numeric":
        converted = pd.to_numeric(series, errors="coerce")
        if (series.notna() & converted.isna()).any():
            fail(f"Column '{params.column}' contains values that cannot be converted to numeric.")
        require_numeric(converted, params.column)
    elif params.type == "datetime":
        converted = pd.to_datetime(series, errors="coerce", format="mixed", utc=True)
        if (series.notna() & converted.isna()).any():
            fail(f"Column '{params.column}' contains values that cannot be converted to datetime.")
    else:
        truth = {"true", "yes", "y", "t", "1"}
        falsehood = {"false", "no", "n", "f", "0"}

        def boolean(value: Any) -> bool | Any:
            if pd.isna(value):
                return pd.NA
            if isinstance(value, bool):
                return value
            if isinstance(value, (int, float)) and value in (0, 1):
                return bool(value)
            if isinstance(value, str):
                normalized = value.strip().lower()
                if normalized in truth:
                    return True
                if normalized in falsehood:
                    return False
            fail(f"Column '{params.column}' contains a value that cannot be converted to boolean.")

        converted = series.map(boolean).astype("boolean")
    df[params.column] = converted
    return df


def trim_whitespace(df: pd.DataFrame, params: OptionalColumns) -> pd.DataFrame:
    columns = params.columns
    if columns is None:
        columns = [name for name in df.columns if not numeric(df[name])
                   and not is_bool_dtype(df[name].dtype) and not is_datetime64_any_dtype(df[name].dtype)]
    elif columns:
        require_columns(df, columns)
    else:
        fail("Choose at least one column.")
    for column in columns:
        require_text(df[column], column)
        df[column] = df[column].astype("string").str.strip()
    return df


def change_case(df: pd.DataFrame, params: ChangeCase) -> pd.DataFrame:
    require_text(df[params.column], params.column)
    df[params.column] = getattr(df[params.column].astype("string").str, params.case)()
    return df


def detect_outliers(df: pd.DataFrame, params: DetectOutliers) -> pd.DataFrame:
    series = df[params.column]
    require_numeric(series, params.column)
    flag_column = f"{params.column}_outlier"
    if flag_column in df.columns:
        fail(f"Column '{flag_column}' already exists; rename or delete it first.")
    q1, q3 = series.quantile([0.25, 0.75])
    iqr = q3 - q1
    df[flag_column] = ((series < q1 - 1.5 * iqr) | (series > q3 + 1.5 * iqr)).fillna(False)
    return df


def select_columns(df: pd.DataFrame, params: Columns) -> pd.DataFrame:
    require_columns(df, params.columns)
    return df.loc[:, params.columns]


# Registry is the single allowlist for human and model-generated requests.
TRANSFORMATIONS: dict[str, tuple[type[Parameters], Callable[..., pd.DataFrame]]] = {
    "remove_duplicates": (RemoveDuplicates, remove_duplicates),
    "drop_missing": (OptionalColumns, drop_missing),
    "fill_missing": (FillMissing, fill_missing),
    "rename_column": (RenameColumn, rename_column),
    "delete_columns": (Columns, delete_columns),
    "filter": (Filter, filter_rows),
    "sort": (Sort, sort_rows),
    "convert_type": (ConvertType, convert_type),
    "trim_whitespace": (OptionalColumns, trim_whitespace),
    "change_case": (ChangeCase, change_case),
    "detect_outliers": (DetectOutliers, detect_outliers),
    "select_columns": (Columns, select_columns),
}


def apply_transformation(df: pd.DataFrame, operation: Transformation) -> pd.DataFrame:
    """Return a transformed copy, or reject the entire operation without side effects."""
    registered = TRANSFORMATIONS.get(operation.operation)
    if registered is None:
        fail(f"Unknown transformation: {operation.operation}.")
    parameter_model, function = registered
    try:
        params = parameter_model.model_validate(operation.parameters)
    except ValidationError as error:
        first = error.errors(include_url=False)[0]
        field = ".".join(str(part) for part in first["loc"]) or "parameters"
        fail(f"Invalid {operation.operation} parameter '{field}': {first['msg']}.")
    if hasattr(params, "column"):
        require_columns(df, [params.column])
    try:
        result = function(df.copy(deep=True), params)
        if not len(result.columns):
            fail("A dataset must keep at least one column.")
        if result.columns.duplicated().any():
            fail("A transformation cannot create duplicate column names.")
        return result.reset_index(drop=True)
    except DataFlowError:
        raise
    except (ValueError, TypeError, OverflowError, KeyError) as error:
        # Pandas implementation details and arbitrary values are not exposed to clients.
        raise DataFlowError(
            f"Unable to apply {operation.operation}; check the column type and parameters.",
            status_code=400, code="invalid_transformation",
        ) from error
