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
from typing import Any, Dict, List, Optional

from pytorch_lightning.utilities import rank_zero_info

from flash.core.adapter import AdapterTask
from flash.core.data.data_pipeline import DataPipeline
from flash.core.data.output import PredsOutput
from flash.core.registry import FlashRegistry
from flash.core.utilities.types import LR_SCHEDULER_TYPE, OPTIMIZER_TYPE, OUTPUT_TRANSFORM_TYPE, OUTPUT_TYPE
from flash.image.instance_segmentation.backbones import INSTANCE_SEGMENTATION_HEADS
from flash.image.instance_segmentation.data import InstanceSegmentationOutputTransform


class InstanceSegmentation(AdapterTask):
    """The ``InstanceSegmentation`` is a :class:`~flash.Task` for detecting objects in images. For more details, see
    :ref:`object_detection`.

    Args:
        num_classes: The number of object classes.
        backbone: String indicating the backbone CNN architecture to use.
        head: String indicating the head module to use on top of the backbone.
        pretrained: Whether the model should be loaded with it's pretrained weights.
        optimizer: Optimizer to use for training.
        lr_scheduler: The LR scheduler to use during training.
        learning_rate: The learning rate to use for training.
        output: The :class:`~flash.core.data.io.output.Output` to use when formatting prediction outputs.
        predict_kwargs: dictionary containing parameters that will be used during the prediction phase.
        **kwargs: additional kwargs used for initializing the task
    """

    heads: FlashRegistry = INSTANCE_SEGMENTATION_HEADS

    required_extras: List[str] = ["image", "icevision"]

    def __init__(
        self,
        num_classes: int,
        backbone: Optional[str] = "resnet18_fpn",
        head: Optional[str] = "mask_rcnn",
        pretrained: bool = True,
        optimizer: OPTIMIZER_TYPE = "Adam",
        lr_scheduler: LR_SCHEDULER_TYPE = None,
        learning_rate: float = 5e-4,
        output_transform: OUTPUT_TRANSFORM_TYPE = InstanceSegmentationOutputTransform(),
        output: OUTPUT_TYPE = PredsOutput(),
        predict_kwargs: Dict = None,
        **kwargs: Any,
    ):
        self.save_hyperparameters()

        predict_kwargs = predict_kwargs if predict_kwargs else {}
        metadata = self.heads.get(head, with_metadata=True)
        adapter = metadata["metadata"]["adapter"].from_task(
            self,
            num_classes=num_classes,
            backbone=backbone,
            head=head,
            pretrained=pretrained,
            predict_kwargs=predict_kwargs,
            **kwargs,
        )

        super().__init__(
            adapter,
            learning_rate=learning_rate,
            optimizer=optimizer,
            lr_scheduler=lr_scheduler,
            output_transform=output_transform,
            output=output,
        )

    def _ci_benchmark_fn(self, history: List[Dict[str, Any]]) -> None:
        """This function is used only for debugging usage with CI."""
        # todo

    def on_load_checkpoint(self, checkpoint: Dict[str, Any]) -> None:
        super().on_load_checkpoint(checkpoint)
        # todo: currently the data pipeline for icevision is not serializable, so we re-create the pipeline.
        if "data_pipeline" not in checkpoint:
            rank_zero_info(
                "Assigned Segmentation Data Pipeline for data processing. This is because a data-pipeline stored in "
                "the model due to pickling issues. "
                "If you'd like to change this, extend the InstanceSegmentation Task and override `on_load_checkpoint`."
            )
            self.data_pipeline = DataPipeline(
                input_transform=None,
                output_transform=InstanceSegmentationOutputTransform(),
            )

    @property
    def predict_kwargs(self) -> Dict[str, Any]:
        """The kwargs used for the prediction step."""
        return self.adapter.predict_kwargs

    @predict_kwargs.setter
    def predict_kwargs(self, predict_kwargs: Dict[str, Any]):
        self.adapter.predict_kwargs = predict_kwargs
