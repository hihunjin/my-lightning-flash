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
import warnings
from typing import Callable, Dict, List, Optional

import numpy as np
import torch
from pytorch_lightning.utilities.exceptions import MisconfigurationException
from torch.utils.data import DataLoader, Dataset, random_split

from flash.core.data.data_module import DataModule
from flash.core.data.data_pipeline import DataPipeline
from flash.core.data.io.input import InputBase
from flash.core.utilities.imports import _BAAL_AVAILABLE, requires

if _BAAL_AVAILABLE:
    from baal.active.dataset import ActiveLearningDataset
    from baal.active.heuristics import AbstractHeuristic, BALD
else:

    class AbstractHeuristic:
        pass

    class BALD(AbstractHeuristic):
        pass


def dataset_to_non_labelled_tensor(dataset: InputBase) -> torch.tensor:
    return np.zeros(len(dataset))


def filter_unlabelled_data(dataset: InputBase) -> Dataset:
    return dataset


def train_val_split(dataset: Dataset, val_size: float = 0.1):
    L = len(dataset)
    train_size = int(L * (1 - val_size))
    val_size = L - train_size
    return random_split(dataset, [train_size, val_size], generator=torch.Generator().manual_seed(42))


class ActiveLearningDataModule(DataModule):
    @requires("baal")
    def __init__(
        self,
        labelled: Optional[DataModule] = None,
        heuristic: "AbstractHeuristic" = BALD(),
        map_dataset_to_labelled: Optional[Callable] = dataset_to_non_labelled_tensor,
        filter_unlabelled_data: Optional[Callable] = filter_unlabelled_data,
        initial_num_labels: Optional[int] = None,
        query_size: int = 1,
        val_split: Optional[float] = None,
    ):
        """The `ActiveLearningDataModule` handles data manipulation for ActiveLearning.

        Args:
            labelled: DataModule containing labelled train data for research use-case.
                The labelled data would be masked.
            heuristic: Sorting algorithm used to rank samples on how likely they can help with model performance.
            map_dataset_to_labelled: Function used to emulate masking on labelled dataset.
            filter_unlabelled_data: Function used to filter the unlabelled data while computing uncertainties.
            initial_num_labels: Number of samples to randomly label to start the training with.
            query_size: Number of samples to be labelled at each Active Learning loop based on the fed heuristic.
            val_split: Float to split train dataset into train and validation set.
        """
        super().__init__(batch_size=1)
        self.labelled = labelled
        self.heuristic = heuristic
        self.map_dataset_to_labelled = map_dataset_to_labelled
        self.filter_unlabelled_data = filter_unlabelled_data
        self.initial_num_labels = initial_num_labels
        self.query_size = query_size
        self.val_split = val_split
        self._dataset: Optional[ActiveLearningDataset] = None

        if not self.labelled:
            raise MisconfigurationException("The labelled `datamodule` should be provided.")

        if not self.labelled.num_classes:
            raise MisconfigurationException("The labelled dataset should be labelled")

        if self.labelled and (self.labelled._val_input or self.labelled._predict_input):
            raise MisconfigurationException("The labelled `datamodule` should have only train data.")

        self._dataset = ActiveLearningDataset(
            self.labelled._train_input, labelled=self.map_dataset_to_labelled(self.labelled._train_input)
        )

        if not self.val_split or not self.has_labelled_data:
            self.val_dataloader = None
        elif self.val_split < 0 or self.val_split > 1:
            raise MisconfigurationException("The `val_split` should a float between 0 and 1.")

        if self.labelled._test_input:
            self.test_dataloader = self._test_dataloader

        if hasattr(self.labelled, "on_after_batch_transfer"):
            self.on_after_batch_transfer = self.labelled.on_after_batch_transfer

        if not self.initial_num_labels:
            warnings.warn(
                "No labels provided for the initial step," "the estimated uncertainties are unreliable!", UserWarning
            )
        else:
            self._dataset.label_randomly(self.initial_num_labels)

    @property
    def has_test(self) -> bool:
        return bool(self.labelled._test_input)

    @property
    def has_labelled_data(self) -> bool:
        return self._dataset.n_labelled > 0

    @property
    def has_unlabelled_data(self) -> bool:
        return self._dataset.n_unlabelled > 0

    @property
    def num_classes(self) -> Optional[int]:
        return getattr(self.labelled, "num_classes", None) or getattr(self.unlabelled, "num_classes", None)

    @property
    def data_pipeline(self) -> "DataPipeline":
        return self.labelled.data_pipeline

    def train_dataloader(self) -> "DataLoader":
        if self.val_split:
            self.labelled._train_input = train_val_split(self._dataset, self.val_split)[0]
        else:
            self.labelled._train_input = self._dataset

        if self.has_labelled_data and self.val_split:
            self.val_dataloader = self._val_dataloader

        return self.labelled.train_dataloader()

    def _val_dataloader(self) -> "DataLoader":
        self.labelled._val_input = train_val_split(self._dataset, self.val_split)[1]
        self.labelled._val_dataloader_collate_fn = self.labelled._train_dataloader_collate_fn
        self.labelled._val_on_after_batch_transfer_fn = self.labelled._train_on_after_batch_transfer_fn
        return self.labelled._val_dataloader()

    def _test_dataloader(self) -> "DataLoader":
        return self.labelled.test_dataloader()

    def predict_dataloader(self) -> "DataLoader":
        self.labelled._predict_input = self.filter_unlabelled_data(self._dataset.pool)
        self.labelled._predict_dataloader_collate_fn = self.labelled._train_dataloader_collate_fn
        self.labelled._predict_on_after_batch_transfer_fn = self.labelled._train_on_after_batch_transfer_fn
        return self.labelled._predict_dataloader()

    def label(self, probabilities: List[torch.Tensor] = None, indices=None):
        if probabilities is not None and indices:
            raise MisconfigurationException(
                "The `probabilities` and `indices` are mutually exclusive, pass only of one them."
            )
        if probabilities is not None:
            probabilities = torch.cat([p[0].unsqueeze(0) for p in probabilities], dim=0)
            uncertainties = self.heuristic.get_uncertainties(probabilities)
            indices = np.argsort(uncertainties)
            if self._dataset is not None:
                self._dataset.label(indices[-self.query_size :])

    def state_dict(self) -> Dict[str, torch.Tensor]:
        return self._dataset.state_dict()

    def load_state_dict(self, state_dict) -> None:
        return self._dataset.load_state_dict(state_dict)
