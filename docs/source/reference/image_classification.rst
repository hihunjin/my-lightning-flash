.. customcarditem::
   :header: Image Classification
   :card_description: Learn to classify images with Flash and build an example Ants / Bees classifier.
   :image: https://pl-flash-data.s3.amazonaws.com/assets/thumbnails/image_classification.svg
   :tags: Image,Classification

.. _image_classification:

####################
Image Classification
####################

********
The Task
********

The task of identifying what is in an image is called image classification.
Typically, Image Classification is used to identify images containing a single object.
The task predicts which ‘class’ the image most likely belongs to with a degree of certainty.
A class is a label that describes what is in an image, such as ‘car’, ‘house’, ‘cat’ etc.

------

*******
Example
*******

Let's look at the task of predicting whether images contain Ants or Bees using the hymenoptera dataset.
The dataset contains ``train`` and ``validation`` folders, and then each folder contains a **bees** folder, with pictures of bees, and an **ants** folder with images of, you guessed it, ants.

.. code-block::

    hymenoptera_data
    ├── train
    │   ├── ants
    │   │   ├── 0013035.jpg
    │   │   ├── 1030023514_aad5c608f9.jpg
    │   │   ...
    │   └── bees
    │       ├── 1092977343_cb42b38d62.jpg
    │       ├── 1093831624_fb5fbe2308.jpg
    │       ...
    └── val
        ├── ants
        │   ├── 10308379_1b6c72e180.jpg
        │   ├── 1053149811_f62a3410d3.jpg
        │   ...
        └── bees
            ├── 1032546534_06907fe3b3.jpg
            ├── 10870992_eebeeb3a12.jpg
            ...

Once we've downloaded the data using :func:`~flash.core.data.download_data`, we create the :class:`~flash.image.classification.data.ImageClassificationData`.
We select a pre-trained backbone to use for our :class:`~flash.image.classification.model.ImageClassifier` and fine-tune on the hymenoptera data.
We then use the trained :class:`~flash.image.classification.model.ImageClassifier` for inference.
Finally, we save the model.
Here's the full example:

.. literalinclude:: ../../../flash_examples/image_classification.py
    :language: python
    :lines: 14-

------

**********
Flash Zero
**********

The image classifier can be used directly from the command line with zero code using :ref:`flash_zero`.
You can run the hymenoptera example with:

.. code-block:: bash

    flash image_classification

To view configuration options and options for running the image classifier with your own data, use:

.. code-block:: bash

    flash image_classification --help

------

**********************
Custom Transformations
**********************

Flash automatically applies some default image transformations and augmentations, but you may wish to customize these for your own use case.
The base :class:`~flash.core.data.io.input_transform.InputTransform` defines 7 hooks for different stages in the data loading pipeline.
To apply image augmentations you can directly import the ``default_transforms`` from ``flash.image.classification.transforms`` and then merge your custom image transformations with them using the :func:`~flash.core.data.transforms.merge_transforms` helper function.
Here's an example where we load the default transforms and merge with custom `torchvision` transformations.


.. testsetup:: transformations

    from flash.core.data.utils import download_data

    download_data("https://pl-flash-data.s3.amazonaws.com/hymenoptera_data.zip", "./data")

.. testcode:: transformations

    from torchvision import transforms as T

    from typing import Tuple, Callable
    import flash
    from flash.core.data.io.input import DataKeys
    from flash.core.data.transforms import ApplyToKeys, merge_transforms
    from flash.image import ImageClassificationData, ImageClassifier
    from flash.core.data.io.input_transform import InputTransform
    from flash.image.classification.transforms import default_transforms
    from dataclasses import dataclass


    @dataclass
    class ImageClassificationInputTransform(InputTransform):

        image_size: Tuple[int, int] = (196, 196)

        def input_per_sample_transform(self):
            return T.Compose(
                [T.ToTensor(), T.Resize(self.image_size), T.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])]
            )

        def train_input_per_sample_transform(self):
            return T.Compose(
                [
                    T.ToTensor(),
                    T.Resize(self.image_size),
                    T.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
                    T.RandomHorizontalFlip(),
                    T.ColorJitter(),
                    T.RandomAutocontrast(),
                    T.RandomPerspective(),
                ]
            )

        def target_per_sample_transform(self) -> Callable:
            return torch.as_tensor


    datamodule = ImageClassificationData.from_folders(
        train_folder="data/hymenoptera_data/train/",
        val_folder="data/hymenoptera_data/val/",
        train_transform=ImageClassificationInputTransform,
        transform_kwargs=dict(image_size=(128, 128)),
        batch_size=1,
    )

    model = ImageClassifier(backbone="resnet18", num_classes=datamodule.num_classes)

    trainer = flash.Trainer(max_epochs=1)
    trainer.finetune(model, datamodule=datamodule, strategy="freeze")


.. testoutput:: transformations
    :hide:

    ...

------

*******
Serving
*******

The :class:`~flash.image.classification.model.ImageClassifier` is servable.
This means you can call ``.serve`` to serve your :class:`~flash.core.model.Task`.
Here's an example:

.. literalinclude:: ../../../flash_examples/serve/image_classification/inference_server.py
    :language: python
    :lines: 14-

You can now perform inference from your client like this:

.. literalinclude:: ../../../flash_examples/serve/image_classification/client.py
    :language: python
    :lines: 14-
