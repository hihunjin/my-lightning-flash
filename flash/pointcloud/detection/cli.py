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
from flash.core.data.utils import download_data
from flash.core.utilities.flash_cli import FlashCLI
from flash.pointcloud import PointCloudObjectDetector, PointCloudObjectDetectorData

__all__ = ["pointcloud_detection"]


def from_kitti(
    batch_size: int = 4,
    **data_module_kwargs,
) -> PointCloudObjectDetectorData:
    """Downloads and loads the KITTI data set."""
    download_data("https://pl-flash-data.s3.amazonaws.com/KITTI_tiny.zip", "data/")
    return PointCloudObjectDetectorData.from_folders(
        train_folder="data/KITTI_Tiny/Kitti/train",
        val_folder="data/KITTI_Tiny/Kitti/val",
        batch_size=batch_size,
        **data_module_kwargs,
    )


def pointcloud_detection():
    """Detect objects in point clouds."""
    cli = FlashCLI(
        PointCloudObjectDetector,
        PointCloudObjectDetectorData,
        default_datamodule_builder=from_kitti,
        default_arguments={
            "trainer.max_epochs": 3,
        },
        finetune=False,
    )

    cli.trainer.save_checkpoint("pointcloud_detection_model.pt")


if __name__ == "__main__":
    pointcloud_detection()
