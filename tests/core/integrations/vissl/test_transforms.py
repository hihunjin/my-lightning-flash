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
import pytest

from flash.core.data.io.input import DataKeys
from flash.core.utilities.imports import _TORCHVISION_AVAILABLE, _VISSL_AVAILABLE
from tests.image.embedding.utils import ssl_datamodule


@pytest.mark.skipif(not (_TORCHVISION_AVAILABLE and _VISSL_AVAILABLE), reason="vissl not installed.")
def test_multicrop_input_transform():
    batch_size = 8
    total_num_crops = 6
    num_crops = [2, 4]
    size_crops = [160, 96]
    crop_scales = [[0.4, 1], [0.05, 0.4]]

    datamodule = ssl_datamodule(
        batch_size=batch_size,
        total_num_crops=total_num_crops,
        num_crops=num_crops,
        size_crops=size_crops,
        crop_scales=crop_scales,
    )
    batch = next(iter(datamodule.train_dataloader()))

    assert len(batch[DataKeys.INPUT]) == total_num_crops
    assert batch[DataKeys.INPUT][0].shape == (batch_size, 3, size_crops[0], size_crops[0])
    assert batch[DataKeys.INPUT][-1].shape == (batch_size, 3, size_crops[-1], size_crops[-1])
    assert list(batch[DataKeys.TARGET].shape) == [batch_size]
