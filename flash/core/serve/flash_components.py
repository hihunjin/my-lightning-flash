import inspect
from typing import Any, Callable, Mapping

import torch

from flash.core.data.batch import _ServeInputProcessor
from flash.core.data.data_pipeline import DataPipelineState
from flash.core.data.io.input import DataKeys
from flash.core.serve import expose, ModelComponent
from flash.core.serve.types.base import BaseType
from flash.core.utilities.stages import RunningStage


class FlashInputs(BaseType):
    def __init__(
        self,
        deserializer: Callable,
    ):
        self._deserializer = deserializer

    def serialize(self, *args) -> Any:  # pragma: no cover
        return None

    def deserialize(self, data: str) -> Any:  # pragma: no cover
        return self._deserializer(data)


class FlashOutputs(BaseType):
    def __init__(
        self,
        output: Callable,
    ):
        self._output = output

    def serialize(self, outputs) -> Any:  # pragma: no cover
        results = []
        if isinstance(outputs, (list, torch.Tensor)):
            for output in outputs:
                result = self._output(output)
                if isinstance(result, Mapping):
                    result = result[DataKeys.PREDS]
                results.append(result)
        if len(results) == 1:
            return results[0]
        return results

    def deserialize(self, data: str) -> Any:  # pragma: no cover
        return None


def build_flash_serve_model_component(model, serve_input):

    data_pipeline_state = DataPipelineState()
    for properties in [
        serve_input,
        getattr(serve_input, "transform", None),
        model._output_transform,
        model._output,
        model,
    ]:
        if properties is not None and hasattr(properties, "attach_data_pipeline_state"):
            properties.attach_data_pipeline_state(data_pipeline_state)

    data_pipeline = model.build_data_pipeline()

    class FlashServeModelComponent(ModelComponent):
        def __init__(self, model):
            self.model = model
            self.model.eval()
            self.data_pipeline = model.build_data_pipeline()
            self.serve_input = serve_input
            self.dataloader_collate_fn = self.serve_input._create_dataloader_collate_fn([])
            self.on_after_batch_transfer_fn = self.serve_input._create_on_after_batch_transfer_fn([])
            self.output_transform_processor = self.data_pipeline.output_transform_processor(
                RunningStage.SERVING, is_serving=True
            )
            # todo (tchaton) Remove this hack
            self.extra_arguments = len(inspect.signature(self.model.transfer_batch_to_device).parameters) == 3
            self.device = self.model.device

        @expose(
            inputs={"inputs": FlashInputs(_ServeInputProcessor(serve_input))},
            outputs={"outputs": FlashOutputs(data_pipeline.output_processor())},
        )
        def predict(self, inputs):
            with torch.no_grad():
                if self.extra_arguments:
                    inputs = self.model.transfer_batch_to_device(inputs, self.device, 0)
                else:
                    inputs = self.model.transfer_batch_to_device(inputs, self.device)
                inputs = self.on_after_batch_transfer_fn(inputs)
                preds = self.model.predict_step(inputs, 0)
                preds = self.output_transform_processor(preds)
                return preds

    return FlashServeModelComponent(model)
