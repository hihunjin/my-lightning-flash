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

from torchmetrics import BLEUScore

from flash.core.utilities.types import LOSS_FN_TYPE, LR_SCHEDULER_TYPE, METRICS_TYPE, OPTIMIZER_TYPE
from flash.text.seq2seq.core.model import Seq2SeqTask


class TranslationTask(Seq2SeqTask):
    """The ``TranslationTask`` is a :class:`~flash.Task` for Seq2Seq text translation. For more details, see
    :ref:`translation`.

    You can change the backbone to any translation model from `HuggingFace/transformers
    <https://huggingface.co/models?filter=pytorch&pipeline_tag=translation>`__ using the ``backbone`` argument.

    .. note:: When changing the backbone, make sure you pass in the same backbone to the :class:`~flash.Task` and the
        :class:`~flash.core.data.data_module.DataModule` object! Since this is a Seq2Seq task, make sure you use a
        Seq2Seq model.

    Args:
        backbone: backbone model to use for the task.
        loss_fn: Loss function for training.
        optimizer: Optimizer to use for training.
        lr_scheduler: The LR scheduler to use during training.
        metrics: Metrics to compute for training and evaluation. Defauls to calculating the BLEU metric.
            Changing this argument currently has no effect.
        learning_rate: Learning rate to use for training, defaults to `1e-5`
        val_target_max_length: Maximum length of targets in validation. Defaults to `128`
        num_beams: Number of beams to use in validation when generating predictions. Defaults to `4`
        n_gram: Maximum n_grams to use in metric calculation. Defaults to `4`
        smooth: Apply smoothing in BLEU calculation. Defaults to `True`
        enable_ort: Enable Torch ONNX Runtime Optimization: https://onnxruntime.ai/docs/#onnx-runtime-for-training
    """

    def __init__(
        self,
        backbone: str = "t5-small",
        tokenizer_kwargs: Optional[Dict[str, Any]] = None,
        loss_fn: LOSS_FN_TYPE = None,
        optimizer: OPTIMIZER_TYPE = "Adam",
        lr_scheduler: LR_SCHEDULER_TYPE = None,
        metrics: METRICS_TYPE = None,
        learning_rate: float = 1e-5,
        val_target_max_length: Optional[int] = 128,
        num_beams: Optional[int] = 4,
        n_gram: bool = 4,
        smooth: bool = True,
        enable_ort: bool = False,
    ):
        self.save_hyperparameters()
        super().__init__(
            backbone=backbone,
            tokenizer_kwargs=tokenizer_kwargs,
            loss_fn=loss_fn,
            optimizer=optimizer,
            lr_scheduler=lr_scheduler,
            metrics=metrics,
            learning_rate=learning_rate,
            val_target_max_length=val_target_max_length,
            num_beams=num_beams,
            enable_ort=enable_ort,
        )
        self.bleu = BLEUScore(
            n_gram=n_gram,
            smooth=smooth,
        )

    @property
    def task(self) -> str:
        return "translation"

    def compute_metrics(self, generated_tokens, batch, prefix):
        reference_corpus = self.tokenize_labels(batch["labels"])
        # wrap targets in list as score expects a list of potential references
        reference_corpus = [[reference] for reference in reference_corpus]

        translate_corpus = self._output_transform.uncollate(generated_tokens)
        translate_corpus = [line for line in translate_corpus]

        result = self.bleu(reference_corpus, translate_corpus)
        self.log(f"{prefix}_bleu_score", result, on_step=False, on_epoch=True, prog_bar=True)

    @staticmethod
    def _ci_benchmark_fn(history: List[Dict[str, Any]]):
        """This function is used only for debugging usage with CI."""
        assert history[-1]["val_bleu_score"] > 0.6, history[-1]["val_bleu_score"]
