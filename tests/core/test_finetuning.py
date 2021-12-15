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
from numbers import Number
from typing import Iterable, List, Optional, Tuple, Union

import pytest
import pytorch_lightning as pl
import torch
from pytorch_lightning.callbacks.model_checkpoint import ModelCheckpoint
from pytorch_lightning.utilities.exceptions import MisconfigurationException
from torch import Tensor
from torch.nn import Flatten
from torch.nn import functional as F
from torch.nn import Linear, LogSoftmax, Module
from torch.utils.data import DataLoader

import flash
from flash.core.model import Task
from tests.helpers.boring_model import BoringModel


class DummyDataset(torch.utils.data.Dataset):
    def __init__(self, num_samples: int = 9):
        self.num_samples = num_samples

    def __getitem__(self, index: int) -> Tuple[Tensor, Number]:
        return torch.rand(1, 28, 28), torch.randint(10, size=(1,)).item()

    def __len__(self) -> int:
        return self.num_samples


class TestModel(BoringModel):
    def __init__(self):
        super().__init__()
        self.flatten = Flatten()
        self.layer = Linear(28 * 28, 50)
        self.layer1 = Linear(50, 20)
        self.layer2 = Linear(20, 10)
        self.softmax = LogSoftmax()

    def forward(self, x):
        return self.softmax(self.layer2(self.layer1(self.layer(self.flatten(x)))))


class TestTaskWithoutFinetuning(Task):
    def __init__(self, **kwargs):
        super().__init__(model=TestModel(), **kwargs)

    def modules_to_freeze(self) -> Optional[Union[Module, Iterable[Union[Module, Iterable]]]]:
        return None


class TestTaskWithFinetuning(Task):
    def __init__(self, **kwargs):
        super().__init__(model=TestModel(), **kwargs)

    def modules_to_freeze(self) -> Optional[Union[Module, Iterable[Union[Module, Iterable]]]]:
        return [self.model.layer, self.model.layer1]


# Using `ModelCheckpoint` callback because they are the last callback to be called and hence freezing of layers should
# be done by then.
class FreezeStrategyChecking(ModelCheckpoint):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def on_train_start(self, trainer: "pl.Trainer", pl_module: "pl.LightningModule") -> None:
        super().on_train_start(trainer, pl_module)
        modules: List[Module] = [pl_module.model.layer, pl_module.model.layer1]
        for module in modules:
            for parameter in module.parameters():
                assert not parameter.requires_grad


class FreezeUnfreezeStrategyChecking(ModelCheckpoint):
    def __init__(self, check_epoch: int, **kwargs):
        super().__init__(**kwargs)
        self.check_epoch = check_epoch

    def on_train_epoch_start(self, trainer, pl_module):
        super().on_train_epoch_start(trainer, pl_module)
        current_epoch = trainer.current_epoch
        modules: List[Module] = [pl_module.model.layer, pl_module.model.layer1]
        for module in modules:
            for parameter in module.parameters():
                assert parameter.requires_grad == (current_epoch >= self.check_epoch)


class UnfreezeMilestonesStrategyChecking(ModelCheckpoint):
    def __init__(self, check_epochs: List[int], num_layers: int, **kwargs):
        super().__init__(**kwargs)
        self.check_epochs = check_epochs
        self.num_layers = num_layers

    def on_train_epoch_start(self, trainer, pl_module):
        super().on_train_epoch_start(trainer, pl_module)
        current_epoch = trainer.current_epoch
        modules: List[Module] = [pl_module.model.layer, pl_module.model.layer1]
        if current_epoch >= self.check_epochs[1]:
            for module in modules:
                for parameter in module.parameters():
                    assert parameter.requires_grad
        elif current_epoch >= self.check_epochs[0] and current_epoch < self.check_epochs[1]:
            for parameter in modules[0].parameters():
                assert not parameter.requires_grad
            for parameter in modules[1].parameters():
                assert parameter.requires_grad
        else:
            for module in modules:
                for parameter in module.parameters():
                    assert not parameter.requires_grad


class CustomStrategyChecking(ModelCheckpoint):
    def __init__(self, check_epoch: int, **kwargs):
        super().__init__(**kwargs)
        self.check_epoch = check_epoch

    def on_train_epoch_start(self, trainer, pl_module):
        super().on_train_epoch_start(trainer, pl_module)
        current_epoch = trainer.current_epoch
        if current_epoch >= self.check_epoch:
            assert pl_module.model.layer.weight.requires_grad


@pytest.mark.parametrize(
    "strategy",
    [
        "no_freeze",
        "freeze",
        ("freeze_unfreeze", 1),
        ("unfreeze_milestones", ((5, 10), 5)),
    ],
)
def test_finetuning_with_none_return_type(strategy):
    task = TestTaskWithoutFinetuning(loss_fn=F.nll_loss)
    trainer = flash.Trainer(max_epochs=1, limit_train_batches=10)
    ds = DummyDataset()
    trainer.finetune(task, train_dataloader=DataLoader(ds), strategy=strategy)


@pytest.mark.parametrize(
    ("strategy", "checker_class", "checker_class_data"),
    [
        ("no_freeze", None, {}),
        ("freeze", FreezeStrategyChecking, {}),
        (("freeze_unfreeze", 2), FreezeUnfreezeStrategyChecking, {"check_epoch": 2}),
        (
            ("unfreeze_milestones", ((1, 3), 1)),
            UnfreezeMilestonesStrategyChecking,
            {"check_epochs": [1, 3], "num_layers": 1},
        ),
    ],
)
def test_finetuning(tmpdir, strategy, checker_class, checker_class_data):
    task = TestTaskWithFinetuning(loss_fn=F.nll_loss)
    callbacks = [] if checker_class is None else checker_class(dirpath=tmpdir, **checker_class_data)
    trainer = flash.Trainer(max_epochs=5, limit_train_batches=10, callbacks=callbacks)
    ds = DummyDataset()
    trainer.finetune(task, train_dataloader=DataLoader(ds), strategy=strategy)


@pytest.mark.parametrize(
    "strategy",
    [
        None,
        "chocolate",
        (12, 1),
        ("chocolate", 1),
        ("freeze_unfreeze", "True"),
        ("unfreeze_milestones", "False"),
        ("unfreeze_milestones", (10, 10)),
        ("unfreeze_milestones", (10, (10, 10))),
        ("unfreeze_milestones", ((10, 10), "True")),
        ("unfreeze_milestones", ((3.14, 10), 10)),
        ("unfreeze_milestones", ((10, 3.14), 10)),
    ],
)
def test_finetuning_errors_and_exceptions(strategy):
    task = TestTaskWithFinetuning(loss_fn=F.nll_loss)
    trainer = flash.Trainer(max_epochs=1, limit_train_batches=10)
    ds = DummyDataset()
    with pytest.raises(MisconfigurationException):
        trainer.finetune(task, train_dataloader=DataLoader(ds), strategy=strategy)
