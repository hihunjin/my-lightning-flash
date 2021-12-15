from typing import Any, List

import numpy as np
from pytorch_lightning.utilities.exceptions import MisconfigurationException
from torch.utils.data import Dataset

import flash
from flash.core.data.properties import Properties


class SplitDataset(Properties, Dataset):
    """SplitDataset is used to create Dataset Subset using indices.

    Args:

        dataset: A dataset to be splitted
        indices: List of indices to expose from the dataset
        use_duplicated_indices: Whether to allow duplicated indices.

    Example::

        split_ds = SplitDataset(dataset, indices=[10, 14, 25])

        split_ds = SplitDataset(dataset, indices=[10, 10, 10, 14, 25], use_duplicated_indices=True)
    """

    def __init__(self, dataset: Any, indices: List[int] = None, use_duplicated_indices: bool = False) -> None:
        kwargs = {}
        if isinstance(dataset, Properties):
            kwargs = dict(
                running_stage=dataset._running_stage,
                data_pipeline_state=dataset._data_pipeline_state,
                state=dataset._state,
            )
        super().__init__(**kwargs)

        if indices is None:
            indices = []
        if not isinstance(indices, list):
            raise MisconfigurationException("indices should be a list")

        if use_duplicated_indices:
            indices = list(indices)
        else:
            indices = list(np.unique(indices))

        if np.max(indices) >= len(dataset) or np.min(indices) < 0:
            raise MisconfigurationException(f"`indices` should be within [0, {len(dataset) -1}].")

        self.dataset = dataset
        self.indices = indices

    def attach_data_pipeline_state(self, data_pipeline_state: "flash.core.data.data_pipeline.DataPipelineState"):
        super().attach_data_pipeline_state(data_pipeline_state)
        if isinstance(self.dataset, Properties):
            self.dataset.attach_data_pipeline_state(data_pipeline_state)

    def __getattr__(self, key: str):
        if key != "dataset":
            return getattr(self.dataset, key)
        raise AttributeError

    def __getitem__(self, index: int) -> Any:
        return self.dataset[self.indices[index]]

    def __len__(self) -> int:
        return len(self.indices)
