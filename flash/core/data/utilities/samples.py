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
from typing import Any, Dict, List, Optional, TypeVar

from flash.core.data.io.input import DataKeys

T = TypeVar("T")


def to_samples(inputs: List[Any], targets: Optional[List[Any]] = None) -> List[Dict[str, Any]]:
    """Package a list of inputs and, optionally, a list of targets in a list of dictionaries (samples).

    Args:
        inputs: The list of inputs to package as dictionaries.
        targets: Optionally provide a list of targets to also be included in the samples.

    Returns:
        A list of sample dictionaries.
    """
    if targets is None:
        return [{DataKeys.INPUT: input} for input in inputs]
    return [{DataKeys.INPUT: input, DataKeys.TARGET: target} for input, target in zip(inputs, targets)]
