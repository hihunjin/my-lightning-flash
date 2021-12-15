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
import functools
import os
import sys
from copy import copy, deepcopy
from dataclasses import dataclass
from functools import partial
from typing import Any, Callable, cast, Dict, Iterable, List, MutableMapping, Optional, Sequence, Tuple, Type, Union

from pytorch_lightning.utilities.enums import LightningEnum
from pytorch_lightning.utilities.exceptions import MisconfigurationException
from torch.utils.data import Dataset

import flash
from flash.core.data.callback import FlashCallback
from flash.core.data.properties import ProcessState, Properties
from flash.core.registry import FlashRegistry
from flash.core.utilities.stages import RunningStage
from flash.core.utilities.types import INPUT_TRANSFORM_TYPE

if sys.version_info < (3, 7):
    from typing import GenericMeta
else:
    GenericMeta = type


if not os.environ.get("READTHEDOCS", False):
    from torch.utils.data import IterableDataset
else:
    # ReadTheDocs mocks the `IterableDataset` import so it's type cannot be used as a base for a metaclass, so we
    # replace it here.
    IterableDataset = object


@dataclass(unsafe_hash=True, frozen=True)
class ImageLabelsMap(ProcessState):

    labels_map: Optional[Dict[int, Tuple[int, int, int]]]


class InputFormat(LightningEnum):
    """The ``InputFormat`` enum contains the data source names used by all of the default ``from_*`` methods in
    :class:`~flash.core.data.data_module.DataModule`."""

    FOLDERS = "folders"
    FILES = "files"
    NUMPY = "numpy"
    TENSORS = "tensors"
    CSV = "csv"
    JSON = "json"
    PARQUET = "parquet"
    DATASETS = "datasets"
    HUGGINGFACE_DATASET = "hf_datasets"
    FIFTYONE = "fiftyone"
    DATAFRAME = "data_frame"
    LISTS = "lists"
    LABELSTUDIO = "labelstudio"

    # TODO: Create a FlashEnum class???
    def __hash__(self) -> int:
        return hash(self.value)


class DataKeys(LightningEnum):
    """The ``DataKeys`` enum contains the keys that are used by built-in data sources to refer to inputs and
    targets."""

    INPUT = "input"
    PREDS = "preds"
    TARGET = "target"
    METADATA = "metadata"

    # TODO: Create a FlashEnum class???
    def __hash__(self) -> int:
        return hash(self.value)


class BaseDataFormat(LightningEnum):
    """The base class for creating ``data_format`` for :class:`~flash.core.data.io.input.Input`."""

    def __hash__(self) -> int:
        return hash(self.value)


def _has_len(data: Union[Sequence, Iterable]) -> bool:
    """Duck typing check to see if the argument supports getting the length.

    Args:
        data: The object to check for length support.
    """
    try:
        len(data)
        return True
    except (TypeError, NotImplementedError):
        return False


def _validate_input(input: "InputBase") -> None:
    """Helper function to validate that the type of an ``InputBase.data`` is appropriate for the type of
    ``InputBase`` being used.

    Args:
        input: The ``InputBase`` instance to validate.

    Raises:
        RuntimeError: If the ``input`` is of type ``Input`` and it's ``data`` attribute does not support ``len``.
        RuntimeError: If the ``input`` is of type ``IterableInput`` and it's ``data`` attribute does support ``len``.
    """
    if input.data is not None:
        if isinstance(input, Input) and not _has_len(input.data):
            raise RuntimeError("`Input.data` is not a sequence with a defined length. Use `IterableInput` instead.")
        elif isinstance(input, IterableInput) and _has_len(input.data):
            raise RuntimeError("`IterableInput.data` is a sequence with a defined length. Use `Input` instead.")


def _wrap_init(class_dict: Dict[str, Any]) -> None:
    """Helper function to wrap the ``__init__`` (if present) from a class construction dict to apply the
    ``_validate_input`` function after instantiation. Modifies the dict inplace.

    Args:
        class_dict: The class construction dict, optionally containing an init to wrap.
    """
    if "__init__" in class_dict:
        fn = class_dict["__init__"]

        @functools.wraps(fn)
        def wrapper(self, *args, **kwargs):
            fn(self, *args, **kwargs)
            _validate_input(self)

        class_dict["__init__"] = wrapper


class _InputMeta(GenericMeta):
    """Metaclass for the ``InputBase`` which wraps any init defined in a subclass with the ``_validate_input``
    helper."""

    def __new__(mcs, name: str, bases: Tuple, class_dict: Dict[str, Any]) -> "_InputMeta":
        _wrap_init(class_dict)
        return cast(_InputMeta, super().__new__(mcs, name, bases, class_dict))


class _IterableInputMeta(_InputMeta, type(IterableDataset)):
    """Metaclass for the ``IterableInput`` which extends ``_InputMeta`` and avoids metaclass conflict with
    ``IterableDataset``."""

    def __new__(mcs, name: str, bases: Tuple, class_dict: Dict[str, Any]) -> "_IterableInputMeta":
        return cast(_IterableInputMeta, super().__new__(mcs, name, bases, class_dict))


class InputBase(Properties, metaclass=_InputMeta):
    """``InputBase`` is the base class for the :class:`~flash.core.data.io.input.Input` and
    :class:`~flash.core.data.io.input.IterableInput` dataset implementations in Flash. These datasets are
    constructed via the ``load_data`` and ``load_sample`` hooks, which allow a single dataset object to include custom
    loading logic according to the running stage (e.g. train, validate, test, predict).

    Args:
        running_stage: The running stage for which the input will be used.
        *args: Any arguments that are to be passed to the ``load_data`` hook.
        **kwargs: Any additional keyword arguments to pass to the ``load_data`` hook.
    """

    input_transforms_registry = FlashRegistry("input_transforms")

    def __init__(
        self,
        running_stage: RunningStage,
        *args: Any,
        transform: INPUT_TRANSFORM_TYPE = None,
        transform_kwargs: Optional[Dict] = None,
        input_transforms_registry: Optional[FlashRegistry] = None,
        data_pipeline_state: Optional["flash.core.data.data_pipeline.DataPipelineState"] = None,
        **kwargs: Any,
    ) -> None:
        from flash.core.data.io.input_transform import create_transform

        self.transform = create_transform(
            transform,
            running_stage,
            data_pipeline_state,
            input_transforms_registry or self.input_transforms_registry,
            transform_kwargs,
        )
        super().__init__(running_stage=running_stage, data_pipeline_state=data_pipeline_state)

        self.data = None
        if len(args) >= 1 and args[0] is not None:
            self.data = self._call_load_data(*args, **kwargs)

    def _create_dataloader_collate_fn(self, callbacks: List[FlashCallback]) -> Optional[Callable]:
        from flash.core.data.io.input_transform import _create_collate_input_transform_processors

        if not self.transform:
            return
        return _create_collate_input_transform_processors(self.transform, callbacks)[0]

    def _create_on_after_batch_transfer_fn(self, callbacks: List[FlashCallback]) -> Optional[Callable]:
        from flash.core.data.io.input_transform import _create_collate_input_transform_processors

        if not self.transform:
            return
        return _create_collate_input_transform_processors(self.transform, callbacks)[1]

    def _call_load_data(self, *args: Any, **kwargs: Any) -> Union[Sequence, Iterable]:
        from flash.core.data.data_pipeline import DataPipeline

        load_data = getattr(
            self, DataPipeline._resolve_function_hierarchy("load_data", self, self.running_stage, InputBase)
        )
        return load_data(*args, **kwargs)

    def _call_load_sample(self, sample: Any) -> Any:
        from flash.core.data.data_pipeline import DataPipeline

        load_sample = getattr(
            self,
            DataPipeline._resolve_function_hierarchy(
                "load_sample",
                self,
                self.running_stage,
                InputBase,
            ),
        )
        return load_sample(copy(sample))

    @staticmethod
    def load_data(*args: Any, **kwargs: Any) -> Union[Sequence, Iterable]:
        """The ``load_data`` hook should return a collection of samples. To reduce the memory footprint, these
        samples should typically not have been loaded. For example, an input which loads images from disk would
        only return the list of filenames here rather than the loaded images.

        Args:
            *args: Any arguments that the input requires.
            **kwargs: Any additional keyword arguments that the input requires.
        """
        return args[0]

    @staticmethod
    def load_sample(sample: MutableMapping[str, Any]) -> Any:
        """The ``load_sample`` hook is called for each ``__getitem__`` or ``__next__`` call to the dataset with a
        single sample from the output of the ``load_data`` hook as input.

        Args:
            sample: A single sample from the output of the ``load_data`` hook.
        """
        return sample

    def __getstate__(self):
        """Temporarily override pickle behaviour.

        TODO: New DataPipeline should avoid this being pickled.
        """
        state = self.__dict__.copy()
        state.pop("data")
        if "data_iter" in state:
            state.pop("data_iter")
        return state

    def __setstate__(self, newstate):
        """Temporarily override pickle behaviour.

        TODO: New DataPipeline should avoid this being pickled.
        """
        newstate["data"] = None
        self.__dict__.update(newstate)

    def __copy__(self):
        """The default copy implementation seems to use ``__getstate__`` and ``__setstate__`` so we override it
        here with a custom implementation to ensure that it includes the data list."""
        cls = self.__class__
        result = cls.__new__(cls)
        result.__dict__.update(self.__dict__)
        return result

    def __deepcopy__(self, memo):
        """The default deepcopy implementation seems to use ``__getstate__`` and ``__setstate__`` so we override it
        here with a custom implementation to ensure that it includes the data list."""
        cls = self.__class__
        result = cls.__new__(cls)
        memo[id(self)] = result
        for k, v in self.__dict__.items():
            setattr(result, k, deepcopy(v, memo))
        return result

    def __bool__(self):
        """If ``self.data`` is ``None`` then the ``InputBase`` is considered falsey.

        This allows for quickly checking whether or not the ``InputBase`` is populated with data.
        """
        return self.data is not None

    @classmethod
    def register_input_transform(
        cls, enum: Union[LightningEnum, str], fn: Union[Type["flash.InputTransform"], partial]
    ) -> None:
        if cls.input_transforms_registry is None:
            raise MisconfigurationException(
                "The class attribute `input_transforms_registry` should be set as a class attribute. "
            )
        cls.input_transforms_registry(fn=fn, name=enum)


class Input(InputBase, Dataset):
    def __getitem__(self, index: int) -> Any:
        return self._call_load_sample(self.data[index])

    def __len__(self) -> int:
        return len(self.data) if self.data is not None else 0


class IterableInput(InputBase, IterableDataset, metaclass=_IterableInputMeta):
    def __iter__(self):
        self.data_iter = iter(self.data)
        return self

    def __next__(self) -> Any:
        return self._call_load_sample(next(self.data_iter))


class ServeInput(Input):
    def __init__(
        self,
        transform: INPUT_TRANSFORM_TYPE = None,
        transform_kwargs: Optional[Dict] = None,
        data_pipeline_state: Optional["flash.core.data.data_pipeline.DataPipelineState"] = None,
    ) -> None:
        if hasattr(self, "serve_load_data"):
            raise MisconfigurationException("`serve_load_data` shouldn't be implemented.")

        super().__init__(
            RunningStage.SERVING,
            transform=transform,
            transform_kwargs=transform_kwargs,
            data_pipeline_state=data_pipeline_state,
        )

    def serve_load_sample(self, sample: Any) -> List[Any]:
        raise NotImplementedError

    def __call__(self, sample: Any) -> Any:
        return self._call_load_sample(sample)

    def example_input(self) -> str:
        raise NotImplementedError

    def __bool__(self):
        return True
