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
from pathlib import Path

import numpy as np
import pytest
import torch

from flash import Trainer
from flash.core.utilities.imports import _FIFTYONE_AVAILABLE, _IMAGE_AVAILABLE, _PIL_AVAILABLE
from flash.image import ImageClassificationData, ImageClassifier
from tests.helpers.utils import _IMAGE_TESTING

if _PIL_AVAILABLE:
    from PIL import Image

if _FIFTYONE_AVAILABLE:
    import fiftyone as fo


def _dummy_image_loader(_):
    return torch.rand(3, 224, 224)


def _rand_image():
    return Image.fromarray(np.random.randint(0, 255, (64, 64, 3), dtype="uint8"))


@pytest.mark.skipif(not _IMAGE_TESTING, reason="image libraries aren't installed.")
def test_classification(tmpdir):
    tmpdir = Path(tmpdir)

    (tmpdir / "a").mkdir()
    (tmpdir / "b").mkdir()

    image_a = str(tmpdir / "a" / "a_1.png")
    image_b = str(tmpdir / "b" / "b_1.png")

    _rand_image().save(image_a)
    _rand_image().save(image_b)

    data = ImageClassificationData.from_files(
        train_files=[image_a, image_b],
        train_targets=[0, 1],
        num_workers=0,
        batch_size=2,
        transform_kwargs={"image_size": (64, 64)},
    )
    model = ImageClassifier(num_classes=2, backbone="resnet18")
    trainer = Trainer(default_root_dir=tmpdir, fast_dev_run=True)
    trainer.finetune(model, datamodule=data, strategy="freeze")


@pytest.mark.skipif(not _IMAGE_AVAILABLE, reason="image libraries aren't installed.")
@pytest.mark.skipif(not _FIFTYONE_AVAILABLE, reason="fiftyone isn't installed.")
def test_classification_fiftyone(tmpdir):
    tmpdir = Path(tmpdir)

    (tmpdir / "a").mkdir()
    (tmpdir / "b").mkdir()
    _rand_image().save(tmpdir / "a_1.png")
    _rand_image().save(tmpdir / "b_1.png")

    train_images = [
        str(tmpdir / "a_1.png"),
        str(tmpdir / "b_1.png"),
    ]

    train_dataset = fo.Dataset.from_dir(str(tmpdir), dataset_type=fo.types.ImageDirectory)
    s1 = train_dataset[train_images[0]]
    s2 = train_dataset[train_images[1]]
    s1["test"] = fo.Classification(label="1")
    s2["test"] = fo.Classification(label="2")
    s1.save()
    s2.save()

    data = ImageClassificationData.from_fiftyone(
        train_dataset=train_dataset,
        label_field="test",
        batch_size=2,
        num_workers=0,
        transform_kwargs={"image_size": (64, 64)},
    )

    model = ImageClassifier(num_classes=2, backbone="resnet18")
    trainer = Trainer(default_root_dir=tmpdir, fast_dev_run=True)
    trainer.finetune(model, datamodule=data, strategy="freeze")
