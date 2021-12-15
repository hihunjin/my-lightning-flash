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
from flash.core.registry import FlashRegistry
from flash.core.utilities.imports import _VISSL_AVAILABLE
from flash.core.utilities.providers import _VISSL
from flash.image.embedding.heads import IMAGE_EMBEDDER_HEADS
from flash.image.embedding.losses import IMAGE_EMBEDDER_LOSS_FUNCTIONS
from flash.image.embedding.vissl.adapter import VISSLAdapter
from flash.image.embedding.vissl.hooks import SimCLRTrainingSetupHook, TrainingSetupHook

if _VISSL_AVAILABLE:
    from vissl.hooks.dino_hooks import DINOHook
    from vissl.hooks.moco_hooks import MoCoHook
    from vissl.hooks.swav_hooks import NormalizePrototypesHook, SwAVUpdateQueueScoresHook


def dino(head: str = "dino_head", **kwargs):
    loss_fn = IMAGE_EMBEDDER_LOSS_FUNCTIONS.get("dino_loss")(**kwargs)
    head = IMAGE_EMBEDDER_HEADS.get(head)(**kwargs)

    return loss_fn, head, [DINOHook(), TrainingSetupHook()]


def swav(head: str = "swav_head", **kwargs):
    loss_fn = IMAGE_EMBEDDER_LOSS_FUNCTIONS.get("swav_loss")(**kwargs)
    head = IMAGE_EMBEDDER_HEADS.get(head)(**kwargs)

    return loss_fn, head, [SwAVUpdateQueueScoresHook(), NormalizePrototypesHook(), TrainingSetupHook()]


def simclr(head: str = "simclr_head", **kwargs):
    loss_fn = IMAGE_EMBEDDER_LOSS_FUNCTIONS.get("simclr_loss")(**kwargs)
    head = IMAGE_EMBEDDER_HEADS.get(head)(**kwargs)

    return loss_fn, head, [SimCLRTrainingSetupHook()]


def moco(head: str = "simclr_head", **kwargs):
    loss_fn = IMAGE_EMBEDDER_LOSS_FUNCTIONS.get("moco_loss")(**kwargs)
    head = IMAGE_EMBEDDER_HEADS.get(head)(**kwargs)

    return (
        loss_fn,
        head,
        [MoCoHook(loss_fn.loss_config.momentum, loss_fn.loss_config.shuffle_batch), TrainingSetupHook()],
    )


def barlow_twins(head: str = "barlow_twins_head", **kwargs):
    loss_fn = IMAGE_EMBEDDER_LOSS_FUNCTIONS.get("barlow_twins_loss")(**kwargs)
    head = IMAGE_EMBEDDER_HEADS.get(head)(**kwargs)

    return loss_fn, head, [TrainingSetupHook()]


def register_vissl_strategies(register: FlashRegistry):
    if _VISSL_AVAILABLE:
        for training_strategy in (dino, swav, simclr, moco, barlow_twins):
            register(training_strategy, name=training_strategy.__name__, adapter=VISSLAdapter, providers=_VISSL)
