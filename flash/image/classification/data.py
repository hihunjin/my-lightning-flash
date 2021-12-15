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
from typing import Any, Callable, Collection, Dict, List, Optional, Sequence, Type, Union

import numpy as np
import pandas as pd
import torch
from torch.utils.data import Dataset

from flash.core.data.base_viz import BaseVisualization
from flash.core.data.callback import BaseDataFetcher
from flash.core.data.data_module import DataModule, DatasetInput
from flash.core.data.data_pipeline import DataPipelineState
from flash.core.data.io.input import DataKeys, Input
from flash.core.data.io.input_transform import INPUT_TRANSFORM_TYPE
from flash.core.data.utilities.paths import PATH_TYPE
from flash.core.integrations.labelstudio.input import _parse_labelstudio_arguments, LabelStudioImageClassificationInput
from flash.core.registry import FlashRegistry
from flash.core.utilities.imports import _MATPLOTLIB_AVAILABLE, Image, requires
from flash.core.utilities.stages import RunningStage
from flash.image.classification.input import (
    ImageClassificationCSVInput,
    ImageClassificationDataFrameInput,
    ImageClassificationFiftyOneInput,
    ImageClassificationFilesInput,
    ImageClassificationFolderInput,
    ImageClassificationNumpyInput,
    ImageClassificationTensorInput,
)
from flash.image.classification.transforms import ImageClassificationInputTransform
from flash.image.data import SampleCollection

if _MATPLOTLIB_AVAILABLE:
    import matplotlib.pyplot as plt
else:
    plt = None


class ImageClassificationData(DataModule):
    """Data module for image classification tasks."""

    input_transforms_registry = FlashRegistry("input_transforms")
    input_transform_cls = ImageClassificationInputTransform

    @classmethod
    def from_files(
        cls,
        train_files: Optional[Sequence[str]] = None,
        train_targets: Optional[Sequence[Any]] = None,
        val_files: Optional[Sequence[str]] = None,
        val_targets: Optional[Sequence[Any]] = None,
        test_files: Optional[Sequence[str]] = None,
        test_targets: Optional[Sequence[Any]] = None,
        predict_files: Optional[Sequence[str]] = None,
        train_transform: INPUT_TRANSFORM_TYPE = ImageClassificationInputTransform,
        val_transform: INPUT_TRANSFORM_TYPE = ImageClassificationInputTransform,
        test_transform: INPUT_TRANSFORM_TYPE = ImageClassificationInputTransform,
        predict_transform: INPUT_TRANSFORM_TYPE = ImageClassificationInputTransform,
        input_cls: Type[Input] = ImageClassificationFilesInput,
        transform_kwargs: Optional[Dict] = None,
        **data_module_kwargs: Any,
    ) -> "ImageClassificationData":

        ds_kw = dict(
            data_pipeline_state=DataPipelineState(),
            transform_kwargs=transform_kwargs,
            input_transforms_registry=cls.input_transforms_registry,
        )

        return cls(
            input_cls(RunningStage.TRAINING, train_files, train_targets, transform=train_transform, **ds_kw),
            input_cls(RunningStage.VALIDATING, val_files, val_targets, transform=val_transform, **ds_kw),
            input_cls(RunningStage.TESTING, test_files, test_targets, transform=test_transform, **ds_kw),
            input_cls(RunningStage.PREDICTING, predict_files, transform=predict_transform, **ds_kw),
            **data_module_kwargs,
        )

    @classmethod
    def from_folders(
        cls,
        train_folder: Optional[str] = None,
        val_folder: Optional[str] = None,
        test_folder: Optional[str] = None,
        predict_folder: Optional[str] = None,
        train_transform: INPUT_TRANSFORM_TYPE = ImageClassificationInputTransform,
        val_transform: INPUT_TRANSFORM_TYPE = ImageClassificationInputTransform,
        test_transform: INPUT_TRANSFORM_TYPE = ImageClassificationInputTransform,
        predict_transform: INPUT_TRANSFORM_TYPE = ImageClassificationInputTransform,
        input_cls: Type[Input] = ImageClassificationFolderInput,
        transform_kwargs: Optional[Dict] = None,
        **data_module_kwargs: Any,
    ) -> "ImageClassificationData":

        ds_kw = dict(
            data_pipeline_state=DataPipelineState(),
            transform_kwargs=transform_kwargs,
            input_transforms_registry=cls.input_transforms_registry,
        )

        return cls(
            input_cls(RunningStage.TRAINING, train_folder, transform=train_transform, **ds_kw),
            input_cls(RunningStage.VALIDATING, val_folder, transform=val_transform, **ds_kw),
            input_cls(RunningStage.TESTING, test_folder, transform=test_transform, **ds_kw),
            input_cls(RunningStage.PREDICTING, predict_folder, transform=predict_transform, **ds_kw),
            **data_module_kwargs,
        )

    @classmethod
    def from_numpy(
        cls,
        train_data: Optional[Collection[np.ndarray]] = None,
        train_targets: Optional[Collection[Any]] = None,
        val_data: Optional[Collection[np.ndarray]] = None,
        val_targets: Optional[Sequence[Any]] = None,
        test_data: Optional[Collection[np.ndarray]] = None,
        test_targets: Optional[Sequence[Any]] = None,
        predict_data: Optional[Collection[np.ndarray]] = None,
        train_transform: INPUT_TRANSFORM_TYPE = ImageClassificationInputTransform,
        val_transform: INPUT_TRANSFORM_TYPE = ImageClassificationInputTransform,
        test_transform: INPUT_TRANSFORM_TYPE = ImageClassificationInputTransform,
        predict_transform: INPUT_TRANSFORM_TYPE = ImageClassificationInputTransform,
        input_cls: Type[Input] = ImageClassificationNumpyInput,
        transform_kwargs: Optional[Dict] = None,
        **data_module_kwargs: Any,
    ) -> "ImageClassificationData":

        ds_kw = dict(
            data_pipeline_state=DataPipelineState(),
            transform_kwargs=transform_kwargs,
            input_transforms_registry=cls.input_transforms_registry,
        )

        return cls(
            input_cls(RunningStage.TRAINING, train_data, train_targets, transform=train_transform, **ds_kw),
            input_cls(RunningStage.VALIDATING, val_data, val_targets, transform=val_transform, **ds_kw),
            input_cls(RunningStage.TESTING, test_data, test_targets, transform=test_transform, **ds_kw),
            input_cls(RunningStage.PREDICTING, predict_data, transform=predict_transform, **ds_kw),
            **data_module_kwargs,
        )

    @classmethod
    def from_tensors(
        cls,
        train_data: Optional[Collection[torch.Tensor]] = None,
        train_targets: Optional[Collection[Any]] = None,
        val_data: Optional[Collection[torch.Tensor]] = None,
        val_targets: Optional[Sequence[Any]] = None,
        test_data: Optional[Collection[torch.Tensor]] = None,
        test_targets: Optional[Sequence[Any]] = None,
        predict_data: Optional[Collection[torch.Tensor]] = None,
        train_transform: INPUT_TRANSFORM_TYPE = ImageClassificationInputTransform,
        val_transform: INPUT_TRANSFORM_TYPE = ImageClassificationInputTransform,
        test_transform: INPUT_TRANSFORM_TYPE = ImageClassificationInputTransform,
        predict_transform: INPUT_TRANSFORM_TYPE = ImageClassificationInputTransform,
        input_cls: Type[Input] = ImageClassificationTensorInput,
        transform_kwargs: Optional[Dict] = None,
        **data_module_kwargs: Any,
    ) -> "ImageClassificationData":

        ds_kw = dict(
            data_pipeline_state=DataPipelineState(),
            transform_kwargs=transform_kwargs,
            input_transforms_registry=cls.input_transforms_registry,
        )

        return cls(
            input_cls(RunningStage.TRAINING, train_data, train_targets, transform=train_transform, **ds_kw),
            input_cls(RunningStage.VALIDATING, val_data, val_targets, transform=val_transform, **ds_kw),
            input_cls(RunningStage.TESTING, test_data, test_targets, transform=test_transform, **ds_kw),
            input_cls(RunningStage.PREDICTING, predict_data, transform=predict_transform, **ds_kw),
            **data_module_kwargs,
        )

    @classmethod
    def from_data_frame(
        cls,
        input_field: str,
        target_fields: Optional[Union[str, Sequence[str]]] = None,
        train_data_frame: Optional[pd.DataFrame] = None,
        train_images_root: Optional[str] = None,
        train_resolver: Optional[Callable[[str, str], str]] = None,
        val_data_frame: Optional[pd.DataFrame] = None,
        val_images_root: Optional[str] = None,
        val_resolver: Optional[Callable[[str, str], str]] = None,
        test_data_frame: Optional[pd.DataFrame] = None,
        test_images_root: Optional[str] = None,
        test_resolver: Optional[Callable[[str, str], str]] = None,
        predict_data_frame: Optional[pd.DataFrame] = None,
        predict_images_root: Optional[str] = None,
        predict_resolver: Optional[Callable[[str, str], str]] = None,
        train_transform: INPUT_TRANSFORM_TYPE = ImageClassificationInputTransform,
        val_transform: INPUT_TRANSFORM_TYPE = ImageClassificationInputTransform,
        test_transform: INPUT_TRANSFORM_TYPE = ImageClassificationInputTransform,
        predict_transform: INPUT_TRANSFORM_TYPE = ImageClassificationInputTransform,
        input_cls: Type[Input] = ImageClassificationDataFrameInput,
        transform_kwargs: Optional[Dict] = None,
        **data_module_kwargs: Any,
    ) -> "ImageClassificationData":

        ds_kw = dict(
            data_pipeline_state=DataPipelineState(),
            transform_kwargs=transform_kwargs,
            input_transforms_registry=cls.input_transforms_registry,
        )

        train_data = (train_data_frame, input_field, target_fields, train_images_root, train_resolver)
        val_data = (val_data_frame, input_field, target_fields, val_images_root, val_resolver)
        test_data = (test_data_frame, input_field, target_fields, test_images_root, test_resolver)
        predict_data = (predict_data_frame, input_field, predict_images_root, predict_resolver)

        return cls(
            input_cls(RunningStage.TRAINING, *train_data, transform=train_transform, **ds_kw),
            input_cls(RunningStage.VALIDATING, *val_data, transform=val_transform, **ds_kw),
            input_cls(RunningStage.TESTING, *test_data, transform=test_transform, **ds_kw),
            input_cls(RunningStage.PREDICTING, *predict_data, transform=predict_transform, **ds_kw),
            **data_module_kwargs,
        )

    @classmethod
    def from_csv(
        cls,
        input_field: str,
        target_fields: Optional[Union[str, List[str]]] = None,
        train_file: Optional[PATH_TYPE] = None,
        train_images_root: Optional[PATH_TYPE] = None,
        train_resolver: Optional[Callable[[PATH_TYPE, Any], PATH_TYPE]] = None,
        val_file: Optional[PATH_TYPE] = None,
        val_images_root: Optional[PATH_TYPE] = None,
        val_resolver: Optional[Callable[[PATH_TYPE, Any], PATH_TYPE]] = None,
        test_file: Optional[str] = None,
        test_images_root: Optional[str] = None,
        test_resolver: Optional[Callable[[PATH_TYPE, Any], PATH_TYPE]] = None,
        predict_file: Optional[str] = None,
        predict_images_root: Optional[str] = None,
        predict_resolver: Optional[Callable[[PATH_TYPE, Any], PATH_TYPE]] = None,
        train_transform: INPUT_TRANSFORM_TYPE = ImageClassificationInputTransform,
        val_transform: INPUT_TRANSFORM_TYPE = ImageClassificationInputTransform,
        test_transform: INPUT_TRANSFORM_TYPE = ImageClassificationInputTransform,
        predict_transform: INPUT_TRANSFORM_TYPE = ImageClassificationInputTransform,
        input_cls: Type[Input] = ImageClassificationCSVInput,
        transform_kwargs: Optional[Dict] = None,
        **data_module_kwargs: Any,
    ) -> "ImageClassificationData":

        ds_kw = dict(
            data_pipeline_state=DataPipelineState(),
            transform_kwargs=transform_kwargs,
            input_transforms_registry=cls.input_transforms_registry,
        )

        train_data = (train_file, input_field, target_fields, train_images_root, train_resolver)
        val_data = (val_file, input_field, target_fields, val_images_root, val_resolver)
        test_data = (test_file, input_field, target_fields, test_images_root, test_resolver)
        predict_data = (predict_file, input_field, predict_images_root, predict_resolver)

        return cls(
            input_cls(RunningStage.TRAINING, *train_data, transform=train_transform, **ds_kw),
            input_cls(RunningStage.VALIDATING, *val_data, transform=val_transform, **ds_kw),
            input_cls(RunningStage.TESTING, *test_data, transform=test_transform, **ds_kw),
            input_cls(RunningStage.PREDICTING, *predict_data, transform=predict_transform, **ds_kw),
            **data_module_kwargs,
        )

    @classmethod
    @requires("fiftyone")
    def from_fiftyone(
        cls,
        train_dataset: Optional[SampleCollection] = None,
        val_dataset: Optional[SampleCollection] = None,
        test_dataset: Optional[SampleCollection] = None,
        predict_dataset: Optional[SampleCollection] = None,
        label_field: str = "ground_truth",
        train_transform: INPUT_TRANSFORM_TYPE = ImageClassificationInputTransform,
        val_transform: INPUT_TRANSFORM_TYPE = ImageClassificationInputTransform,
        test_transform: INPUT_TRANSFORM_TYPE = ImageClassificationInputTransform,
        predict_transform: INPUT_TRANSFORM_TYPE = ImageClassificationInputTransform,
        input_cls: Type[Input] = ImageClassificationFiftyOneInput,
        transform_kwargs: Optional[Dict] = None,
        **data_module_kwargs,
    ) -> "ImageClassificationData":

        ds_kw = dict(
            data_pipeline_state=DataPipelineState(),
            transform_kwargs=transform_kwargs,
            input_transforms_registry=cls.input_transforms_registry,
            label_field=label_field,
        )

        return cls(
            input_cls(RunningStage.TRAINING, train_dataset, transform=train_transform, **ds_kw),
            input_cls(RunningStage.VALIDATING, val_dataset, transform=val_transform, **ds_kw),
            input_cls(RunningStage.TESTING, test_dataset, transform=test_transform, **ds_kw),
            input_cls(RunningStage.PREDICTING, predict_dataset, transform=predict_transform, **ds_kw),
            **data_module_kwargs,
        )

    @classmethod
    def from_labelstudio(
        cls,
        export_json: str = None,
        train_export_json: str = None,
        val_export_json: str = None,
        test_export_json: str = None,
        predict_export_json: str = None,
        data_folder: str = None,
        train_data_folder: str = None,
        val_data_folder: str = None,
        test_data_folder: str = None,
        predict_data_folder: str = None,
        train_transform: INPUT_TRANSFORM_TYPE = ImageClassificationInputTransform,
        val_transform: INPUT_TRANSFORM_TYPE = ImageClassificationInputTransform,
        test_transform: INPUT_TRANSFORM_TYPE = ImageClassificationInputTransform,
        predict_transform: INPUT_TRANSFORM_TYPE = ImageClassificationInputTransform,
        input_cls: Type[Input] = LabelStudioImageClassificationInput,
        transform_kwargs: Optional[Dict] = None,
        val_split: Optional[float] = None,
        multi_label: Optional[bool] = False,
        **data_module_kwargs: Any,
    ) -> "ImageClassificationData":
        """Creates a :class:`~flash.core.data.data_module.DataModule` object
        from the given export file and data directory using the
        :class:`~flash.core.data.io.input.Input` of name
        :attr:`~flash.core.data.io.input.InputFormat.FOLDERS`
        from the passed or constructed :class:`~flash.core.data.io.input_transform.InputTransform`.

        Args:
            export_json: path to label studio export file
            train_export_json: path to label studio export file for train set,
            overrides export_json if specified
            val_export_json: path to label studio export file for validation
            test_export_json: path to label studio export file for test
            predict_export_json: path to label studio export file for predict
            data_folder: path to label studio data folder
            train_data_folder: path to label studio data folder for train data set,
            overrides data_folder if specified
            val_data_folder: path to label studio data folder for validation data
            test_data_folder: path to label studio data folder for test data
            predict_data_folder: path to label studio data folder for predict data
            train_transform: The dictionary of transforms to use during training which maps
                :class:`~flash.core.data.io.input_transform.InputTransform` hook names to callable transforms.
            val_transform: The dictionary of transforms to use during validation which maps
                :class:`~flash.core.data.io.input_transform.InputTransform` hook names to callable transforms.
            test_transform: The dictionary of transforms to use during testing which maps
                :class:`~flash.core.data.io.input_transform.InputTransform` hook names to callable transforms.
            predict_transform: The dictionary of transforms to use during predicting which maps
                :class:`~flash.core.data.io.input_transform.InputTransform` hook names to callable transforms.
            data_fetcher: The :class:`~flash.core.data.callback.BaseDataFetcher` to pass to the
                :class:`~flash.core.data.data_module.DataModule`.
            input_transform: The :class:`~flash.core.data.io.input_transform.InputTransform` to pass to the
                :class:`~flash.core.data.data_module.DataModule`. If ``None``, ``cls.input_transform_cls``
                will be constructed and used.
            val_split: The ``val_split`` argument to pass to the :class:`~flash.core.data.data_module.DataModule`.
            multi_label: Whether the labels are multi encoded
            image_size: Size of the image.
            data_module_kwargs: Additional keyword arguments to use when constructing the datamodule.

        Returns:
            The constructed data module.

        Examples::

            data_module = DataModule.from_labelstudio(
                export_json='project.json',
                data_folder='label-studio/media/upload',
                val_split=0.8,
            )
        """

        train_data, val_data, test_data, predict_data = _parse_labelstudio_arguments(
            export_json=export_json,
            train_export_json=train_export_json,
            val_export_json=val_export_json,
            test_export_json=test_export_json,
            predict_export_json=predict_export_json,
            data_folder=data_folder,
            train_data_folder=train_data_folder,
            val_data_folder=val_data_folder,
            test_data_folder=test_data_folder,
            predict_data_folder=predict_data_folder,
            val_split=val_split,
            multi_label=multi_label,
        )

        ds_kw = dict(
            data_pipeline_state=DataPipelineState(),
            transform_kwargs=transform_kwargs,
            input_transforms_registry=cls.input_transforms_registry,
        )

        return cls(
            input_cls(RunningStage.TRAINING, train_data, transform=train_transform, **ds_kw),
            input_cls(RunningStage.VALIDATING, val_data, transform=val_transform, **ds_kw),
            input_cls(RunningStage.TESTING, val_data, transform=test_transform, **ds_kw),
            input_cls(RunningStage.PREDICTING, predict_data, transform=predict_transform, **ds_kw),
            **data_module_kwargs,
        )

    @classmethod
    def from_datasets(
        cls,
        train_dataset: Optional[Dataset] = None,
        val_dataset: Optional[Dataset] = None,
        test_dataset: Optional[Dataset] = None,
        predict_dataset: Optional[Dataset] = None,
        train_transform: INPUT_TRANSFORM_TYPE = ImageClassificationInputTransform,
        val_transform: INPUT_TRANSFORM_TYPE = ImageClassificationInputTransform,
        test_transform: INPUT_TRANSFORM_TYPE = ImageClassificationInputTransform,
        predict_transform: INPUT_TRANSFORM_TYPE = ImageClassificationInputTransform,
        input_cls: Type[Input] = DatasetInput,
        transform_kwargs: Optional[Dict] = None,
        **data_module_kwargs: Any,
    ) -> "DataModule":
        """Creates a :class:`~flash.core.data.data_module.DataModule` object from the given datasets using the
        :class:`~flash.core.data.io.input.Input`
        of name :attr:`~flash.core.data.io.input.InputFormat.DATASETS`
        from the passed or constructed :class:`~flash.core.data.io.input_transform.InputTransform`.

        Args:
            train_dataset: Dataset used during training.
            val_dataset: Dataset used during validating.
            test_dataset: Dataset used during testing.
            predict_dataset: Dataset used during predicting.
            train_transform: The dictionary of transforms to use during training which maps
                :class:`~flash.core.data.io.input_transform.InputTransform` hook names to callable transforms.
            val_transform: The dictionary of transforms to use during validation which maps
                :class:`~flash.core.data.io.input_transform.InputTransform` hook names to callable transforms.
            test_transform: The dictionary of transforms to use during testing which maps
                :class:`~flash.core.data.io.input_transform.InputTransform` hook names to callable transforms.
            predict_transform: The dictionary of transforms to use during predicting which maps
                :class:`~flash.core.data.io.input_transform.InputTransform` hook names to callable transforms.
            input_cls: Input class used to create the datasets.
            transform_kwargs: Additional keyword arguments to be used when constructing the transform.
            data_module_kwargs: Additional keyword arguments to use when constructing the DataModule.

        Returns:
            The constructed data module.

        Examples::

            data_module = DataModule.from_datasets(
                train_dataset=train_dataset,
            )
        """
        ds_kw = dict(
            data_pipeline_state=DataPipelineState(),
            transform_kwargs=transform_kwargs,
            input_transforms_registry=cls.input_transforms_registry,
        )

        return cls(
            input_cls(RunningStage.TRAINING, train_dataset, transform=train_transform, **ds_kw),
            input_cls(RunningStage.VALIDATING, val_dataset, transform=val_transform, **ds_kw),
            input_cls(RunningStage.TESTING, test_dataset, transform=test_transform, **ds_kw),
            input_cls(RunningStage.PREDICTING, predict_dataset, transform=predict_transform, **ds_kw),
            **data_module_kwargs,
        )

    def set_block_viz_window(self, value: bool) -> None:
        """Setter method to switch on/off matplotlib to pop up windows."""
        self.data_fetcher.block_viz_window = value

    @staticmethod
    def configure_data_fetcher(*args, **kwargs) -> BaseDataFetcher:
        return MatplotlibVisualization(*args, **kwargs)


class MatplotlibVisualization(BaseVisualization):
    """Process and show the image batch and its associated label using matplotlib."""

    max_cols: int = 4  # maximum number of columns we accept
    block_viz_window: bool = True  # parameter to allow user to block visualisation windows

    @staticmethod
    @requires("image")
    def _to_numpy(img: Union[np.ndarray, torch.Tensor, Image.Image]) -> np.ndarray:
        out: np.ndarray
        if isinstance(img, np.ndarray):
            out = img
        elif isinstance(img, Image.Image):
            out = np.array(img)
        elif isinstance(img, torch.Tensor):
            out = img.squeeze(0).permute(1, 2, 0).cpu().numpy()
        else:
            raise TypeError(f"Unknown image type. Got: {type(img)}.")
        return out

    @requires("matplotlib")
    def _show_images_and_labels(self, data: List[Any], num_samples: int, title: str):
        # define the image grid
        cols: int = min(num_samples, self.max_cols)
        rows: int = num_samples // cols

        # create figure and set title
        fig, axs = plt.subplots(rows, cols)
        fig.suptitle(title)

        if not isinstance(axs, np.ndarray):
            axs = [axs]

        for i, ax in enumerate(axs):
            # unpack images and labels
            if isinstance(data, list):
                _img, _label = data[i][DataKeys.INPUT], data[i].get(DataKeys.TARGET, "")
            elif isinstance(data, dict):
                _img, _label = data[DataKeys.INPUT][i], data.get(DataKeys.TARGET, [""] * (i + 1))[i]
            else:
                raise TypeError(f"Unknown data type. Got: {type(data)}.")
            # convert images to numpy
            _img: np.ndarray = self._to_numpy(_img)
            if isinstance(_label, torch.Tensor):
                _label = _label.squeeze().tolist()
            # show image and set label as subplot title
            ax.imshow(_img)
            ax.set_title(str(_label))
            ax.axis("off")
        plt.show(block=self.block_viz_window)

    def show_load_sample(self, samples: List[Any], running_stage: RunningStage):
        win_title: str = f"{running_stage} - show_load_sample"
        self._show_images_and_labels(samples, len(samples), win_title)

    def show_per_sample_transform(self, samples: List[Any], running_stage: RunningStage):
        win_title: str = f"{running_stage} - show_per_sample_transform"
        self._show_images_and_labels(samples, len(samples), win_title)

    def show_per_batch_transform(self, batch: List[Any], running_stage):
        win_title: str = f"{running_stage} - show_per_batch_transform"
        self._show_images_and_labels(batch[0], batch[0][DataKeys.INPUT].shape[0], win_title)
