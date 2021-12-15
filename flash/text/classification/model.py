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
import warnings
from typing import Any, Dict, List, Optional, Type

import torch
from pytorch_lightning import Callback

from flash.core.classification import ClassificationTask, LabelsOutput
from flash.core.data.io.input import DataKeys, ServeInput
from flash.core.integrations.transformers.input_transform import TransformersInputTransform
from flash.core.integrations.transformers.states import TransformersBackboneState
from flash.core.registry import FlashRegistry
from flash.core.serve import Composition
from flash.core.utilities.imports import _TRANSFORMERS_AVAILABLE, requires
from flash.core.utilities.types import (
    INPUT_TRANSFORM_TYPE,
    LOSS_FN_TYPE,
    LR_SCHEDULER_TYPE,
    METRICS_TYPE,
    OPTIMIZER_TYPE,
    OUTPUT_TYPE,
)
from flash.text.classification.backbones import TEXT_CLASSIFIER_BACKBONES
from flash.text.input import TextDeserializer
from flash.text.ort_callback import ORTCallback

if _TRANSFORMERS_AVAILABLE:
    from transformers.modeling_outputs import Seq2SeqSequenceClassifierOutput, SequenceClassifierOutput


class TextClassifier(ClassificationTask):
    """The ``TextClassifier`` is a :class:`~flash.Task` for classifying text. For more details, see
    :ref:`text_classification`. The ``TextClassifier`` also supports multi-label classification with
    ``multi_label=True``. For more details, see :ref:`text_classification_multi_label`.

    Args:
        num_classes: Number of classes to classify.
        backbone: A model to use to compute text features can be any BERT model from HuggingFace/transformersimage .
        optimizer: Optimizer to use for training.
        lr_scheduler: The LR scheduler to use during training.
        metrics: Metrics to compute for training and evaluation. Can either be an metric from the `torchmetrics`
            package, a custom metric inherenting from `torchmetrics.Metric`, a callable function or a list/dict
            containing a combination of the aforementioned. In all cases, each metric needs to have the signature
            `metric(preds,target)` and return a single scalar tensor. Defaults to :class:`torchmetrics.Accuracy`.
        learning_rate: Learning rate to use for training, defaults to `1e-3`
        multi_label: Whether the targets are multi-label or not.
        output: The :class:`~flash.core.data.io.output.Output` to use when formatting prediction outputs.
        enable_ort: Enable Torch ONNX Runtime Optimization: https://onnxruntime.ai/docs/#onnx-runtime-for-training
    """

    required_extras: str = "text"

    backbones: FlashRegistry = TEXT_CLASSIFIER_BACKBONES

    def __init__(
        self,
        num_classes: int,
        backbone: str = "prajjwal1/bert-medium",
        loss_fn: LOSS_FN_TYPE = None,
        optimizer: OPTIMIZER_TYPE = "Adam",
        lr_scheduler: LR_SCHEDULER_TYPE = None,
        metrics: METRICS_TYPE = None,
        learning_rate: float = 1e-2,
        multi_label: bool = False,
        output: OUTPUT_TYPE = None,
        enable_ort: bool = False,
    ):
        self.save_hyperparameters()

        os.environ["TOKENIZERS_PARALLELISM"] = "TRUE"
        # disable HF thousand warnings
        warnings.simplefilter("ignore")
        # set os environ variable for multiprocesses
        os.environ["PYTHONWARNINGS"] = "ignore"

        super().__init__(
            num_classes=num_classes,
            model=None,
            loss_fn=loss_fn,
            optimizer=optimizer,
            lr_scheduler=lr_scheduler,
            metrics=metrics,
            learning_rate=learning_rate,
            multi_label=multi_label,
            output=output or LabelsOutput(multi_label=multi_label),
        )
        self.enable_ort = enable_ort
        self.set_state(TransformersBackboneState(backbone))
        self.model = self.backbones.get(backbone)(num_labels=num_classes)
        self.save_hyperparameters()

    @property
    def backbone(self):
        return self.model.base_model

    def forward(self, batch: Dict[str, torch.Tensor]):
        result = self.model(input_ids=batch.get("input_ids", None), attention_mask=batch.get("attention_mask", None))
        if isinstance(result, (SequenceClassifierOutput, Seq2SeqSequenceClassifierOutput)):
            result = result.logits
        return result

    def step(self, batch, batch_idx, metrics) -> dict:
        target = batch.pop(DataKeys.TARGET)
        batch = (batch, target)
        return super().step(batch, batch_idx, metrics)

    def predict_step(self, batch: Any, batch_idx: int, dataloader_idx: int = 0) -> Any:
        return self(batch)

    def _ci_benchmark_fn(self, history: List[Dict[str, Any]]):
        """This function is used only for debugging usage with CI."""
        if self.hparams.multi_label:
            assert history[-1]["val_f1"] > 0.40, history[-1]["val_f1"]
        else:
            assert history[-1]["val_accuracy"] > 0.70, history[-1]["val_accuracy"]

    def configure_callbacks(self) -> List[Callback]:
        callbacks = super().configure_callbacks() or []
        if self.enable_ort:
            callbacks.append(ORTCallback())
        return callbacks

    @requires("serve")
    def serve(
        self,
        host: str = "127.0.0.1",
        port: int = 8000,
        sanity_check: bool = True,
        input_cls: Optional[Type[ServeInput]] = TextDeserializer,
        transform: INPUT_TRANSFORM_TYPE = TransformersInputTransform,
        transform_kwargs: Optional[Dict] = None,
    ) -> Composition:
        return super().serve(host, port, sanity_check, input_cls, transform, transform_kwargs)
