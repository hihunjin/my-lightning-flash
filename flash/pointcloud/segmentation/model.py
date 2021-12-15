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
from typing import Any, Callable, Dict, Iterable, Optional, Tuple, Union

import torch
from torch import nn
from torch.nn import functional as F
from torch.utils.data import DataLoader, Sampler
from torchmetrics import IoU

from flash.core.classification import ClassificationTask
from flash.core.data.io.input import DataKeys, Input
from flash.core.data.io.output import Output
from flash.core.data.states import CollateFn
from flash.core.registry import FlashRegistry
from flash.core.utilities.imports import _POINTCLOUD_AVAILABLE
from flash.core.utilities.types import LOSS_FN_TYPE, LR_SCHEDULER_TYPE, METRICS_TYPE, OPTIMIZER_TYPE, OUTPUT_TYPE
from flash.pointcloud.segmentation.backbones import POINTCLOUD_SEGMENTATION_BACKBONES

if _POINTCLOUD_AVAILABLE:
    from open3d._ml3d.torch.modules.losses.semseg_loss import filter_valid_label
    from open3d.ml.torch.dataloaders import TorchDataloader


class PointCloudSegmentationOutput(Output):
    pass


class PointCloudSegmentation(ClassificationTask):
    """The ``PointCloudClassifier`` is a :class:`~flash.core.classification.ClassificationTask` that classifies
    pointcloud data.

    Args:
        num_classes: The number of classes (outputs) for this :class:`~flash.core.model.Task`.
        backbone: The backbone name (or a tuple of ``nn.Module``, output size) to use.
        backbone_kwargs: Any additional kwargs to pass to the backbone constructor.
        head: a `nn.Module` to use on top of the backbone. The output dimension should match the `num_classes`
            argument. If not set will default to a single linear layer.
        loss_fn: The loss function to use. If ``None``, a default will be selected by the
            :class:`~flash.core.classification.ClassificationTask` depending on the ``multi_label`` argument.
        optimizer: Optimizer to use for training.
        lr_scheduler: The LR scheduler to use during training.
        metrics: Any metrics to use with this :class:`~flash.core.model.Task`. If ``None``, a default will be selected
            by the :class:`~flash.core.classification.ClassificationTask` depending on the ``multi_label`` argument.
        learning_rate: The learning rate for the optimizer.
        multi_label: If ``True``, this will be treated as a multi-label classification problem.
        output: The :class:`~flash.core.data.io.output.Output` to use when formatting prediction outputs.
    """

    backbones: FlashRegistry = POINTCLOUD_SEGMENTATION_BACKBONES

    required_extras: str = "pointcloud"

    def __init__(
        self,
        num_classes: int,
        backbone: Union[str, Tuple[nn.Module, int]] = "RandLANet",
        backbone_kwargs: Optional[Dict] = None,
        head: Optional[nn.Module] = None,
        loss_fn: LOSS_FN_TYPE = torch.nn.functional.cross_entropy,
        optimizer: OPTIMIZER_TYPE = "Adam",
        lr_scheduler: LR_SCHEDULER_TYPE = None,
        metrics: METRICS_TYPE = None,
        learning_rate: float = 1e-2,
        multi_label: bool = False,
        output: OUTPUT_TYPE = PointCloudSegmentationOutput(),
    ):
        import flash

        if metrics is None:
            metrics = IoU(num_classes=num_classes)

        super().__init__(
            model=None,
            loss_fn=loss_fn,
            optimizer=optimizer,
            lr_scheduler=lr_scheduler,
            metrics=metrics,
            learning_rate=learning_rate,
            multi_label=multi_label,
            output=output,
        )

        self.save_hyperparameters()

        if not backbone_kwargs:
            backbone_kwargs = {"num_classes": num_classes}

        if isinstance(backbone, tuple):
            self.backbone, out_features = backbone
        else:
            self.backbone, out_features, collate_fn = self.backbones.get(backbone)(**backbone_kwargs)
            # replace latest layer
            if not flash._IS_TESTING:
                self.backbone.fc = nn.Identity()
            self.set_state(CollateFn(collate_fn))

        self.head = nn.Identity() if flash._IS_TESTING else (head or nn.Linear(out_features, num_classes))

    def apply_filtering(self, labels, scores):
        scores, labels = filter_valid_label(scores, labels, self.hparams.num_classes, [0], self.device)
        return labels, scores

    def to_metrics_format(self, x: torch.Tensor) -> torch.Tensor:
        return F.softmax(self.to_loss_format(x), dim=-1)

    def to_loss_format(self, x: torch.Tensor) -> torch.Tensor:
        return x.reshape(-1, x.shape[-1])

    def training_step(self, batch: Any, batch_idx: int) -> Any:
        batch = (batch[DataKeys.INPUT], batch[DataKeys.INPUT]["labels"].view(-1))
        return super().training_step(batch, batch_idx)

    def validation_step(self, batch: Any, batch_idx: int) -> Any:
        batch = (batch[DataKeys.INPUT], batch[DataKeys.INPUT]["labels"].view(-1))
        return super().validation_step(batch, batch_idx)

    def test_step(self, batch: Any, batch_idx: int) -> Any:
        batch = (batch[DataKeys.INPUT], batch[DataKeys.INPUT]["labels"].view(-1))
        return super().test_step(batch, batch_idx)

    def predict_step(self, batch: Any, batch_idx: int, dataloader_idx: int = 0) -> Any:
        batch[DataKeys.PREDS] = self(batch[DataKeys.INPUT])
        batch[DataKeys.TARGET] = batch[DataKeys.INPUT]["labels"]
        # drop sub-sampled pointclouds
        batch[DataKeys.INPUT] = batch[DataKeys.INPUT]["xyz"][0]
        return batch

    def forward(self, x) -> torch.Tensor:
        """First call the backbone, then the model head."""
        # hack to enable backbone to work properly.
        self.backbone.device = self.device
        x = self.backbone(x)
        if self.head is not None:
            x = self.head(x)
        return x

    def _process_dataset(
        self,
        dataset: Input,
        batch_size: int,
        num_workers: int,
        pin_memory: bool,
        collate_fn: Callable,
        shuffle: bool = False,
        drop_last: bool = True,
        sampler: Optional[Sampler] = None,
        **kwargs
    ) -> DataLoader:
        if not isinstance(dataset.data, TorchDataloader):

            dataset.dataset = TorchDataloader(
                dataset.dataset,
                preprocess=self.backbone.preprocess,
                transform=self.backbone.transform,
                use_cache=False,
            )

        return DataLoader(
            dataset,
            batch_size=batch_size,
            num_workers=num_workers,
            pin_memory=pin_memory,
            collate_fn=collate_fn,
            shuffle=shuffle,
            drop_last=drop_last,
            sampler=sampler,
        )

    def modules_to_freeze(self) -> Union[nn.Module, Iterable[Union[nn.Module, Iterable]]]:
        """Return the module attributes of the model to be frozen."""
        return list(self.backbone.children())
