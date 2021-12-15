# Copyright The PyTorch Lightning team.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
from typing import Dict, List, Tuple

import numpy as np

from flash.core.utilities.imports import _PANDAS_AVAILABLE

if _PANDAS_AVAILABLE:
    import pandas as pd
    from pandas.core.frame import DataFrame
else:
    DataFrame = None


def _impute(df: DataFrame, num_cols: List) -> DataFrame:
    for col in num_cols:
        df[col] = df[col].fillna(df[col].median())
    return df


def _compute_normalization(df: DataFrame, num_cols: List) -> Tuple:
    return df[num_cols].mean(), df[num_cols].std()


def _normalize(df: DataFrame, num_cols: List, mean: DataFrame, std: DataFrame) -> DataFrame:
    df[num_cols] = (df[num_cols] - mean) / std
    return df


def _generate_codes(df: DataFrame, cat_cols: List) -> dict:
    tmp = df.copy()
    for col in cat_cols:
        tmp[col] = tmp[col].astype("category").cat.as_ordered()

    # list of categories for each column (always a column for None)
    codes = {col: list(tmp[col].cat.categories) for col in cat_cols}

    return codes


def _categorize(df: DataFrame, cat_cols: List, codes) -> DataFrame:
    # apply codes to each column
    for col in cat_cols:
        df[col] = pd.Categorical(df[col], categories=codes[col], ordered=True)
    df[cat_cols] = df[cat_cols].apply(lambda x: x.cat.codes)

    # we add one here as Nones are -1, so they turn into 0's
    df[cat_cols] = df[cat_cols] + 1
    return df


def _pre_transform(
    df: DataFrame,
    num_cols: List[str],
    cat_cols: List[str],
    codes: Dict,
    mean: DataFrame,
    std: DataFrame,
    target: str = None,
    target_codes: Dict = None,
) -> DataFrame:
    df = _impute(df, num_cols)
    df = _normalize(df, num_cols, mean=mean, std=std)
    df = _categorize(df, cat_cols, codes=codes)
    if target_codes and target:
        df = _categorize(df, [target], codes=target_codes)
    return df


def _to_cat_vars_numpy(df: DataFrame, cat_cols: List[str]) -> list:
    return [c.to_numpy().astype(np.int64) for n, c in df[cat_cols].items()]


def _to_num_vars_numpy(df: DataFrame, num_cols: List[str]) -> list:
    return [c.to_numpy().astype(np.float32) for n, c in df[num_cols].items()]
