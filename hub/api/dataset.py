import os
import numpy as np
from time import process_time
import hub
from typing import Optional, Union

from hub.auto.unstructured.kaggle import download_kaggle_dataset
from hub.auto.unstructured.image_classification import ImageClassification
from hub.client.client import HubBackendClient
from hub.core.dataset import Dataset
from hub import core
from hub.constants import DEFAULT_MEMORY_CACHE_SIZE, DEFAULT_LOCAL_CACHE_SIZE
from hub.util.auto import get_most_common_extension
from hub.util.bugout_reporter import feature_report_path
from hub.util.keys import dataset_exists
from hub.util.exceptions import (
    DatasetHandlerError,
    AutoCompressionError,
    InvalidFileExtension,
    InvalidPathException,
    SamePathException,
)
from hub.util.storage import get_storage_and_cache_chain, storage_provider_from_path


class dataset:
    def __new__(
        cls,
        path: str,
        read_only: bool = False,
        overwrite: bool = False,
        public: bool = True,
        memory_cache_size: int = DEFAULT_MEMORY_CACHE_SIZE,
        local_cache_size: int = DEFAULT_LOCAL_CACHE_SIZE,
        creds: Optional[dict] = None,
        token: Optional[str] = None,
    ):
        """Returns a Dataset object referencing either a new or existing dataset.

        Important:
            Using `overwrite` will delete all of your data if it exists! Be very careful when setting this parameter.

        Args:
            path (str): The full path to the dataset. Can be:-
                - a Hub cloud path of the form hub://username/datasetname. To write to Hub cloud datasets, ensure that you are logged in to Hub (use 'activeloop login' from command line)
                - an s3 path of the form s3://bucketname/path/to/dataset. Credentials are required in either the environment or passed to the creds argument.
                - a local file system path of the form ./path/to/dataset or ~/path/to/dataset or path/to/dataset.
                - a memory path of the form mem://path/to/dataset which doesn't save the dataset but keeps it in memory instead. Should be used only for testing as it does not persist.
            read_only (bool): Opens dataset in read only mode if this is passed as True. Defaults to False.
                Datasets stored on Hub cloud that your account does not have write access to will automatically open in read mode.
            overwrite (bool): WARNING: If set to True this overwrites the dataset if it already exists. This can NOT be undone! Defaults to False.
            public (bool): Defines if the dataset will have public access. Applicable only if Hub cloud storage is used and a new Dataset is being created. Defaults to True.
            memory_cache_size (int): The size of the memory cache to be used in MB.
            local_cache_size (int): The size of the local filesystem cache to be used in MB.
            creds (dict, optional): A dictionary containing credentials used to access the dataset at the path.
                This takes precedence over credentials present in the environment. Currently only works with s3 paths.
                It supports 'aws_access_key_id', 'aws_secret_access_key', 'aws_session_token', 'endpoint_url' and 'region' as keys.
            token (str, optional): Activeloop token, used for fetching credentials for Hub datasets. This is optional, tokens are normally autogenerated.

        Returns:
            Dataset object created using the arguments provided.
        """
        if creds is None:
            creds = {}

        feature_report_path(path, "dataset", {"Overwrite": overwrite})

        storage, cache_chain = get_storage_and_cache_chain(
            path=path,
            read_only=read_only,
            creds=creds,
            token=token,
            memory_cache_size=memory_cache_size,
            local_cache_size=local_cache_size,
        )
        if overwrite and dataset_exists(storage):
            storage.clear()

        read_only = storage.read_only
        return Dataset(
            storage=cache_chain, read_only=read_only, public=public, token=token
        )

    @staticmethod
    def empty(
        path: str,
        overwrite: bool = False,
        public: Optional[bool] = True,
        memory_cache_size: int = DEFAULT_MEMORY_CACHE_SIZE,
        local_cache_size: int = DEFAULT_LOCAL_CACHE_SIZE,
        creds: Optional[dict] = None,
        token: Optional[str] = None,
    ) -> Dataset:
        """Creates an empty dataset

        Important:
            Using `overwrite` will delete all of your data if it exists! Be very careful when setting this parameter.

        Args:
            path (str): The full path to the dataset. Can be:-
                - a Hub cloud path of the form hub://username/datasetname. To write to Hub cloud datasets, ensure that you are logged in to Hub (use 'activeloop login' from command line)
                - an s3 path of the form s3://bucketname/path/to/dataset. Credentials are required in either the environment or passed to the creds argument.
                - a local file system path of the form ./path/to/dataset or ~/path/to/dataset or path/to/dataset.
                - a memory path of the form mem://path/to/dataset which doesn't save the dataset but keeps it in memory instead. Should be used only for testing as it does not persist.
            overwrite (bool): WARNING: If set to True this overwrites the dataset if it already exists. This can NOT be undone! Defaults to False.
            public (bool, optional): Defines if the dataset will have public access. Applicable only if Hub cloud storage is used and a new Dataset is being created. Defaults to True.
            memory_cache_size (int): The size of the memory cache to be used in MB.
            local_cache_size (int): The size of the local filesystem cache to be used in MB.
            creds (dict, optional): A dictionary containing credentials used to access the dataset at the path.
                This takes precedence over credentials present in the environment. Currently only works with s3 paths.
                It supports 'aws_access_key_id', 'aws_secret_access_key', 'aws_session_token', 'endpoint_url' and 'region' as keys.
            token (str, optional): Activeloop token, used for fetching credentials for Hub datasets. This is optional, tokens are normally autogenerated.

        Returns:
            Dataset object created using the arguments provided.

        Raises:
            DatasetHandlerError: If a Dataset already exists at the given path and overwrite is False.
        """
        if creds is None:
            creds = {}

        feature_report_path(path, "empty", {"Overwrite": overwrite})

        storage, cache_chain = get_storage_and_cache_chain(
            path=path,
            read_only=False,
            creds=creds,
            token=token,
            memory_cache_size=memory_cache_size,
            local_cache_size=local_cache_size,
        )

        if overwrite and dataset_exists(storage):
            storage.clear()
        elif dataset_exists(storage):
            raise DatasetHandlerError(
                f"A dataset already exists at the given path ({path}). If you want to create a new empty dataset, either specify another path or use overwrite=True. If you want to load the dataset that exists at this path, use hub.load() instead."
            )

        read_only = storage.read_only
        return Dataset(
            storage=cache_chain, read_only=read_only, public=public, token=token
        )

    @staticmethod
    def load(
        path: str,
        read_only: bool = False,
        overwrite: bool = False,
        public: Optional[bool] = True,
        memory_cache_size: int = DEFAULT_MEMORY_CACHE_SIZE,
        local_cache_size: int = DEFAULT_LOCAL_CACHE_SIZE,
        creds: Optional[dict] = None,
        token: Optional[str] = None,
    ) -> Dataset:
        """Loads an existing dataset

        Important:
            Using `overwrite` will delete all of your data if it exists! Be very careful when setting this parameter.

        Args:
            path (str): The full path to the dataset. Can be:-
                - a Hub cloud path of the form hub://username/datasetname. To write to Hub cloud datasets, ensure that you are logged in to Hub (use 'activeloop login' from command line)
                - an s3 path of the form s3://bucketname/path/to/dataset. Credentials are required in either the environment or passed to the creds argument.
                - a local file system path of the form ./path/to/dataset or ~/path/to/dataset or path/to/dataset.
                - a memory path of the form mem://path/to/dataset which doesn't save the dataset but keeps it in memory instead. Should be used only for testing as it does not persist.
            read_only (bool): Opens dataset in read only mode if this is passed as True. Defaults to False.
                Datasets stored on Hub cloud that your account does not have write access to will automatically open in read mode.
            overwrite (bool): WARNING: If set to True this overwrites the dataset if it already exists. This can NOT be undone! Defaults to False.
            public (bool, optional): Defines if the dataset will have public access. Applicable only if Hub cloud storage is used and a new Dataset is being created. Defaults to True.
            memory_cache_size (int): The size of the memory cache to be used in MB.
            local_cache_size (int): The size of the local filesystem cache to be used in MB.
            creds (dict, optional): A dictionary containing credentials used to access the dataset at the path.
                This takes precedence over credentials present in the environment. Currently only works with s3 paths.
                It supports 'aws_access_key_id', 'aws_secret_access_key', 'aws_session_token', 'endpoint_url' and 'region' as keys.
            token (str, optional): Activeloop token, used for fetching credentials for Hub datasets. This is optional, tokens are normally autogenerated.

        Returns:
            Dataset object created using the arguments provided.

        Raises:
            DatasetHandlerError: If a Dataset does not exist at the given path.
        """
        if creds is None:
            creds = {}

        feature_report_path(path, "load", {"Overwrite": overwrite})

        storage, cache_chain = get_storage_and_cache_chain(
            path=path,
            read_only=read_only,
            creds=creds,
            token=token,
            memory_cache_size=memory_cache_size,
            local_cache_size=local_cache_size,
        )

        if not dataset_exists(storage):
            raise DatasetHandlerError(
                f"A Hub dataset does not exist at the given path ({path}). Check the path provided or in case you want to create a new dataset, use hub.empty()."
            )
        if overwrite:
            storage.clear()

        read_only = storage.read_only
        return Dataset(
            storage=cache_chain, read_only=read_only, public=public, token=token
        )

    @staticmethod
    def delete(path: str, force: bool = False, large_ok: bool = False) -> None:
        """Deletes a dataset at a given path.
        This is an IRREVERSIBLE operation. Data once deleted can not be recovered.

        Args:
            path (str): The path to the dataset to be deleted.
            force (bool): Delete data regardless of whether
                it looks like a hub dataset. All data at the path will be removed.
            large_ok (bool): Delete datasets larger than 1GB. Disabled by default.
        """

        feature_report_path(path, "delete", {"Force": force, "Large_OK": large_ok})

        try:
            ds = hub.load(path)
            ds.delete(large_ok=large_ok)
        except:
            if force:
                base_storage = storage_provider_from_path(
                    path, creds={}, read_only=False, token=None
                )
                base_storage.clear()
            else:
                raise

    @staticmethod
    def fix(path: str, backed_up: bool = False) -> None:
        """Attempts to fix a corrupted dataset.

        Important:
            To be 100% safe, you should first back up your dataset. This method is experimental and may corrupt your dataset further!

        Args:
            path (str): Path to the corrupted dataset.
            backed_up (bool): Must be explicitly set to `True`.

        Raises:
            ValueError: If dataset is not marked as backed up.
        """

        if not backed_up:
            raise ValueError(
                "BACK UP YOUR DATASET BEFORE CALLING FIX! As an extra precaution, you must first set the `backed_up` argument to `True` in `hub.fix`."
            )

        core.chunk_engine.FIX_TENSOR_LENGTH = True
        ds = hub.load(path)
        ds.synchronize()

        core.chunk_engine.FIX_TENSOR_LENGTH = False
        ds.flush()

    @staticmethod
    def like(
        path: str,
        source: Union[str, Dataset],
        creds: dict = None,
        overwrite: bool = False,
    ) -> Dataset:
        """Copies the `source` dataset's structure to a new location. No samples are copied, only the meta/info for the dataset and it's tensors.

        Args:
            path (str): Path where the new dataset will be created.
            source (Union[str, Dataset]): Path or dataset object that will be used as the template for the new dataset.
            creds (dict): Credentials that will be used to create the new dataset.
            overwrite (bool): If True and a dataset exists at `destination`, it will be overwritten. Defaults to False.

        Returns:
            Dataset: New dataset object.
        """

        feature_report_path(path, "like", {"Overwrite": overwrite})

        destination_ds = dataset.empty(path, creds=creds, overwrite=overwrite)
        source_ds = source
        if isinstance(source, str):
            source_ds = dataset.load(source)

        for tensor_name in source_ds.version_state["meta"].tensors:  # type: ignore
            destination_ds.create_tensor_like(tensor_name, source_ds[tensor_name])

        destination_ds.info.update(source_ds.info.__getstate__())  # type: ignore

        return destination_ds

    @staticmethod
    def ingest(
        src: str,
        dest: str,
        images_compression: str = "auto",
        dest_creds: dict = None,
        progress_bar: bool = True,
        summary: bool = True,
        **dataset_kwargs,
    ) -> Dataset:
        """Ingests a dataset from a source and stores it as a structured dataset to destination

        Note:
            - Currently only local source paths and image classification datasets are supported for automatic ingestion.
            - Supported filetypes: png/jpeg/jpg.
            - All files and sub-directories with unsupported filetypes are ignored.
            - Valid source directory structures look like:

            ```
                data/
                    img0.jpg
                    img1.jpg
                    ...

            ```
            or
            ```
                data/
                    class0/
                        cat0.jpg
                        ...
                    class1/
                        dog0.jpg
                        ...
                    ...

            ```
            or
            ```
                data/
                    train/
                        class0/
                            img0.jpg
                            ...
                        ...
                    val/
                        class0/
                            img0.jpg
                            ...
                        ...
                    ...
            ```

            - Classes defined as sub-directories can be accessed at `ds["test/labels"].info.class_names`.
            - Support for train and test sub directories is present under ds["train/images"], ds["train/labels"] and ds["test/images"], ds["test/labels"]
            - Mapping filenames to classes from an external file is currently not supported.

        Args:
            src (str): Local path to where the unstructured dataset is stored.
            dest (str): Destination path where the structured dataset will be stored. Can be:-
                - a Hub cloud path of the form hub://username/datasetname. To write to Hub cloud datasets, ensure that you are logged in to Hub (use 'activeloop login' from command line)
                - an s3 path of the form s3://bucketname/path/to/dataset. Credentials are required in either the environment or passed to the creds argument.
                - a local file system path of the form ./path/to/dataset or ~/path/to/dataset or path/to/dataset.
                - a memory path of the form mem://path/to/dataset which doesn't save the dataset but keeps it in memory instead. Should be used only for testing as it does not persist.
            images_compression (str): For image classification datasets, this compression will be used for the `images` tensor. If images_compression is "auto", compression will be automatically determined by the most common extension in the directory.
            dest_creds (dict): A dictionary containing credentials used to access the destination path of the dataset.
            progress_bar (bool): Enables or disables ingestion progress bar. Defaults to True.
            summary (bool): If True, a summary of skipped files will be printed after completion. Defaults to True.
            **dataset_kwargs: Any arguments passed here will be forwarded to the dataset creator function.

        Returns:
            Dataset: New dataset object with structured dataset.

        Raises:
            InvalidPathException: If the source directory does not exist.
            SamePathException: If the source and destination path are same.
            AutoCompressionError: If the source director is empty or does not contain a valid extension.
            InvalidFileExtension: If the most frequent file extension is found to be 'None' during auto-compression.
        """

        if not os.path.isdir(src):
            raise InvalidPathException(src)

        if os.path.isdir(dest) and os.path.samefile(src, dest):
            raise SamePathException(src)

        if images_compression == "auto":
            images_compression = get_most_common_extension(src)
            if images_compression is None:
                raise InvalidFileExtension(src)

        ds = hub.dataset(dest, creds=dest_creds, **dataset_kwargs)

        # TODO: support more than just image classification (and update docstring)
        unstructured = ImageClassification(source=src)

        # TODO: auto detect compression
        unstructured.structure(
            ds,  # type: ignore
            use_progress_bar=progress_bar,
            generate_summary=summary,
            image_tensor_args={"sample_compression": images_compression},
        )

        return ds  # type: ignore

    @staticmethod
    def ingest_kaggle(
        tag: str,
        src: str,
        dest: str,
        exist_ok: bool = False,
        images_compression: str = "auto",
        dest_creds: dict = None,
        kaggle_credentials: dict = None,
        progress_bar: bool = True,
        summary: bool = True,
        **dataset_kwargs,
    ) -> Dataset:
        """Download and ingest a kaggle dataset and store it as a structured dataset to destination

        Note:
            Currently only local source paths and image classification datasets are supported for automatic ingestion.

        Args:
            tag (str): Kaggle dataset tag. Example: `"coloradokb/dandelionimages"` points to https://www.kaggle.com/coloradokb/dandelionimages
            src (str): Local path to where the raw kaggle dataset will be downlaoded to.
            dest (str): Destination path where the structured dataset will be stored. Can be:
                - a Hub cloud path of the form hub://username/datasetname. To write to Hub cloud datasets, ensure that you are logged in to Hub (use 'activeloop login' from command line)
                - an s3 path of the form s3://bucketname/path/to/dataset. Credentials are required in either the environment or passed to the creds argument.
                - a local file system path of the form ./path/to/dataset or ~/path/to/dataset or path/to/dataset.
                - a memory path of the form mem://path/to/dataset which doesn't save the dataset but keeps it in memory instead. Should be used only for testing as it does not persist.
            exist_ok (bool): If the kaggle dataset was already downloaded and `exist_ok` is True, ingestion will proceed without error.
            images_compression (str): For image classification datasets, this compression will be used for the `images` tensor. If images_compression is "auto", compression will be automatically determined by the most common extension in the directory.
            dest_creds (dict): A dictionary containing credentials used to access the destination path of the dataset.
            kaggle_credentials (dict): A dictionary containing kaggle credentials {"username":"YOUR_USERNAME", "key": "YOUR_KEY"}. If None, environment variables/the kaggle.json file will be used if available.
            progress_bar (bool): Enables or disables ingestion progress bar. Set to true by default.
            summary (bool): Generates ingestion summary. Set to true by default.
            **dataset_kwargs: Any arguments passed here will be forwarded to the dataset creator function.

        Returns:
            Dataset: New dataset object with structured dataset.

        Raises:
            SamePathException: If the source and destination path are same.
        """

        if os.path.isdir(src) and os.path.isdir(dest):
            if os.path.samefile(src, dest):
                raise SamePathException(src)

        download_kaggle_dataset(
            tag,
            local_path=src,
            kaggle_credentials=kaggle_credentials,
            exist_ok=exist_ok,
        )

        ds = hub.ingest(
            src=src,
            dest=dest,
            images_compression=images_compression,
            dest_creds=dest_creds,
            progress_bar=progress_bar,
            summary=summary,
            **dataset_kwargs,
        )

        return ds

    @staticmethod
    def list(workspace: str = "") -> None:
        """List all available hub cloud datasets.

        Args:
            workspace (str): Specify user/organization name. If not given,
                returns a list of all datasets that can be accessed, regardless of what workspace they are in.
                Otherwise, lists all datasets in the given workspace.

        Returns:
            List of dataset names.
        """
        client = HubBackendClient()
        datasets = client.get_datasets(workspace=workspace)
        return datasets
