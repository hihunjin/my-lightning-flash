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
from typing import Any, Dict, List, Optional, Type, Union

import torch
from torch import nn
from torch.nn import functional as F
from torchmetrics import IoU

from flash.core.classification import ClassificationTask
from flash.core.data.io.input import DataKeys, ServeInput
from flash.core.data.io.output_transform import OutputTransform
from flash.core.registry import FlashRegistry
from flash.core.serve import Composition
from flash.core.utilities.imports import _KORNIA_AVAILABLE, requires
from flash.core.utilities.isinstance import _isinstance
from flash.core.utilities.types import (
    INPUT_TRANSFORM_TYPE,
    LOSS_FN_TYPE,
    LR_SCHEDULER_TYPE,
    METRICS_TYPE,
    OPTIMIZER_TYPE,
    OUTPUT_TRANSFORM_TYPE,
    OUTPUT_TYPE,
)
from flash.image.segmentation.backbones import SEMANTIC_SEGMENTATION_BACKBONES
from flash.image.segmentation.heads import SEMANTIC_SEGMENTATION_HEADS
from flash.image.segmentation.input import SemanticSegmentationDeserializer
from flash.image.segmentation.output import SegmentationLabelsOutput
from flash.image.segmentation.transforms import SemanticSegmentationInputTransform

if _KORNIA_AVAILABLE:
    import kornia as K


class SemanticSegmentationOutputTransform(OutputTransform):
    def per_sample_transform(self, sample: Any) -> Any:
        resize = K.geometry.Resize(sample[DataKeys.METADATA]["size"], interpolation="bilinear")
        sample[DataKeys.PREDS] = resize(sample[DataKeys.PREDS])
        sample[DataKeys.INPUT] = resize(sample[DataKeys.INPUT])
        return super().per_sample_transform(sample)


class SemanticSegmentation(ClassificationTask):
    """``SemanticSegmentation`` is a :class:`~flash.Task` for semantic segmentation of images. For more details, see
    :ref:`semantic_segmentation`.

    Args:
        num_classes: Number of classes to classify.
        backbone: A string or model to use to compute image features.
        backbone_kwargs: Additional arguments for the backbone configuration.
        head: A string or (model, num_features) tuple to use to compute image features.
        head_kwargs: Additional arguments for the head configuration.
        pretrained: Use a pretrained backbone.
        loss_fn: Loss function for training.
        optimizer: Optimizer to use for training.
        lr_scheduler: The LR scheduler to use during training.
        metrics: Metrics to compute for training and evaluation. Can either be an metric from the `torchmetrics`
            package, a custom metric inherenting from `torchmetrics.Metric`, a callable function or a list/dict
            containing a combination of the aforementioned. In all cases, each metric needs to have the signature
            `metric(preds,target)` and return a single scalar tensor. Defaults to :class:`torchmetrics.IOU`.
        learning_rate: Learning rate to use for training.
        multi_label: Whether the targets are multi-label or not.
        output: The :class:`~flash.core.data.io.output.Output` to use when formatting prediction outputs.
        output_transform: :class:`~flash.core.data.io.output_transform.OutputTransform` use for post processing samples.
    """

    output_transform_cls = SemanticSegmentationOutputTransform

    backbones: FlashRegistry = SEMANTIC_SEGMENTATION_BACKBONES

    heads: FlashRegistry = SEMANTIC_SEGMENTATION_HEADS

    required_extras: str = "image"

    def __init__(
        self,
        num_classes: int,
        backbone: Union[str, nn.Module] = "resnet50",
        backbone_kwargs: Optional[Dict] = None,
        head: str = "fpn",
        head_kwargs: Optional[Dict] = None,
        pretrained: Union[bool, str] = True,
        loss_fn: LOSS_FN_TYPE = None,
        optimizer: OPTIMIZER_TYPE = "Adam",
        lr_scheduler: LR_SCHEDULER_TYPE = None,
        metrics: METRICS_TYPE = None,
        learning_rate: float = 1e-3,
        multi_label: bool = False,
        output: OUTPUT_TYPE = None,
        output_transform: OUTPUT_TRANSFORM_TYPE = None,
    ) -> None:
        if metrics is None:
            metrics = IoU(num_classes=num_classes)

        if loss_fn is None:
            loss_fn = F.cross_entropy

        # TODO: need to check for multi_label
        if multi_label:
            raise NotImplementedError("Multi-label not supported yet.")

        super().__init__(
            model=None,
            loss_fn=loss_fn,
            optimizer=optimizer,
            lr_scheduler=lr_scheduler,
            metrics=metrics,
            learning_rate=learning_rate,
            output=output or SegmentationLabelsOutput(),
            output_transform=output_transform or self.output_transform_cls(),
        )

        self.save_hyperparameters()

        if not backbone_kwargs:
            backbone_kwargs = {}

        if not head_kwargs:
            head_kwargs = {}

        if isinstance(backbone, nn.Module):
            self.backbone = backbone
        else:
            self.backbone = self.backbones.get(backbone)(**backbone_kwargs)

        self.head: nn.Module = self.heads.get(head)(
            backbone=self.backbone, num_classes=num_classes, pretrained=pretrained, **head_kwargs
        )
        self.backbone = self.head.encoder

    def training_step(self, batch: Any, batch_idx: int) -> Any:
        batch = (batch[DataKeys.INPUT], batch[DataKeys.TARGET])
        return super().training_step(batch, batch_idx)

    def validation_step(self, batch: Any, batch_idx: int) -> Any:
        batch = (batch[DataKeys.INPUT], batch[DataKeys.TARGET])
        return super().validation_step(batch, batch_idx)

    def test_step(self, batch: Any, batch_idx: int) -> Any:
        batch = (batch[DataKeys.INPUT], batch[DataKeys.TARGET])
        return super().test_step(batch, batch_idx)

    def predict_step(self, batch: Any, batch_idx: int, dataloader_idx: int = 0) -> Any:
        batch_input = batch[DataKeys.INPUT]
        batch[DataKeys.PREDS] = super().predict_step(batch_input, batch_idx, dataloader_idx=dataloader_idx)
        return batch

    def forward(self, x) -> torch.Tensor:
        res = self.head(x)

        # some frameworks like torchvision return a dict.
        # In particular, torchvision segmentation models return the output logits
        # in the key `out`.
        if _isinstance(res, Dict[str, torch.Tensor]):
            res = res["out"]

        return res

    @classmethod
    def available_pretrained_weights(cls, backbone: str):
        result = cls.backbones.get(backbone, with_metadata=True)
        pretrained_weights = None

        if "weights_paths" in result["metadata"]:
            pretrained_weights = list(result["metadata"]["weights_paths"])

        return pretrained_weights

    @requires("serve")
    def serve(
        self,
        host: str = "127.0.0.1",
        port: int = 8000,
        sanity_check: bool = True,
        input_cls: Optional[Type[ServeInput]] = SemanticSegmentationDeserializer,
        transform: INPUT_TRANSFORM_TYPE = SemanticSegmentationInputTransform,
        transform_kwargs: Optional[Dict] = None,
    ) -> Composition:
        return super().serve(host, port, sanity_check, input_cls, transform, transform_kwargs)

    @staticmethod
    def _ci_benchmark_fn(history: List[Dict[str, Any]]):
        """This function is used only for debugging usage with CI."""
        assert history[-1]["val_iou"] > 0.2
