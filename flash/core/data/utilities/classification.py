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
from enum import auto, Enum
from functools import reduce
from typing import Any, cast, List, Optional, Tuple, Union

import numpy as np
import torch

from flash.core.data.utilities.sort import sorted_alphanumeric


def _is_list_like(x: Any) -> bool:
    try:
        _ = x[0]
        _ = len(x)
        return True
    except (TypeError, IndexError):  # Single element tensors raise an `IndexError`
        return False


def _as_list(x: Union[List, torch.Tensor, np.ndarray]) -> List:
    if torch.is_tensor(x) or isinstance(x, np.ndarray):
        return cast(List, x.tolist())
    return x


def _strip(x: str) -> str:
    return x.strip(", ")


class TargetMode(Enum):
    """The ``TargetMode`` Enum describes the different supported formats for targets in Flash."""

    MULTI_TOKEN = auto()
    MULTI_NUMERIC = auto()
    MUTLI_COMMA_DELIMITED = auto()
    MUTLI_SPACE_DELIMITED = auto()
    MULTI_BINARY = auto()

    SINGLE_TOKEN = auto()
    SINGLE_NUMERIC = auto()
    SINGLE_BINARY = auto()

    @classmethod
    def from_target(cls, target: Any) -> "TargetMode":
        """Determine the ``TargetMode`` for a given target.

        Multi-label targets can be:
            * Comma delimited string - ``TargetMode.MUTLI_COMMA_DELIMITED`` (e.g. ["blue,green", "red"])
            * List of strings - ``TargetMode.MULTI_TOKEN`` (e.g. [["blue", "green"], ["red"]])
            * List of numbers - ``TargetMode.MULTI_NUMERIC`` (e.g. [[0, 1], [2]])
            * Binary list - ``TargetMode.MULTI_BINARY`` (e.g. [[1, 1, 0], [0, 0, 1]])

        Single-label targets can be:
            * Single string - ``TargetMode.SINGLE_TOKEN`` (e.g. ["blue", "green", "red"])
            * Single number - ``TargetMode.SINGLE_NUMERIC`` (e.g. [0, 1, 2])
            * One-hot binary list - ``TargetMode.SINGLE_BINARY`` (e.g. [[1, 0, 0], [0, 1, 0], [0, 0, 1]])

        Args:
            target: A target that is one of: a single target, a list of targets, a comma delimited string.
        """
        if isinstance(target, str):
            target = _strip(target)
            # TODO: This could be a dangerous assumption if people happen to have a label that contains a comma or space
            if "," in target:
                return TargetMode.MUTLI_COMMA_DELIMITED
            elif " " in target:
                return TargetMode.MUTLI_SPACE_DELIMITED
            else:
                return TargetMode.SINGLE_TOKEN
        elif _is_list_like(target):
            if isinstance(target[0], str):
                return TargetMode.MULTI_TOKEN
            elif len(target) > 1:
                if all(t == 0 or t == 1 for t in target):
                    if sum(target) == 1:
                        return TargetMode.SINGLE_BINARY
                    return TargetMode.MULTI_BINARY
                return TargetMode.MULTI_NUMERIC
        return TargetMode.SINGLE_NUMERIC

    @property
    def multi_label(self) -> bool:
        return any(
            [
                self is TargetMode.MUTLI_COMMA_DELIMITED,
                self is TargetMode.MUTLI_SPACE_DELIMITED,
                self is TargetMode.MULTI_NUMERIC,
                self is TargetMode.MULTI_TOKEN,
                self is TargetMode.MULTI_BINARY,
            ]
        )

    @property
    def numeric(self) -> bool:
        return any(
            [
                self is TargetMode.MULTI_NUMERIC,
                self is TargetMode.SINGLE_NUMERIC,
            ]
        )

    @property
    def binary(self) -> bool:
        return any(
            [
                self is TargetMode.MULTI_BINARY,
                self is TargetMode.SINGLE_BINARY,
            ]
        )


_RESOLUTION_MAPPING = {
    TargetMode.MULTI_BINARY: [TargetMode.MULTI_NUMERIC],
    TargetMode.SINGLE_BINARY: [TargetMode.MULTI_BINARY, TargetMode.MULTI_NUMERIC],
    TargetMode.SINGLE_TOKEN: [TargetMode.MUTLI_COMMA_DELIMITED, TargetMode.MUTLI_SPACE_DELIMITED],
    TargetMode.SINGLE_NUMERIC: [TargetMode.MULTI_NUMERIC],
}


def _resolve_target_mode(a: TargetMode, b: TargetMode) -> TargetMode:
    """The purpose of the addition here is to reduce the ``TargetMode`` over multiple targets. If one target mode
    is a comma delimited string and the other a single string then their sum will be comma delimited. If one target
    is multi binary and the other is single binary, their sum will be multi binary. Otherwise, we expect that both
    target modes are the same.

    Raises:
        ValueError: If the two  target modes could not be resolved to a single mode.
    """
    if a is b:
        return a
    elif a in _RESOLUTION_MAPPING and b in _RESOLUTION_MAPPING[a]:
        return b
    elif b in _RESOLUTION_MAPPING and a in _RESOLUTION_MAPPING[b]:
        return a
    raise ValueError(
        "Found inconsistent target modes. All targets should be either: single values, lists of values, or "
        "comma-delimited strings."
    )


def get_target_mode(targets: List[Any]) -> TargetMode:
    """Aggregate the ``TargetMode`` for a list of targets.

    Args:
        targets: The list of targets to get the label mode for.

    Returns:
        The total ``TargetMode`` of the list of targets.
    """
    targets = _as_list(targets)
    return reduce(_resolve_target_mode, [TargetMode.from_target(target) for target in targets])


class TargetFormatter:
    """A ``TargetFormatter`` is used to convert targets of a given type to a standard format required by the
    task."""

    def __call__(self, target: Any) -> Any:
        return self.format(target)

    def format(self, target: Any) -> Any:
        return _as_list(target)


class SingleNumericTargetFormatter(TargetFormatter):
    def format(self, target: Any) -> Any:
        result = super().format(target)
        if _is_list_like(result):
            result = result[0]
        return result


class SingleLabelTargetFormatter(TargetFormatter):
    def __init__(self, labels: List[Any]):
        self.label_to_idx = {label: idx for idx, label in enumerate(labels)}

    def format(self, target: Any) -> Any:
        return self.label_to_idx[_strip(target[0] if not isinstance(target, str) else target)]


class MultiLabelTargetFormatter(SingleLabelTargetFormatter):
    def __init__(self, labels: List[Any]):
        super().__init__(labels)

        self.num_classes = len(labels)

    def format(self, target: Any) -> Any:
        result = [0] * self.num_classes
        for t in target:
            idx = super().format(t)
            result[idx] = 1
        return result


class CommaDelimitedTargetFormatter(MultiLabelTargetFormatter):
    def format(self, target: Any) -> Any:
        return super().format(target.split(","))


class SpaceDelimitedTargetFormatter(MultiLabelTargetFormatter):
    def format(self, target: Any) -> Any:
        return super().format(target.split(" "))


class MultiNumericTargetFormatter(TargetFormatter):
    def __init__(self, num_classes: int):
        self.num_classes = num_classes

    def format(self, target: Any) -> Any:
        result = [0] * self.num_classes
        for idx in target:
            result[idx] = 1
        return result


class OneHotTargetFormatter(TargetFormatter):
    def format(self, target: Any) -> Any:
        for idx, t in enumerate(target):
            if t == 1:
                return idx
        return 0


def get_target_formatter(
    target_mode: TargetMode, labels: Optional[List[Any]], num_classes: Optional[int]
) -> TargetFormatter:
    """Get the ``TargetFormatter`` object to use for the given ``TargetMode``, ``labels``, and ``num_classes``.

    Args:
        target_mode: The target mode to format.
        labels: Labels used by the target (if available).
        num_classes: The number of classes in the targets.

    Returns:
        The target formatter to use when formatting targets.
    """
    if target_mode is TargetMode.MULTI_BINARY:
        return TargetFormatter()
    elif target_mode is TargetMode.SINGLE_NUMERIC:
        return SingleNumericTargetFormatter()
    elif target_mode is TargetMode.SINGLE_BINARY:
        return OneHotTargetFormatter()
    elif target_mode is TargetMode.MULTI_NUMERIC:
        return MultiNumericTargetFormatter(num_classes)
    elif target_mode is TargetMode.SINGLE_TOKEN:
        return SingleLabelTargetFormatter(labels)
    elif target_mode is TargetMode.MUTLI_COMMA_DELIMITED:
        return CommaDelimitedTargetFormatter(labels)
    elif target_mode is TargetMode.MUTLI_SPACE_DELIMITED:
        return SpaceDelimitedTargetFormatter(labels)
    return MultiLabelTargetFormatter(labels)


def get_target_details(targets: List[Any], target_mode: TargetMode) -> Tuple[Optional[List[Any]], int]:
    """Given a list of targets and their ``TargetMode``, this function determines the ``labels`` and
    ``num_classes``. Targets can be:

    * Token-based: ``labels`` is the unique tokens, ``num_classes`` is the number of unique tokens.
    * Numeric: ``labels`` is ``None`` and ``num_classes`` is the maximum value plus one.
    * Binary: ``labels`` is ``None`` and ``num_classes`` is the length of the binary target.

    Args:
        targets: A list of targets.
        target_mode: The ``TargetMode`` of the targets from ``get_target_mode``.

    Returns:
        (labels, num_classes): Tuple containing the inferred ``labels`` (or ``None`` if no labels could be inferred)
        and ``num_classes``.
    """
    targets = _as_list(targets)
    if target_mode.numeric:
        # Take a max over all values
        if target_mode is TargetMode.MULTI_NUMERIC:
            values = []
            for target in targets:
                values.extend(target)
        else:
            values = targets
        num_classes = _as_list(max(values))
        if _is_list_like(num_classes):
            num_classes = num_classes[0]
        num_classes = num_classes + 1
        labels = None
    elif target_mode.binary:
        # Take a length
        # TODO: Add a check here and error if target lengths are not all equal
        num_classes = len(targets[0])
        labels = None
    else:
        # Compute tokens
        tokens = []
        if target_mode is TargetMode.MUTLI_COMMA_DELIMITED:
            for target in targets:
                tokens.extend(target.split(","))
        elif target_mode is TargetMode.MUTLI_SPACE_DELIMITED:
            for target in targets:
                tokens.extend(target.split(" "))
        elif target_mode is TargetMode.MULTI_TOKEN:
            for target in targets:
                tokens.extend(target)
        else:
            tokens = targets

        tokens = [_strip(token) for token in tokens]
        labels = list(sorted_alphanumeric(set(tokens)))
        num_classes = len(labels)
    return labels, num_classes
