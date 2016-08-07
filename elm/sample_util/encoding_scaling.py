import copy
from functools import partial

import numpy as np
import sklearn.preprocessing as sklearn_pre
import xarray as xr

from elm.config import import_callable
from elm.sample_util.util import bands_as_columns
from elm.sample_util.elm_store import ElmStore
from elm.model_selection.util import get_args_kwargs_defaults

DIR_SKPRE = dir(sklearn_pre)


def _import_scaler(scaler_str):
    if scaler_str in DIR_SKPRE:
        scaler = getattr(sklearn_pre, scaler_str)
    else:
        scaler = import_callable(scaler)
    a, k, d = get_args_kwargs_defaults(scaler)
    if 'X' in a or 'x' in a:
        is_preproc_class = False
    else:
        is_preproc_class = True
    if 'classes' in a:
        requires_classes = True
    else:
        requires_classes = False
    return (scaler, is_preproc_class, requires_classes)


def _update_elm_store_for_changes(es, new_array, new_names=None):
    old_shp = es.sample.shape
    if new_array.shape[1] != old_shp[1]:
        if (new_names and len(new_names) != es.shape[1]) or new_array.shape[1] < old_shp[1]:
            raise ValueError('Expected "new_names" to have length {} but got '
                             '{} (expected because scaler decreases column size of input '
                             'matrix)'.format(es.sample.shape[1], new_names))
        inds = range(old_shp[1], new_array.shape[1])
        new_names = list(es.sample.band) + ['band_{}'.format(idx) for idx in inds]
        return ElmStore({'sample': xr.DataArray(new_array,
                                        coords=[(es.sample.dims[0], getattr(es.sample, es.sample.dims[0])),
                                                ('band', new_names)],
                                        dims=es.sample.dims,
                                        attrs=copy.deepcopy(es.sample.attrs))},
                        attrs=copy.deepcopy(es.attrs))
    else:
        assert new_array.shape == old_shp, (repr((new_array.shape, old_shp)))
        es.sample.values= new_array
    return es


def _filter_kwargs(**scaler_kwargs):
    return {k: v for k, v in scaler_kwargs.items()
            if not k in ('new_names', 'func_kwargs', 'method',)}


def _scale_with_sklearn_pre_class(X, scaler, requires_classes=False, **scaler_kwargs):
    s = scaler(**_filter_kwargs(**scaler_kwargs))
    scaled = s.fit_transform(X.sample.values)
    return _update_elm_store_for_changes(X,
                                         scaled,
                                         new_names=scaler_kwargs.get('new_names'))

def _scale_with_sklearn_func(X, scaler, **scaler_kwargs):
    scaled = scaler(X, **_filter_kwargs(**scaler_kwargs))
    return _update_elm_store_for_changes(X,
                                         scaled,
                                         new_names=scaler_kwargs.get('new_names'))

@bands_as_columns
def sklearn_preprocessing(X, scaler, **scaler_kwargs):
    scaler_kwargs = copy.deepcopy(scaler_kwargs or {})
    (scaler, is_preproc_class, requires_classes) = _import_scaler(scaler)
    if requires_classes and not 'classes' in scaler_kwargs:
        raise ValueError('scaler {} requires "classes" but those were '
                         'not in scaler_kwargs'.format(scaler))
    if 'func' in scaler_kwargs:
        func = import_callable(scaler_kwargs['func'])
        kwargs = scaler_kwargs.get('kwargs_to_func') or {}
        scaler_kwargs['func'] = partial(func, **kwargs)
    if is_preproc_class:
        return _scale_with_sklearn_pre_class(X, scaler, **scaler_kwargs)
    return _scale_with_sklearn_func(X, scaler, **scaler_kwargs)


def require_positive(X, small_num=0.0001):
    if not X.dtype.kind == 'f':
        X = X.astype(np.float32)
    X[np.where(X <= 0)] = small_num
    assert np.all(X >= 0)
    return X
