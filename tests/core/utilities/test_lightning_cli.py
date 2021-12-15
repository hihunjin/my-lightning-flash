# Adapted from the Lightning CLI:
# https://github.com/PyTorchLightning/pytorch-lightning/blob/master/tests/utilities/test_cli.py
import inspect
import json
import os
import pickle
import sys
from argparse import Namespace
from contextlib import redirect_stdout
from io import StringIO
from typing import List, Optional, Union
from unittest import mock

import pytest
import torch
import yaml
from packaging import version
from pytorch_lightning import Callback, LightningDataModule, LightningModule, Trainer
from pytorch_lightning.callbacks import LearningRateMonitor, ModelCheckpoint
from pytorch_lightning.plugins.environments import SLURMEnvironment

from flash.core.utilities.compatibility import accelerator_connector
from flash.core.utilities.imports import _TORCHVISION_AVAILABLE
from flash.core.utilities.lightning_cli import (
    instantiate_class,
    LightningArgumentParser,
    LightningCLI,
    SaveConfigCallback,
)
from tests.helpers.boring_model import BoringDataModule, BoringModel

torchvision_version = version.parse("0")
if _TORCHVISION_AVAILABLE:
    torchvision_version = version.parse(__import__("torchvision").__version__)


@mock.patch("argparse.ArgumentParser.parse_args")
def test_default_args(mock_argparse, tmpdir):
    """Tests default argument parser for Trainer."""
    mock_argparse.return_value = Namespace(**Trainer.default_attributes())

    parser = LightningArgumentParser(add_help=False, parse_as_dict=False)
    args = parser.parse_args([])

    args.max_epochs = 5
    trainer = Trainer.from_argparse_args(args)

    assert isinstance(trainer, Trainer)
    assert trainer.max_epochs == 5


@pytest.mark.parametrize("cli_args", [["--accumulate_grad_batches=22"], ["--weights_save_path=./"], []])
def test_add_argparse_args_redefined(cli_args):
    """Redefines some default Trainer arguments via the cli and tests the Trainer initialization correctness."""
    parser = LightningArgumentParser(add_help=False, parse_as_dict=False)
    parser.add_lightning_class_args(Trainer, None)

    args = parser.parse_args(cli_args)

    # make sure we can pickle args
    pickle.dumps(args)

    # Check few deprecated args are not in namespace:
    for depr_name in ("gradient_clip", "nb_gpu_nodes", "max_nb_epochs"):
        assert depr_name not in args

    trainer = Trainer.from_argparse_args(args=args)
    pickle.dumps(trainer)

    assert isinstance(trainer, Trainer)


@pytest.mark.parametrize(
    ["cli_args", "expected"],
    [
        ("--auto_lr_find=True --auto_scale_batch_size=power", dict(auto_lr_find=True, auto_scale_batch_size="power")),
        (
            "--auto_lr_find any_string --auto_scale_batch_size ON",
            dict(auto_lr_find="any_string", auto_scale_batch_size=True),
        ),
        ("--auto_lr_find=Yes --auto_scale_batch_size=On", dict(auto_lr_find=True, auto_scale_batch_size=True)),
        ("--auto_lr_find Off --auto_scale_batch_size No", dict(auto_lr_find=False, auto_scale_batch_size=False)),
        ("--auto_lr_find TRUE --auto_scale_batch_size FALSE", dict(auto_lr_find=True, auto_scale_batch_size=False)),
        ("--limit_train_batches=100", dict(limit_train_batches=100)),
        ("--limit_train_batches 0.8", dict(limit_train_batches=0.8)),
        ("--weights_summary=null", dict(weights_summary=None)),
    ],
)
def test_parse_args_parsing(cli_args, expected):
    """Test parsing simple types and None optionals not modified."""
    cli_args = cli_args.split(" ") if cli_args else []
    parser = LightningArgumentParser(add_help=False, parse_as_dict=False)
    parser.add_lightning_class_args(Trainer, None)
    with mock.patch("sys.argv", ["any.py"] + cli_args):
        args = parser.parse_args()

    for k, v in expected.items():
        assert getattr(args, k) == v
    assert Trainer.from_argparse_args(args)


@pytest.mark.parametrize(
    ["cli_args", "expected", "instantiate"],
    [
        (["--gpus", "[0, 2]"], dict(gpus=[0, 2]), False),
        (["--tpu_cores=[1,3]"], dict(tpu_cores=[1, 3]), False),
        (['--accumulate_grad_batches={"5":3,"10":20}'], dict(accumulate_grad_batches={5: 3, 10: 20}), True),
    ],
)
def test_parse_args_parsing_complex_types(cli_args, expected, instantiate):
    """Test parsing complex types."""
    parser = LightningArgumentParser(add_help=False, parse_as_dict=False)
    parser.add_lightning_class_args(Trainer, None)
    with mock.patch("sys.argv", ["any.py"] + cli_args):
        args = parser.parse_args()

    for k, v in expected.items():
        assert getattr(args, k) == v
    if instantiate:
        assert Trainer.from_argparse_args(args)


@pytest.mark.parametrize(
    ["cli_args", "expected_gpu"],
    [
        ("--gpus 1", [0]),
        ("--gpus 0,", [0]),
        ("--gpus 0,1", [0, 1]),
    ],
)
def test_parse_args_parsing_gpus(monkeypatch, cli_args, expected_gpu):
    """Test parsing of gpus and instantiation of Trainer."""
    monkeypatch.setattr("torch.cuda.device_count", lambda: 2)
    cli_args = cli_args.split(" ") if cli_args else []
    parser = LightningArgumentParser(add_help=False, parse_as_dict=False)
    parser.add_lightning_class_args(Trainer, None)
    with mock.patch("sys.argv", ["any.py"] + cli_args):
        args = parser.parse_args()

    trainer = Trainer.from_argparse_args(args)
    assert trainer.data_parallel_device_ids == expected_gpu


@pytest.mark.skipif(
    sys.version_info < (3, 7),
    reason="signature inspection while mocking is not working in Python < 3.7 despite autospec",
)
@pytest.mark.parametrize(
    ["cli_args", "extra_args"],
    [
        ({}, {}),
        (dict(logger=False), {}),
        (dict(logger=False), dict(logger=True)),
        (dict(logger=False), dict(checkpoint_callback=True)),
    ],
)
def test_init_from_argparse_args(cli_args, extra_args):
    unknown_args = dict(unknown_arg=0)

    # unkown args in the argparser/namespace should be ignored
    with mock.patch("pytorch_lightning.Trainer.__init__", autospec=True, return_value=None) as init:
        trainer = Trainer.from_argparse_args(Namespace(**cli_args, **unknown_args), **extra_args)
        expected = dict(cli_args)
        expected.update(extra_args)  # extra args should override any cli arg
        init.assert_called_with(trainer, **expected)

    # passing in unknown manual args should throw an error
    with pytest.raises(TypeError, match=r"__init__\(\) got an unexpected keyword argument 'unknown_arg'"):
        Trainer.from_argparse_args(Namespace(**cli_args), **extra_args, **unknown_args)


class Model(LightningModule):
    def __init__(self, model_param: int):
        super().__init__()
        self.model_param = model_param


def model_builder(model_param: int) -> Model:
    return Model(model_param)


def trainer_builder(
    limit_train_batches: int, fast_dev_run: bool = False, callbacks: Optional[Union[List[Callback], Callback]] = None
) -> Trainer:
    return Trainer(limit_train_batches=limit_train_batches, fast_dev_run=fast_dev_run, callbacks=callbacks)


@pytest.mark.parametrize(["trainer_class", "model_class"], [(Trainer, Model), (trainer_builder, model_builder)])
def test_lightning_cli(trainer_class, model_class, monkeypatch):
    """Test that LightningCLI correctly instantiates model, trainer and calls fit."""

    expected_model = dict(model_param=7)
    expected_trainer = dict(limit_train_batches=100)

    def fit(trainer, model):
        for k, v in expected_model.items():
            assert getattr(model, k) == v
        for k, v in expected_trainer.items():
            assert getattr(trainer, k) == v
        save_callback = [x for x in trainer.callbacks if isinstance(x, SaveConfigCallback)]
        assert len(save_callback) == 1
        save_callback[0].on_train_start(trainer, model)

    def on_train_start(callback, trainer, _):
        config_dump = callback.parser.dump(callback.config, skip_none=False)
        for k, v in expected_model.items():
            assert f"  {k}: {v}" in config_dump
        for k, v in expected_trainer.items():
            assert f"  {k}: {v}" in config_dump
        trainer.ran_asserts = True

    monkeypatch.setattr(Trainer, "fit", fit)
    monkeypatch.setattr(SaveConfigCallback, "on_train_start", on_train_start)

    with mock.patch("sys.argv", ["any.py", "--model.model_param=7", "--trainer.limit_train_batches=100"]):
        cli = LightningCLI(model_class, trainer_class=trainer_class, save_config_callback=SaveConfigCallback)
        assert hasattr(cli.trainer, "ran_asserts") and cli.trainer.ran_asserts


def test_lightning_cli_args_callbacks(tmpdir):

    callbacks = [
        dict(
            class_path="pytorch_lightning.callbacks.LearningRateMonitor",
            init_args=dict(logging_interval="epoch", log_momentum=True),
        ),
        dict(class_path="pytorch_lightning.callbacks.ModelCheckpoint", init_args=dict(monitor="NAME")),
    ]

    class TestModel(BoringModel):
        def on_fit_start(self):
            callback = [c for c in self.trainer.callbacks if isinstance(c, LearningRateMonitor)]
            assert len(callback) == 1
            assert callback[0].logging_interval == "epoch"
            assert callback[0].log_momentum is True
            callback = [c for c in self.trainer.callbacks if isinstance(c, ModelCheckpoint)]
            assert len(callback) == 1
            assert callback[0].monitor == "NAME"
            self.trainer.ran_asserts = True

    with mock.patch("sys.argv", ["any.py", f"--trainer.callbacks={json.dumps(callbacks)}"]):
        cli = LightningCLI(TestModel, trainer_defaults=dict(default_root_dir=str(tmpdir), fast_dev_run=True))

    assert cli.trainer.ran_asserts


def test_lightning_cli_configurable_callbacks(tmpdir):
    class MyLightningCLI(LightningCLI):
        def add_arguments_to_parser(self, parser):
            parser.add_lightning_class_args(LearningRateMonitor, "learning_rate_monitor")

    cli_args = [
        f"--trainer.default_root_dir={tmpdir}",
        "--trainer.max_epochs=1",
        "--learning_rate_monitor.logging_interval=epoch",
    ]

    with mock.patch("sys.argv", ["any.py"] + cli_args):
        cli = MyLightningCLI(BoringModel)

    callback = [c for c in cli.trainer.callbacks if isinstance(c, LearningRateMonitor)]
    assert len(callback) == 1
    assert callback[0].logging_interval == "epoch"


def test_lightning_cli_args_cluster_environments(tmpdir):
    plugins = [dict(class_path="pytorch_lightning.plugins.environments.SLURMEnvironment")]

    class TestModel(BoringModel):
        def on_fit_start(self):
            # Ensure SLURMEnvironment is set, instead of default LightningEnvironment
            assert isinstance(accelerator_connector(self.trainer)._cluster_environment, SLURMEnvironment)
            self.trainer.ran_asserts = True

    with mock.patch("sys.argv", ["any.py", f"--trainer.plugins={json.dumps(plugins)}"]):
        cli = LightningCLI(TestModel, trainer_defaults=dict(default_root_dir=str(tmpdir), fast_dev_run=True))

    assert cli.trainer.ran_asserts


def test_lightning_cli_args(tmpdir):

    cli_args = [
        f"--data.data_dir={tmpdir}",
        f"--trainer.default_root_dir={tmpdir}",
        "--trainer.max_epochs=1",
        "--trainer.weights_summary=null",
        "--seed_everything=1234",
    ]

    with mock.patch("sys.argv", ["any.py"] + cli_args):
        cli = LightningCLI(BoringModel, BoringDataModule, trainer_defaults={"callbacks": [LearningRateMonitor()]})

    assert cli.config["seed_everything"] == 1234
    config_path = tmpdir / "lightning_logs" / "version_0" / "config.yaml"
    assert os.path.isfile(config_path)
    with open(config_path) as f:
        config = yaml.safe_load(f.read())
    assert "model" not in config and "model" not in cli.config  # no arguments to include
    assert config["data"] == cli.config["data"]
    assert config["trainer"] == cli.config["trainer"]


def test_lightning_cli_save_config_cases(tmpdir):

    config_path = tmpdir / "config.yaml"
    cli_args = [
        f"--trainer.default_root_dir={tmpdir}",
        "--trainer.logger=False",
        "--trainer.fast_dev_run=1",
    ]

    # With fast_dev_run!=False config should not be saved
    with mock.patch("sys.argv", ["any.py"] + cli_args):
        LightningCLI(BoringModel)
    assert not os.path.isfile(config_path)

    # With fast_dev_run==False config should be saved
    cli_args[-1] = "--trainer.max_epochs=1"
    with mock.patch("sys.argv", ["any.py"] + cli_args):
        LightningCLI(BoringModel)
    assert os.path.isfile(config_path)

    # If run again on same directory exception should be raised since config file already exists
    with mock.patch("sys.argv", ["any.py"] + cli_args), pytest.raises(RuntimeError):
        LightningCLI(BoringModel)


def test_lightning_cli_config_and_subclass_mode(tmpdir):

    config = dict(
        model=dict(class_path="tests.helpers.boring_model.BoringModel"),
        data=dict(class_path="tests.helpers.boring_model.BoringDataModule", init_args=dict(data_dir=str(tmpdir))),
        trainer=dict(default_root_dir=str(tmpdir), max_epochs=1, weights_summary=None),
    )
    config_path = tmpdir / "config.yaml"
    with open(config_path, "w") as f:
        f.write(yaml.dump(config))

    with mock.patch("sys.argv", ["any.py", "--config", str(config_path)]):
        cli = LightningCLI(
            BoringModel,
            BoringDataModule,
            subclass_mode_model=True,
            subclass_mode_data=True,
            trainer_defaults={"callbacks": LearningRateMonitor()},
        )

    config_path = tmpdir / "lightning_logs" / "version_0" / "config.yaml"
    assert os.path.isfile(config_path)
    with open(config_path) as f:
        config = yaml.safe_load(f.read())
    assert config["model"] == cli.config["model"]
    assert config["data"] == cli.config["data"]
    assert config["trainer"] == cli.config["trainer"]


def any_model_any_data_cli():
    LightningCLI(
        LightningModule,
        LightningDataModule,
        subclass_mode_model=True,
        subclass_mode_data=True,
    )


def test_lightning_cli_help():

    cli_args = ["any.py", "--help"]
    out = StringIO()
    with mock.patch("sys.argv", cli_args), redirect_stdout(out), pytest.raises(SystemExit):
        any_model_any_data_cli()

    assert "--print_config" in out.getvalue()
    assert "--config" in out.getvalue()
    assert "--seed_everything" in out.getvalue()
    assert "--model.help" in out.getvalue()
    assert "--data.help" in out.getvalue()

    skip_params = {"self"}
    for param in inspect.signature(Trainer.__init__).parameters.keys():
        if param not in skip_params:
            assert f"--trainer.{param}" in out.getvalue()

    cli_args = ["any.py", "--data.help=tests.helpers.boring_model.BoringDataModule"]
    out = StringIO()
    with mock.patch("sys.argv", cli_args), redirect_stdout(out), pytest.raises(SystemExit):
        any_model_any_data_cli()

    assert "--data.init_args.data_dir" in out.getvalue()


def test_lightning_cli_print_config():

    cli_args = [
        "any.py",
        "--seed_everything=1234",
        "--model=tests.helpers.boring_model.BoringModel",
        "--data=tests.helpers.boring_model.BoringDataModule",
        "--print_config",
    ]

    out = StringIO()
    with mock.patch("sys.argv", cli_args), redirect_stdout(out), pytest.raises(SystemExit):
        any_model_any_data_cli()

    outval = yaml.safe_load(out.getvalue())
    assert outval["seed_everything"] == 1234
    assert outval["model"]["class_path"] == "tests.helpers.boring_model.BoringModel"
    assert outval["data"]["class_path"] == "tests.helpers.boring_model.BoringDataModule"


def test_lightning_cli_submodules(tmpdir):
    class MainModule(BoringModel):
        def __init__(
            self,
            submodule1: LightningModule,
            submodule2: LightningModule,
            main_param: int = 1,
        ):
            super().__init__()
            self.submodule1 = submodule1
            self.submodule2 = submodule2

    config = """model:
        main_param: 2
        submodule1:
            class_path: tests.helpers.boring_model.BoringModel
        submodule2:
            class_path: tests.helpers.boring_model.BoringModel
    """
    config_path = tmpdir / "config.yaml"
    with open(config_path, "w") as f:
        f.write(config)

    cli_args = [
        f"--trainer.default_root_dir={tmpdir}",
        "--trainer.max_epochs=1",
        f"--config={str(config_path)}",
    ]

    with mock.patch("sys.argv", ["any.py"] + cli_args):
        cli = LightningCLI(MainModule)

    assert cli.config["model"]["main_param"] == 2
    assert isinstance(cli.model.submodule1, BoringModel)
    assert isinstance(cli.model.submodule2, BoringModel)


@pytest.mark.skipif(torchvision_version < version.parse("0.8.0"), reason="torchvision>=0.8.0 is required")
def test_lightning_cli_torch_modules(tmpdir):
    class TestModule(BoringModel):
        def __init__(
            self,
            activation: torch.nn.Module = None,
            transform: Optional[List[torch.nn.Module]] = None,
        ):
            super().__init__()
            self.activation = activation
            self.transform = transform

    config = """model:
        activation:
          class_path: torch.nn.LeakyReLU
          init_args:
            negative_slope: 0.2
        transform:
          - class_path: torchvision.transforms.Resize
            init_args:
              size: 64
          - class_path: torchvision.transforms.CenterCrop
            init_args:
              size: 64
    """
    config_path = tmpdir / "config.yaml"
    with open(config_path, "w") as f:
        f.write(config)

    cli_args = [
        f"--trainer.default_root_dir={tmpdir}",
        "--trainer.max_epochs=1",
        f"--config={str(config_path)}",
    ]

    with mock.patch("sys.argv", ["any.py"] + cli_args):
        cli = LightningCLI(TestModule)

    assert isinstance(cli.model.activation, torch.nn.LeakyReLU)
    assert cli.model.activation.negative_slope == 0.2
    assert len(cli.model.transform) == 2
    assert all(isinstance(v, torch.nn.Module) for v in cli.model.transform)


class BoringModelRequiredClasses(BoringModel):
    def __init__(
        self,
        num_classes: int,
        batch_size: int = 8,
    ):
        super().__init__()
        self.num_classes = num_classes
        self.batch_size = batch_size


class BoringDataModuleBatchSizeAndClasses(BoringDataModule):
    def __init__(
        self,
        batch_size: int = 8,
    ):
        super().__init__()
        self.batch_size = batch_size
        self.num_classes = 5  # only available after instantiation


def test_lightning_cli_link_arguments(tmpdir):
    class MyLightningCLI(LightningCLI):
        def add_arguments_to_parser(self, parser):
            parser.link_arguments("data.batch_size", "model.batch_size")
            parser.link_arguments("data.num_classes", "model.num_classes", apply_on="instantiate")

    cli_args = [
        f"--trainer.default_root_dir={tmpdir}",
        "--trainer.max_epochs=1",
        "--data.batch_size=12",
    ]

    with mock.patch("sys.argv", ["any.py"] + cli_args):
        cli = MyLightningCLI(BoringModelRequiredClasses, BoringDataModuleBatchSizeAndClasses)

    assert cli.model.batch_size == 12
    assert cli.model.num_classes == 5

    class MyLightningCLI(LightningCLI):
        def add_arguments_to_parser(self, parser):
            parser.link_arguments("data.batch_size", "model.init_args.batch_size")
            parser.link_arguments("data.num_classes", "model.init_args.num_classes", apply_on="instantiate")

    cli_args[-1] = "--model=tests.core.utilities.test_lightning_cli.BoringModelRequiredClasses"

    with mock.patch("sys.argv", ["any.py"] + cli_args):
        cli = MyLightningCLI(
            BoringModelRequiredClasses,
            BoringDataModuleBatchSizeAndClasses,
            subclass_mode_model=True,
        )

    assert cli.model.batch_size == 8
    assert cli.model.num_classes == 5


class CustomException(BaseException):
    pass


class EarlyExitTestModel(BoringModel):
    def on_fit_start(self):
        raise CustomException()

    def on_exception(self, execption):
        raise execption


@pytest.mark.parametrize("logger", (False, True))
@pytest.mark.parametrize(
    "trainer_kwargs",
    (
        dict(accelerator="ddp_cpu"),
        dict(accelerator="ddp_cpu", plugins="ddp_find_unused_parameters_false"),
    ),
)
def test_cli_ddp_spawn_save_config_callback(tmpdir, logger, trainer_kwargs):
    with mock.patch("sys.argv", ["any.py"]), pytest.raises(CustomException):
        LightningCLI(
            EarlyExitTestModel,
            trainer_defaults={
                "default_root_dir": str(tmpdir),
                "logger": logger,
                "max_steps": 1,
                "max_epochs": 1,
                **trainer_kwargs,
            },
        )
    if logger:
        config_dir = tmpdir / "lightning_logs"
        # no more version dirs should get created
        assert os.listdir(config_dir) == ["version_0"]
        config_path = config_dir / "version_0" / "config.yaml"
    else:
        config_path = tmpdir / "config.yaml"
    assert os.path.isfile(config_path)


def test_cli_config_overwrite(tmpdir):
    trainer_defaults = {"default_root_dir": str(tmpdir), "logger": False, "max_steps": 1, "max_epochs": 1}

    with mock.patch("sys.argv", ["any.py"]):
        LightningCLI(BoringModel, trainer_defaults=trainer_defaults)
    with mock.patch("sys.argv", ["any.py"]), pytest.raises(RuntimeError, match="Aborting to avoid overwriting"):
        LightningCLI(BoringModel, trainer_defaults=trainer_defaults)
    with mock.patch("sys.argv", ["any.py"]):
        LightningCLI(BoringModel, save_config_overwrite=True, trainer_defaults=trainer_defaults)


def test_lightning_cli_optimizer(tmpdir):
    class MyLightningCLI(LightningCLI):
        def add_arguments_to_parser(self, parser):
            parser.add_optimizer_args(torch.optim.Adam)

    cli_args = [
        f"--trainer.default_root_dir={tmpdir}",
        "--trainer.max_epochs=1",
    ]

    match = (
        "BoringModel.configure_optimizers` will be overridden by "
        "`MyLightningCLI.add_configure_optimizers_method_to_model`"
    )
    with mock.patch("sys.argv", ["any.py"] + cli_args), pytest.warns(UserWarning, match=match):
        cli = MyLightningCLI(BoringModel)

    assert cli.model.configure_optimizers is not BoringModel.configure_optimizers
    assert len(cli.trainer.optimizers) == 1
    assert isinstance(cli.trainer.optimizers[0], torch.optim.Adam)
    assert len(cli.trainer.lr_schedulers) == 0


def test_lightning_cli_optimizer_and_lr_scheduler(tmpdir):
    class MyLightningCLI(LightningCLI):
        def add_arguments_to_parser(self, parser):
            parser.add_optimizer_args(torch.optim.Adam)
            parser.add_lr_scheduler_args(torch.optim.lr_scheduler.ExponentialLR)

    cli_args = [
        f"--trainer.default_root_dir={tmpdir}",
        "--trainer.max_epochs=1",
        "--lr_scheduler.gamma=0.8",
    ]

    with mock.patch("sys.argv", ["any.py"] + cli_args):
        cli = MyLightningCLI(BoringModel)

    assert cli.model.configure_optimizers is not BoringModel.configure_optimizers
    assert len(cli.trainer.optimizers) == 1
    assert isinstance(cli.trainer.optimizers[0], torch.optim.Adam)
    assert len(cli.trainer.lr_schedulers) == 1
    assert isinstance(cli.trainer.lr_schedulers[0]["scheduler"], torch.optim.lr_scheduler.ExponentialLR)
    assert cli.trainer.lr_schedulers[0]["scheduler"].gamma == 0.8


def test_lightning_cli_optimizer_and_lr_scheduler_subclasses(tmpdir):
    class MyLightningCLI(LightningCLI):
        def add_arguments_to_parser(self, parser):
            parser.add_optimizer_args((torch.optim.SGD, torch.optim.Adam))
            parser.add_lr_scheduler_args((torch.optim.lr_scheduler.StepLR, torch.optim.lr_scheduler.ExponentialLR))

    optimizer_arg = dict(
        class_path="torch.optim.Adam",
        init_args=dict(lr=0.01),
    )
    lr_scheduler_arg = dict(
        class_path="torch.optim.lr_scheduler.StepLR",
        init_args=dict(step_size=50),
    )
    cli_args = [
        f"--trainer.default_root_dir={tmpdir}",
        "--trainer.max_epochs=1",
        f"--optimizer={json.dumps(optimizer_arg)}",
        f"--lr_scheduler={json.dumps(lr_scheduler_arg)}",
    ]

    with mock.patch("sys.argv", ["any.py"] + cli_args):
        cli = MyLightningCLI(BoringModel)

    assert len(cli.trainer.optimizers) == 1
    assert isinstance(cli.trainer.optimizers[0], torch.optim.Adam)
    assert len(cli.trainer.lr_schedulers) == 1
    assert isinstance(cli.trainer.lr_schedulers[0]["scheduler"], torch.optim.lr_scheduler.StepLR)
    assert cli.trainer.lr_schedulers[0]["scheduler"].step_size == 50


def test_lightning_cli_optimizers_and_lr_scheduler_with_link_to(tmpdir):
    class MyLightningCLI(LightningCLI):
        def add_arguments_to_parser(self, parser):
            parser.add_optimizer_args(torch.optim.Adam, nested_key="optim1", link_to="model.optim1")
            parser.add_optimizer_args((torch.optim.ASGD, torch.optim.SGD), nested_key="optim2", link_to="model.optim2")
            parser.add_lr_scheduler_args(torch.optim.lr_scheduler.ExponentialLR, link_to="model.scheduler")

    class TestModel(BoringModel):
        def __init__(
            self,
            optim1: dict,
            optim2: dict,
            scheduler: dict,
        ):
            super().__init__()
            self.optim1 = instantiate_class(self.parameters(), optim1)
            self.optim2 = instantiate_class(self.parameters(), optim2)
            self.scheduler = instantiate_class(self.optim1, scheduler)

    cli_args = [
        f"--trainer.default_root_dir={tmpdir}",
        "--trainer.max_epochs=1",
        "--optim2.class_path=torch.optim.SGD",
        "--optim2.init_args.lr=0.01",
        "--lr_scheduler.gamma=0.2",
    ]

    with mock.patch("sys.argv", ["any.py"] + cli_args):
        cli = MyLightningCLI(TestModel)

    assert isinstance(cli.model.optim1, torch.optim.Adam)
    assert isinstance(cli.model.optim2, torch.optim.SGD)
    assert isinstance(cli.model.scheduler, torch.optim.lr_scheduler.ExponentialLR)
