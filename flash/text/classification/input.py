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
from functools import partial
from typing import Any, Dict, List, Optional, Union

import pandas as pd

from flash.core.data.io.classification_input import ClassificationInput, ClassificationState
from flash.core.data.io.input import DataKeys
from flash.core.data.utilities.classification import TargetMode
from flash.core.data.utilities.paths import PATH_TYPE
from flash.core.integrations.transformers.states import TransformersBackboneState
from flash.core.utilities.imports import _TEXT_AVAILABLE, requires

if _TEXT_AVAILABLE:
    from datasets import Dataset, load_dataset
else:
    Dataset = object


class TextClassificationInput(ClassificationInput):
    @staticmethod
    def _resolve_target(target_keys: Union[str, List[str]], element: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(target_keys, List):
            element[DataKeys.TARGET] = element.pop(target_keys)
        else:
            element[DataKeys.TARGET] = [element[target_key] for target_key in target_keys]
        return element

    @requires("text")
    def load_data(
        self,
        hf_dataset: Dataset,
        input_key: str,
        target_keys: Optional[Union[str, List[str]]] = None,
        max_length: int = 128,
    ) -> Dataset:
        """Loads data into HuggingFace datasets.Dataset."""
        self.max_length = max_length

        if not self.predicting:
            hf_dataset = hf_dataset.map(partial(self._resolve_target, target_keys))
            targets = hf_dataset.to_dict()[DataKeys.TARGET]
            self.load_target_metadata(targets)

            # If we had binary multi-class targets then we also know the labels (column names)
            if self.target_mode is TargetMode.MULTI_BINARY and isinstance(target_keys, List):
                classification_state = self.get_state(ClassificationState)
                self.set_state(ClassificationState(target_keys, classification_state.num_classes))

        # remove extra columns
        extra_columns = set(hf_dataset.column_names) - {input_key, DataKeys.TARGET}
        hf_dataset = hf_dataset.remove_columns(extra_columns)

        if input_key != DataKeys.INPUT:
            hf_dataset = hf_dataset.rename_column(input_key, DataKeys.INPUT)

        return hf_dataset

    def load_sample(self, sample: Dict[str, Any]) -> Any:
        tokenized_sample = self.get_state(TransformersBackboneState).tokenizer(
            sample[DataKeys.INPUT], max_length=self.max_length, truncation=True, padding="max_length"
        )
        tokenized_sample = tokenized_sample.data
        if DataKeys.TARGET in sample:
            tokenized_sample[DataKeys.TARGET] = self.format_target(sample[DataKeys.TARGET])
        return tokenized_sample


class TextClassificationCSVInput(TextClassificationInput):
    @requires("text")
    def load_data(
        self,
        csv_file: PATH_TYPE,
        input_key: str,
        target_keys: Optional[Union[str, List[str]]] = None,
        max_length: int = 128,
    ) -> Dataset:
        dataset_dict = load_dataset("csv", data_files={"data": str(csv_file)})
        return super().load_data(dataset_dict["data"], input_key, target_keys, max_length)


class TextClassificationJSONInput(TextClassificationInput):
    @requires("text")
    def load_data(
        self,
        json_file: PATH_TYPE,
        field: str,
        input_key: str,
        target_keys: Optional[Union[str, List[str]]] = None,
        max_length: int = 128,
    ) -> Dataset:
        dataset_dict = load_dataset("json", data_files={"data": str(json_file)}, field=field)
        return super().load_data(dataset_dict["data"], input_key, target_keys, max_length)


class TextClassificationDataFrameInput(TextClassificationInput):
    @requires("text")
    def load_data(
        self,
        data_frame: pd.DataFrame,
        input_key: str,
        target_keys: Optional[Union[str, List[str]]] = None,
        max_length: int = 128,
    ) -> Dataset:
        return super().load_data(Dataset.from_pandas(data_frame), input_key, target_keys, max_length)


class TextClassificationParquetInput(TextClassificationInput):
    @requires("text")
    def load_data(
        self,
        parquet_file: PATH_TYPE,
        input_key: str,
        target_keys: Optional[Union[str, List[str]]] = None,
        max_length: int = 128,
    ) -> Dataset:
        return super().load_data(Dataset.from_parquet(str(parquet_file)), input_key, target_keys, max_length)


class TextClassificationListInput(TextClassificationInput):
    @requires("text")
    def load_data(
        self,
        inputs: List[str],
        targets: Optional[List[Any]] = None,
        max_length: int = 128,
    ) -> Dataset:
        if targets is not None:
            hf_dataset = Dataset.from_dict({DataKeys.INPUT: inputs, DataKeys.TARGET: targets})
        else:
            hf_dataset = Dataset.from_dict({DataKeys.INPUT: inputs})
        return super().load_data(hf_dataset, DataKeys.INPUT, DataKeys.TARGET, max_length)
