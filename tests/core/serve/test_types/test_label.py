import pytest
import torch

from flash.core.serve.types import Label


def test_path(session_global_datadir):
    label = Label(path=str(session_global_datadir / "imagenet_labels.txt"))
    assert label.deserialize("chickadee") == torch.tensor(19)
    assert label.serialize(torch.tensor(19)) == "chickadee"


def test_list():
    label = Label(classes=["classA", "classB"])
    assert label.deserialize("classA") == torch.tensor(0)


def test_dict():
    label = Label(classes={56: "classA", 48: "classB"})
    assert label.deserialize("classA") == torch.tensor(56)

    with pytest.raises(TypeError):
        Label(classes={"wrongtype": "classA"})


def test_wrong_type():
    with pytest.raises(TypeError):
        Label(classes=set())
    with pytest.raises(ValueError):
        Label(classes=None)
