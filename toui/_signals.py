"""
A module that creates instructions "signals" to allow communicating with JavaScript.
"""
import inspect
import json
from toui._helpers import debug, info
from copy import copy
from functools import wraps


class Signal:

    included_private_methods = ["_open_another_page"]
    no_return_functions = []

    def __init__(self, return_type=None):
        self.ws = None
        self.return_type = return_type

    def __call__(decorator, func):
        decorator._func = func
        @wraps(func)
        def new_func(self, *args, **kwargs):
            decorator.object = self
            if self._signal_mode:
                original_copy = copy(self)
            value = decorator._func(self, *args, **kwargs)
            real_output = value
            if self._signal_mode:
                if self.__class__.__name__ == 'Element':
                    decorator.ws = self._parent_page.__dict__.get("_ws")
                    decorator.evaluate_js = self._parent_page._evaluate_js
                elif self.__class__.__name__ == "Page":
                    decorator.ws = self.__dict__.get("_ws")
                    decorator.evaluate_js = self._evaluate_js
                kwargs = inspect.signature(decorator._func).bind(self, *args, **kwargs)
                kwargs.apply_defaults()
                kwargs = kwargs.arguments
                kwargs['return_value'] = value
                kwargs['object'] = kwargs['self']
                kwargs['original_copy'] = original_copy
                del kwargs['self']
                real_output = decorator._call_method(decorator._func, **kwargs)
            if func.__name__ in decorator.no_return_functions:
                return
            if decorator.return_type == "js":
                return real_output
            return value
        return new_func

    def _call_method(self, func, **kwargs):
        for method_name, method in inspect.getmembers(self, inspect.isfunction):
            if method_name == func.__name__ and (not method_name.startswith("_") or
                                                 method_name in self.included_private_methods):
                signal = method(**kwargs)
                if signal:
                    return self._send(signal)
                else:
                    return

    def _send(self, signal):
        if self.ws:
            self.ws.send(json.dumps(signal))
            debug(f"SENT: {signal}")
            if self.return_type == "js":
                data_from_js = self.ws.receive()
                debug(f"DATA RECEIVED")
                data_validation = self.object._app._validate_data(data_from_js)
                if not data_validation:
                    info("Data validation returns `False`. The data will not be used.")
                    return
                data_dict = json.loads(data_from_js)
                debug(f"RECEIVED DATA KEYS: {list(data_dict.keys())}")
                if data_dict['type'] == "files":
                    files = []
                    for file_dict in data_dict['data']:
                        files.append(File(file_dict, signal, self.object._app, file_dict['file-id'], ws=self.ws))
                    return files
                return data_dict['data']
        else:
            out = self.evaluate_js(func=signal['func'], kwargs=signal['kwargs'])
            debug(f"SENT: {signal}")
            if self.return_type == "js":
                try:
                    data_dict = json.loads(out)
                    debug(f"DATA RECEIVED")
                    if data_dict['type'] == "files":
                        files = []
                        for file_dict in data_dict['data']:
                            files.append(File(file_dict, signal, self.object._app, file_dict['file-id'], ws=None))
                        return files
                except: data_dict = {"data": None}
                return data_dict['data']


class File:
    """
    Contains the information of an uploaded file and can be used to save the file contents.

    This object should only be created through `Element.get_files()` method.

    Attributes
    ----------
    name
        Name of the file.

    type
        Type of the file.

    size
        Size of the file.

    last_modified
        The last modified date as the number of milliseconds since the Unix epoch (January 1, 1970 at midnight).

    is_binary: bool
        Set the value of this attribute to ``True`` only if you want the file content to be converted to bytes
        before saving it.

    See Also
    --------
    Element.get_files()

    """
    def __init__(self, file_dict, signal, app, file_id, ws=None):
        self._file_dict = file_dict
        self.name = self._file_dict['name']
        self.size = self._file_dict['size']
        self.type = self._file_dict['type']
        self.last_modified = self._file_dict['last-modified']
        self._ws = ws
        self._id = file_id
        self._app = app
        self._signal = signal
        self.is_binary = False

    def __iter__(self):
        js_func = "_saveFile"
        js_args = []
        js_kwargs = {}
        js_kwargs['file-id'] = self._id
        js_kwargs['binary'] = self.is_binary
        signal = {'func': js_func, 'args': js_args, 'kwargs': js_kwargs}
        if self._ws:
            self._ws.send(json.dumps(signal))
            debug(f"SENT: {signal}")
            while True:
                data_from_js = self._ws.receive()
                data_validation = self._app._validate_data(data_from_js)
                if not data_validation:
                    info("Data validation returns `False`. The data will not be used.")
                    return
                data_dict = json.loads(data_from_js)
                data = data_dict['data']
                if self.is_binary:
                    data = bytearray(data)
                yield data
                if data_dict['end'] == True:
                    break
        else:
            out = self._signal.evaluate_js(func=signal['func'], kwargs=signal['kwargs'])
            debug(f"SENT: {signal}")
            while True:
                data_from_js = out
                data_dict = json.loads(data_from_js)
                data = data_dict['data']
                if self.is_binary:
                    data = bytearray(data)
                yield data
                if data_dict['end'] == True:
                    break

    def __repr__(self):
        return f"<File {self.name}>"

    def save(self, stream):
        """
        Saves the contents of the file to a stream.

        Parameters
        ----------
        stream

        Examples
        --------
        Saving a `File` object to a stream.

        >>> def saveFile():
        ...     pg = app.get_user_page()
        ...     input_element = pg.get_element("file-element") # Assuming 'file-content' is an id of an element that uploads files
        ...     files = input_element.get_files()
        ...     for file in files:
        ...         with open(file.name, "w") as stream:
        ...             file.save(stream)
        """
        for data in self:
            stream.write(data)
            stream.flush()