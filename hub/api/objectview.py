from hub.api.datasetview import DatasetView
from hub.schema import Sequence, Tensor, SchemaDict, Primitive
from hub.api.dataset_utils import slice_extract_info, slice_split, str_to_int

# from hub.exceptions import NoneValueException
import collections.abc as abc
import hub.api as api


class ObjectView:
    def __init__(
        self,
        dataset,
        subpath=None,
        slice_list=None,
        nums=[],
        offsets=[],
        squeeze_dims=[],
        inner_schema_obj=None,
        new=True,
    ):
        self.dataset = dataset
        self.schema = (
            dataset.schema.dict_
            if not isinstance(dataset, DatasetView)
            else dataset.dataset.schema.dict_
        )
        # assert isinstance(self.schema, dict)
        self.subpath = subpath

        self.nums = nums
        self.offsets = offsets
        self.squeeze_dims = squeeze_dims

        self.inner_schema_obj = inner_schema_obj

        if new:
            # Creating new obj
            if self.subpath:
                (
                    self.inner_schema_obj,
                    self.nums,
                    self.offsets,
                    self.squeeze_dims,
                ) = self.process_path(
                    self.subpath,
                    self.inner_schema_obj,
                    self.nums.copy(),
                    self.offsets.copy(),
                    self.squeeze_dims.copy(),
                )
            # Check if dataset view needs to be made
            if slice_list and len(slice_list) >= 1:
                num, ofs = slice_extract_info(slice_list[0], dataset.shape[0])
                self.dataset = DatasetView(
                    dataset, num, ofs, isinstance(slice_list[0], int)
                )

            if slice_list and len(slice_list) > 1:
                slice_list = slice_list[1:]
                if len(slice_list) > len(self.nums):
                    raise IndexError("Too many indices")
                for i, it in enumerate(slice_list):
                    num, ofs = slice_extract_info(it, self.nums[i])
                    self.nums[i] = num
                    self.offsets[i] += ofs
                    self.squeeze_dims[i] = num == 1

    def num_process(self, schema_obj, nums, offsets, squeeze_dims):
        if isinstance(schema_obj, SchemaDict):
            return
        if isinstance(schema_obj.max_shape, int):
            nums.append(schema_obj.max_shape)
            offsets.append(0)
            squeeze_dims.append(False)
        elif isinstance(schema_obj, Sequence):
            nums.append(0)
            offsets.append(0)
            squeeze_dims.append(False)
            if isinstance(schema_obj.dtype, Tensor):
                self.num_process(schema_obj.dtype, nums, offsets, squeeze_dims)
        else:
            for dim in schema_obj.max_shape:
                nums.append(dim)
                offsets.append(0)
                squeeze_dims.append(False)
        if not isinstance(schema_obj.dtype, Primitive) and not isinstance(
            schema_obj, Sequence
        ):
            raise ValueError("Only sequences can be nested")
        # Nested tensor. Bad use case.
        # if isinstance(schema_obj.dtype, Tensor):
        #     self.num_process(schema_obj.dtype)

    def process_path(self, subpath, inner_schema_obj, nums, offsets, squeeze_dims):
        paths = subpath.split("/")[1:]
        try:
            if inner_schema_obj:
                if isinstance(inner_schema_obj, Sequence):
                    schema_obj = inner_schema_obj.dtype.dict_[paths[0]]
                elif isinstance(inner_schema_obj, SchemaDict):
                    schema_obj = inner_schema_obj.dict_[paths[0]]
                else:
                    raise KeyError()
            else:
                schema_obj = self.schema[paths[0]]
        except KeyError:
            raise KeyError(f"{paths[0]} is an invalid key")
        self.num_process(schema_obj, nums, offsets, squeeze_dims)
        for path in paths[1:]:
            try:
                if isinstance(schema_obj, Sequence):
                    schema_obj = schema_obj.dtype.dict_[path]
                elif isinstance(schema_obj, SchemaDict):
                    schema_obj = schema_obj.dict_[path]
                else:
                    raise KeyError()
                self.num_process(schema_obj, nums, offsets, squeeze_dims)
            except KeyError:
                raise KeyError(f"{path} is an invalid key")
        return schema_obj, nums, offsets, squeeze_dims

    def __getitem__(self, slice_):
        if not isinstance(slice_, abc.Iterable) or isinstance(slice_, str):
            slice_ = [slice_]
        slice_ = list(slice_)
        subpath, slice_list = slice_split(slice_)

        dataset = self.dataset
        nums, offsets, squeeze_dims, inner_schema_obj = (
            self.nums.copy(),
            self.offsets.copy(),
            self.squeeze_dims.copy(),
            self.inner_schema_obj,
        )

        if subpath:
            inner_schema_obj, nums, offsets, squeeze_dims = self.process_path(
                subpath, inner_schema_obj, nums, offsets, squeeze_dims
            )
        subpath = self.subpath + subpath
        if len(slice_list) >= 1:
            # Slice first dim
            if isinstance(self.dataset, DatasetView) and not self.dataset.squeeze_dim:
                dataset = self.dataset[slice_list[0]]
                slice_list = slice_list[1:]
            elif not isinstance(self.dataset, DatasetView):
                num, ofs = slice_extract_info(slice_list[0], self.dataset.shape[0])
                dataset = DatasetView(
                    self.dataset, num, ofs, isinstance(slice_list[0], int)
                )
                slice_list = slice_list[1:]

            # Expand slice list for rest of dims
            if len(slice_list) >= 1:
                exp_slice_list = []
                for squeeze in squeeze_dims:
                    if squeeze:
                        exp_slice_list += [None]
                    else:
                        try:
                            exp_slice_list += [slice_list.pop(0)]
                        except IndexError:
                            # slice list smaller than max
                            exp_slice_list += [None]
                if len(slice_list) > 0:
                    # slice list longer than max
                    raise IndexError("Too many indices")
                for i, it in enumerate(exp_slice_list):
                    if it is not None:
                        num, ofs = slice_extract_info(it, nums[i])
                        nums[i] = num
                        offsets[i] += ofs
                        squeeze_dims[i] = num == 1
        return ObjectView(
            dataset=dataset,
            subpath=subpath,
            slice_list=None,
            nums=nums,
            offsets=offsets,
            squeeze_dims=squeeze_dims,
            inner_schema_obj=inner_schema_obj,
            new=False,
        )

    def numpy(self):
        if not self.subpath:
            # either dataset view or entire dataset
            # @TODO DatasetView needs compute() to support this
            if isinstance(self.dataset, DatasetView):
                return self.dataset.compute()
            else:
                # this case shouldn't arise
                return self.dataset._tensors
        else:
            if not isinstance(self.dataset, DatasetView):
                # subpath present but no slice done
                if len(self.subpath.split("/")[1:]) > 1:
                    raise IndexError("Can only go deeper on single datapoint")
                return self.dataset._tensors[self.subpath][:]
            if not self.dataset.squeeze_dim:
                # return a combined tensor for multiple datapoints
                # only possible if the field has a fixed size
                paths = self.subpath.split("/")[1:]
                if len(paths) > 1:
                    raise IndexError("Can only go deeper on single datapoint")
                slice_ = [
                    ofs if sq else slice(ofs, ofs + num) if num else slice(None, None)
                    for ofs, num, sq in zip(self.offsets, self.nums, self.squeeze_dims)
                ]
                slice_ = [slice(None, None)] + slice_
                # Will throw error if dynamic tensor, else array
                return self.dataset[[paths[0]] + slice_].compute()
            else:
                # single datapoint
                paths = self.subpath.split("/")[1:]
                schema = self.schema[paths[0]]
                slice_ = [
                    ofs if sq else slice(ofs, ofs + num) if num else slice(None, None)
                    for ofs, num, sq in zip(self.offsets, self.nums, self.squeeze_dims)
                ]
                if isinstance(schema, Sequence):
                    if isinstance(schema.dtype, SchemaDict):
                        # if sequence of dict, have to fetch everything
                        value = self.dataset[paths[0]].compute()
                        for path in paths[1:]:
                            value = value[path]
                        try:
                            return value[tuple(slice_)]
                        except TypeError:
                            # silently ignores error
                            return value
                    else:
                        # sequence of tensors
                        return self.dataset[paths[0]].compute()[tuple(slice_)]
                elif isinstance(schema, SchemaDict):
                    value = self.dataset[paths[0]]
                    for path in paths[1:]:
                        value = value[path]
                    if isinstance(value, api.tensorview.TensorView):
                        return value[slice_].compute()
                    try:
                        return value[tuple(slice_)]
                    except TypeError:
                        # silently ignores error
                        return value
                else:
                    # tensor
                    return self.dataset[[paths[0]] + slice_].compute()

    def compute(self):
        return self.numpy()

    def __setitem__(self, slice_, value):
        objview = self.__getitem__(slice_)
        assign_value = value

        if not objview.subpath:
            # either dataset view or entire dataset
            raise ValueError("Can't assign to dataset sliced without subpath")
        else:
            if not isinstance(objview.dataset, DatasetView):
                # subpath present but no slice done
                assign_value = str_to_int(assign_value, objview.dataset.tokenizer)
                if len(objview.subpath.split("/")[1:]) > 1:
                    raise IndexError("Can only go deeper on single datapoint")
                objview.dataset._tensors[objview.subpath][:] = assign_value
            if not objview.dataset.squeeze_dim:
                # assign a combined tensor for multiple datapoints
                # only possible if the field has a fixed size
                assign_value = str_to_int(
                    assign_value, objview.dataset.dataset.tokenizer
                )
                paths = objview.subpath.split("/")[1:]
                if len(paths) > 1:
                    raise IndexError("Can only go deeper on single datapoint")
                # Will throw error if dynamic tensor, else array
                try:
                    shape = list(assign_value.shape)[1:]
                    slice_ = []
                    for num, of, sq, shp in zip(
                        objview.nums, objview.offsets, objview.squeeze_dims, shape
                    ):
                        if sq:
                            slice_ += [of]
                        elif num:
                            if num < shp:
                                raise ValueError(
                                    f"Dimension with length {shp} is too big"
                                )
                            else:
                                slice_ += [slice(of, of + shp)]
                        else:
                            slice_ += [slice(None, None)]
                except AttributeError:
                    slice_ = [
                        of if sq else slice(of, of + num) if num else slice(None, None)
                        for num, of, sq in zip(
                            objview.nums, objview.offsets, objview.squeeze_dims
                        )
                    ]
                slice_ = [slice(None, None)] + slice_
                objview.dataset[[paths[0]] + slice_] = assign_value
            else:
                # single datapoint
                def assign(paths, value):
                    # helper function for recursive assign
                    if len(paths) > 0:
                        path = paths.pop(0)
                        value[path] = assign(paths, value[path])
                        return value
                    try:
                        value[tuple(slice_)] = assign_value
                    except TypeError:
                        value = assign_value
                    return value

                assign_value = str_to_int(
                    assign_value, objview.dataset.dataset.tokenizer
                )
                paths = objview.subpath.split("/")[1:]
                schema = objview.schema[paths[0]]
                slice_ = [
                    of if sq else slice(of, of + num) if num else slice(None, None)
                    for num, of, sq in zip(
                        objview.nums, objview.offsets, objview.squeeze_dims
                    )
                ]
                if isinstance(schema, Sequence):
                    if isinstance(schema.dtype, SchemaDict):
                        # if sequence of dict, have to fetch everything
                        value = objview.dataset[paths[0]].compute()
                        value = assign(paths[1:], value)
                        objview.dataset[paths[0]] = value
                    else:
                        # sequence of tensors
                        value = objview.dataset[paths[0]].compute()
                        value[tuple(slice_)] = assign_value
                        objview.dataset[paths[0]] = value
                elif isinstance(schema, SchemaDict):
                    value = objview.dataset[paths[0]]
                    value = assign(paths[1:], value)
                    objview.dataset[paths[0]] = value
                else:
                    # tensor
                    objview.dataset[[paths[0]] + slice_] = assign_value

    def __str__(self):
        if isinstance(self.dataset, DatasetView):
            slice_ = [
                self.dataset.offset
                if self.dataset.squeeze_dim
                else slice(
                    self.dataset.offset, self.dataset.offset + self.dataset.num_samples
                )
            ]
        else:
            slice_ = [slice(None, None)]
        slice_ += [
            ofs if sq else slice(ofs, ofs + num) if num else slice(None, None)
            for ofs, num, sq in zip(self.offsets, self.nums, self.squeeze_dims)
        ]
        return f"ObjectView(subpath='{self.subpath}', slice={str(slice_)})"
