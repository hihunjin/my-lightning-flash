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
from typing import Optional

from pytorch_lightning.utilities.enums import LightningEnum


class RunningStage(LightningEnum):
    """Enum for the current running stage.

    This stage complements :class:`TrainerFn` by specifying the current running stage for each function.
    More than one running stage value can be set while a :class:`TrainerFn` is running:

        - ``TrainerFn.FITTING`` - ``RunningStage.{SANITY_CHECKING,TRAINING,VALIDATING}``
        - ``TrainerFn.VALIDATING`` - ``RunningStage.VALIDATING``
        - ``TrainerFn.TESTING`` - ``RunningStage.TESTING``
        - ``TrainerFn.PREDICTING`` - ``RunningStage.PREDICTING``
        - ``TrainerFn.SERVING`` - ``RunningStage.SERVING``
        - ``TrainerFn.TUNING`` - ``RunningStage.{TUNING,SANITY_CHECKING,TRAINING,VALIDATING}``
    """

    TRAINING = "train"
    SANITY_CHECKING = "sanity_check"
    VALIDATING = "validate"
    TESTING = "test"
    PREDICTING = "predict"
    SERVING = "serve"
    TUNING = "tune"

    @property
    def evaluating(self) -> bool:
        return self in (self.VALIDATING, self.TESTING)

    @property
    def dataloader_prefix(self) -> Optional[str]:
        if self in (self.SANITY_CHECKING, self.TUNING):
            return None
        if self == self.VALIDATING:
            return "val"
        return self.value


_STAGES_PREFIX = {
    RunningStage.TRAINING: "train",
    RunningStage.TESTING: "test",
    RunningStage.VALIDATING: "val",
    RunningStage.PREDICTING: "predict",
    RunningStage.SERVING: "serve",
}

_STAGES_PREFIX_VALUES = {"train", "test", "val", "predict", "serve"}

_RUNNING_STAGE_MAPPING = {
    RunningStage.TRAINING: RunningStage.TRAINING,
    RunningStage.SANITY_CHECKING: RunningStage.VALIDATING,
    RunningStage.VALIDATING: RunningStage.VALIDATING,
    RunningStage.TESTING: RunningStage.TESTING,
    RunningStage.PREDICTING: RunningStage.PREDICTING,
    RunningStage.SERVING: RunningStage.SERVING,
    RunningStage.TUNING: RunningStage.TUNING,
}
