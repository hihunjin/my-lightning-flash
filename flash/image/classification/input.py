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
import os
from typing import Any, Callable, Dict, List, Optional, Union

import pandas as pd

from flash.core.data.io.classification_input import ClassificationInput, ClassificationState
from flash.core.data.io.input import DataKeys
from flash.core.data.utilities.classification import TargetMode
from flash.core.data.utilities.data_frame import read_csv, resolve_files, resolve_targets
from flash.core.data.utilities.paths import filter_valid_files, make_dataset, PATH_TYPE
from flash.core.data.utilities.samples import to_samples
from flash.core.integrations.fiftyone.utils import FiftyOneLabelUtilities
from flash.core.utilities.imports import requires
from flash.image.data import (
    fol,
    ImageFilesInput,
    ImageNumpyInput,
    ImageTensorInput,
    IMG_EXTENSIONS,
    NP_EXTENSIONS,
    SampleCollection,
)


class ImageClassificationFilesInput(ClassificationInput, ImageFilesInput):
    def load_data(self, files: List[PATH_TYPE], targets: Optional[List[Any]] = None) -> List[Dict[str, Any]]:
        if targets is None:
            return super().load_data(files)
        files, targets = filter_valid_files(files, targets, valid_extensions=IMG_EXTENSIONS + NP_EXTENSIONS)
        self.load_target_metadata(targets)
        return to_samples(files, targets)

    def load_sample(self, sample: Dict[str, Any]) -> Dict[str, Any]:
        sample = super().load_sample(sample)
        if DataKeys.TARGET in sample:
            sample[DataKeys.TARGET] = self.format_target(sample[DataKeys.TARGET])
        return sample


class ImageClassificationFolderInput(ImageClassificationFilesInput):
    def load_data(self, folder: PATH_TYPE) -> List[Dict[str, Any]]:
        files, targets = make_dataset(folder, extensions=IMG_EXTENSIONS + NP_EXTENSIONS)
        return super().load_data(files, targets)


class ImageClassificationFiftyOneInput(ImageClassificationFilesInput):
    @requires("fiftyone")
    def load_data(self, sample_collection: SampleCollection, label_field: str = "ground_truth") -> List[Dict[str, Any]]:
        label_utilities = FiftyOneLabelUtilities(label_field, fol.Label)
        label_utilities.validate(sample_collection)

        label_path = sample_collection._get_label_field_path(label_field, "label")[1]

        filepaths = sample_collection.values("filepath")
        targets = sample_collection.values(label_path)

        return super().load_data(filepaths, targets)

    @staticmethod
    @requires("fiftyone")
    def predict_load_data(data: SampleCollection) -> List[Dict[str, Any]]:
        return super().load_data(data.values("filepath"))


class ImageClassificationTensorInput(ClassificationInput, ImageTensorInput):
    def load_data(self, tensor: Any, targets: Optional[List[Any]] = None) -> List[Dict[str, Any]]:
        if targets is not None:
            self.load_target_metadata(targets)
        return to_samples(tensor, targets)

    def load_sample(self, sample: Dict[str, Any]) -> Dict[str, Any]:
        sample = super().load_sample(sample)
        if DataKeys.TARGET in sample:
            sample[DataKeys.TARGET] = self.format_target(sample[DataKeys.TARGET])
        return sample


class ImageClassificationNumpyInput(ClassificationInput, ImageNumpyInput):
    def load_data(self, array: Any, targets: Optional[List[Any]] = None) -> List[Dict[str, Any]]:
        if targets is not None:
            self.load_target_metadata(targets)
        return to_samples(array, targets)

    def load_sample(self, sample: Dict[str, Any]) -> Dict[str, Any]:
        sample = super().load_sample(sample)
        if DataKeys.TARGET in sample:
            sample[DataKeys.TARGET] = self.format_target(sample[DataKeys.TARGET])
        return sample


class ImageClassificationDataFrameInput(ImageClassificationFilesInput):
    def load_data(
        self,
        data_frame: pd.DataFrame,
        input_key: str,
        target_keys: Optional[Union[str, List[str]]] = None,
        root: Optional[PATH_TYPE] = None,
        resolver: Optional[Callable[[Optional[PATH_TYPE], Any], PATH_TYPE]] = None,
    ) -> List[Dict[str, Any]]:
        files = resolve_files(data_frame, input_key, root, resolver)
        if target_keys is not None:
            targets = resolve_targets(data_frame, target_keys)
        else:
            targets = None
        result = super().load_data(files, targets)

        # If we had binary multi-class targets then we also know the labels (column names)
        if self.training and self.target_mode is TargetMode.MULTI_BINARY and isinstance(target_keys, List):
            classification_state = self.get_state(ClassificationState)
            self.set_state(ClassificationState(target_keys, classification_state.num_classes))

        return result


class ImageClassificationCSVInput(ImageClassificationDataFrameInput):
    def load_data(
        self,
        csv_file: PATH_TYPE,
        input_key: str,
        target_keys: Optional[Union[str, List[str]]] = None,
        root: Optional[PATH_TYPE] = None,
        resolver: Optional[Callable[[Optional[PATH_TYPE], Any], PATH_TYPE]] = None,
    ) -> List[Dict[str, Any]]:
        data_frame = read_csv(csv_file)
        if root is None:
            root = os.path.dirname(csv_file)
        return super().load_data(data_frame, input_key, target_keys, root, resolver)
