import pytest
import torch

from flash.core.serve.types import Number


def test_serialize():
    num = Number()
    tensor = torch.tensor([[1]])
    assert 1 == num.serialize(tensor)
    assert isinstance(num.serialize(tensor.to(torch.float32)), float)
    assert isinstance(num.serialize(tensor.to(torch.float64)), float)
    assert isinstance(num.serialize(tensor.to(torch.int16)), int)
    assert isinstance(num.serialize(tensor.to(torch.int32)), int)
    assert isinstance(num.serialize(tensor.to(torch.int64)), int)
    assert isinstance(num.serialize(tensor.to(torch.complex64)), complex)

    tensor = torch.tensor([1, 2])
    with pytest.raises(ValueError):
        # only one element tensors can be converted to Python scalars
        num.serialize(tensor)


def test_deserialize():
    num = Number()
    assert num.deserialize(1).shape == torch.Size([1, 1])
    assert torch.allclose(num.deserialize(1), torch.tensor([[1]]))
    assert num.deserialize(1).dtype == torch.int64
    assert num.deserialize(2.0).dtype == torch.float32
