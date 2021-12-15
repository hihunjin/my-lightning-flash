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
from functools import partial
from pathlib import Path

import flash
from flash.core.utilities.imports import _ICEDATA_AVAILABLE, _ICEVISION_AVAILABLE, _IMAGE_AVAILABLE
from flash.image import InstanceSegmentation, InstanceSegmentationData

if _ICEDATA_AVAILABLE:
    import icedata
if _ICEVISION_AVAILABLE:
    import icevision

from unittest import mock

import pytest

from flash.__main__ import main


@pytest.mark.skipif(not _IMAGE_AVAILABLE, reason="image libraries aren't installed.")
@pytest.mark.skipif(not _ICEVISION_AVAILABLE, reason="IceVision is not installed for testing")
def test_cli():
    cli_args = ["flash", "instance_segmentation", "--trainer.fast_dev_run", "True"]
    with mock.patch("sys.argv", cli_args):
        try:
            main()
        except SystemExit:
            pass


# todo: this test takes around 25s because of the icedata download, can we speed it up?
@pytest.mark.skipif(not _IMAGE_AVAILABLE, reason="image libraries aren't installed.")
@pytest.mark.skipif(not _ICEVISION_AVAILABLE, reason="IceVision is not installed for testing")
def test_instance_segmentation_inference(tmpdir):
    """Test to ensure that inference runs with instance segmentation from input paths."""
    # modify the root path to use 'data' where our CI caches datasets
    icevision.utils.data_dir.data_dir = Path("data/icevision/")
    icevision.utils.data_dir.data_dir.mkdir(exist_ok=True, parents=True)
    data_dir = icedata.pets.load_data()

    datamodule = InstanceSegmentationData.from_icedata(
        train_folder=data_dir,
        val_split=0.1,
        parser=partial(icedata.pets.parser, mask=True),
        batch_size=1,
    )

    model = InstanceSegmentation(
        head="mask_rcnn",
        backbone="resnet18_fpn",
        num_classes=datamodule.num_classes,
        output=None,
    )

    # 3. Create the trainer and finetune the model
    trainer = flash.Trainer(max_epochs=1, fast_dev_run=True)
    trainer.finetune(model, datamodule=datamodule, strategy="freeze")

    datamodule = InstanceSegmentationData.from_files(
        predict_files=[
            str(data_dir / "images/yorkshire_terrier_9.jpg"),
            str(data_dir / "images/yorkshire_terrier_12.jpg"),
            str(data_dir / "images/yorkshire_terrier_13.jpg"),
        ],
        batch_size=2,
    )
    predictions = trainer.predict(model, datamodule=datamodule)
    assert len(predictions[0][0]) == 6

    model_path = os.path.join(tmpdir, "model.pt")
    trainer.save_checkpoint(model_path)
    InstanceSegmentation.load_from_checkpoint(model_path)

    datamodule = InstanceSegmentationData.from_files(
        predict_files=[
            str(data_dir / "images/yorkshire_terrier_9.jpg"),
            str(data_dir / "images/yorkshire_terrier_12.jpg"),
            str(data_dir / "images/yorkshire_terrier_13.jpg"),
        ],
        batch_size=2,
    )
    predictions = trainer.predict(model, datamodule=datamodule)
    assert len(predictions[0][0]) == 6
