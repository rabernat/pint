# -*- coding: utf-8 -*-
"""
    pint.numpy_func
    ~~~~~~~~~~~~~~~

    :copyright: 2019 by Pint Authors, see AUTHORS for more details.
    :license: BSD, see LICENSE for more details.
"""

from .compat import is_upcast_type, np, string_types
from .errors import DimensionalityError
from .util import iterable, sized

HANDLED_UFUNCS = {}
HANDLED_FUNCTIONS = {}


#
# Shared Implementation Utilities
#


# TODO: make more robust and test
def _is_quantity_sequence(arg):
    if iterable(arg) and sized(arg) and not isinstance(arg, string_types):
        if hasattr(arg[0], 'units'):
            if not all([hasattr(item, 'units') for item in arg]):
                raise TypeError("{} contains items that aren't Quantity type".format(arg))
            return True
    return False


def _get_first_input_units(args, kwargs={}):
    args_combo = list(args) + list(kwargs.values())
    out_units=None
    for arg in args_combo:
        if hasattr(arg, 'units'):  # TODO better check?
            out_units = arg.units
        elif _is_quantity_sequence(arg):
            out_units = arg[0].units
        if out_units is not None:
            break
    return out_units


def convert_to_consistent_units(*args, pre_calc_units=None, **kwargs):
    """Takes the args for a numpy function and converts any Quantity or Sequence of Quantities 
    into the units of the first Quantiy/Sequence of quantities. Other args are left untouched
    if pre_calc_units is None or dimensionless, otherwise a DimensionalityError is raised.
    """
    def convert_arg(arg):
        if pre_calc_units is not None:
            if hasattr(arg, 'units'):  # TODO better check?
                return arg.m_as(pre_calc_units)
            elif _is_quantity_sequence(arg):
                return [item.m_as(pre_calc_units) for item in arg]
            elif arg is not None:
                if pre_calc_units.dimensionless:
                    return pre_calc_units._REGISTRY.Quantity(arg).m_as(pre_calc_units)
                else:
                    raise DimensionalityError('dimensionless', pre_calc_units)
        else:
            if hasattr(arg, 'units'):  # TODO better check?
                return arg.m
            elif _is_quantity_sequence(arg):
                return [item.m for item in arg]
        return arg

    new_args = tuple(convert_arg(arg) for arg in args)
    new_kwargs = {key: convert_arg(arg) for key, arg in kwargs.items()}
    return new_args, new_kwargs


def unwrap_and_wrap_consistent_units(*args):
    """Returns the given args as parsed by convert_to_consistent_units assuming units of first
    arg with units, along with a wrapper to restore that unit to the output.
    """
    first_input_units = _get_first_input_units(args)
    args, _ = convert_to_consistent_units(*args, pre_calc_units=first_input_units)
    return args, lambda value: first_input_units._REGISTRY.Quantity(value, first_input_units)


def get_op_output_unit(unit_op, first_input_units, all_args=[], size=None):
    """Determine resulting unit from given operation."""
    if unit_op == "sum":
        result_unit = (1 * first_input_units + 1 * first_input_units).units
    elif unit_op == "mul":
        product = first_input_units._REGISTRY.parse_units('')
        for x in all_args:
            print(x)
            if hasattr(x, 'units'):
                product *= x.units
        result_unit = product
    elif unit_op == "delta":
        result_unit = (1 * first_input_units - 1 * first_input_units).units
    elif unit_op == "delta,div":
        product = (1 * first_input_units - 1 * first_input_units).units
        for x in all_args[1:]:
            if hasattr(x, 'units'):
                product /= x.units
        result_unit = product
    elif unit_op == "div":
        product = first_input_units._REGISTRY.parse_units('')
        for x in all_args:
            if hasattr(x, 'units'):
                product /= x.units
        result_unit = product
    elif unit_op == "variance":
        result_unit = ((1 * first_input_units + 1 * first_input_units)**2).units
    elif unit_op == "square":
        result_unit = first_input_units**2
    elif unit_op == "sqrt":
        result_unit = first_input_units**0.5
    elif unit_op == "reciprocal":
        result_unit = first_input_units**-1
    elif unit_op == "size":
        if size is None:
            raise ValueError('size argument must be given when unit_op=="size"')
        result_unit = first_input_units**size

    else:
        raise ValueError('Output unit method {} not understood'.format(unit_op))

    return result_unit


def implements(numpy_func_string, func_type):
    """Register an __array_function__/__array_ufunc__ implementation for Quantity objects."""
    def decorator(func):
        if func_type == 'function':
            HANDLED_FUNCTIONS[numpy_func_string] = func
        elif func_type == 'ufunc':
            HANDLED_UFUNCS[numpy_func_string] = func
        else:
            raise ValueError('Invalid func_type {}'.format(func_type))
        return func
    return decorator


def implement_func(func_type, func_str, input_units=None, output_unit=None):
    """TODO"""
    func = getattr(np, func_str)

    @implements(func_str, func_type)
    def implementation(*args, **kwargs):
        args_and_kwargs = list(args) + list(kwargs.values())
        first_input_units = _get_first_input_units(args, kwargs)
        if input_units == "all_consistent":
            # Match all input args/kwargs to same units
            stripped_args, stripped_kwargs = convert_to_consistent_units(
                *args, pre_calc_units=first_input_units, **kwargs)
        else:
            # Match all input args/kwargs to input_units, or if input_units is None, simply
            # strip units 
            stripped_args, stripped_kwargs = convert_to_consistent_units(
                *args, pre_calc_units=input_units, **kwargs)

        # Determine result through base numpy function on stripped arguments
        result_magnitude = func(*stripped_args, **stripped_kwargs)

        if output_unit is None:
            # Short circuit and return magnitude alone
            return result_magnitude
        elif output_unit == "match_input":
            result_unit = first_input_units
        else:
            result_unit = get_op_output_unit(output_unit, first_input_units, args_and_kwargs)

        return first_input_units._REGISTRY.Quantity(result_magnitude, result_unit)


"""
Define ufunc behavior collections.

TODO: document as before


"""
matching_input_bare_output_ufuncs = ['equal', 'greater', 'greater_equal', 'less',
                                     'less_equal', 'not_equal']
matching_input_set_units_output_ufuncs = {'arctan2': 'radian'}
set_units_ufuncs = {'cumprod': ('', ''),
                    'arccos': ('', 'radian'),
                    'arcsin': ('', 'radian'),
                    'arctan': ('', 'radian'),
                    'arccosh': ('', 'radian'),
                    'arcsinh': ('', 'radian'),
                    'arctanh': ('', 'radian'),
                    'exp': ('', ''),
                    'expm1': ('', ''),
                    'exp2': ('', ''),
                    'log': ('', ''),
                    'log10': ('', ''),
                    'log1p': ('', ''),
                    'log2': ('', ''),
                    'sin': ('radian', ''),
                    'cos': ('radian', ''),
                    'tan': ('radian', ''),
                    'sinh': ('radian', ''),
                    'cosh': ('radian', ''),
                    'tanh': ('radian', ''),
                    'radians': ('degree', 'radian'),
                    'degrees': ('radian', 'degree'),
                    'deg2rad': ('degree', 'radian'),
                    'rad2deg': ('radian', 'degree'),
                    'logaddexp': ('', ''),
                    'logaddexp2': ('', '')}
matching_input_copy_units_output_ufuncs = ['compress', 'conj', 'conjugate', 'copy',
                                           'diagonal', 'max', 'mean', 'min',
                                           'ptp', 'ravel', 'repeat', 'reshape', 'round',
                                           'squeeze', 'swapaxes', 'take', 'trace',
                                           'transpose', 'ceil', 'floor', 'hypot', 'rint',
                                           'add', 'subtract', 'copysign', 'nextafter',
                                           'trunc', 'frexp', 'absolute', 'negative']  # TODO: review extra args/kwargs
copy_units_output_ufuncs = ['ldexp', 'fmod', 'mod', 'remainder']
op_units_output_ufuncs = {'var': 'square', 'prod': 'size', 'multiply': 'mul',
                          'true_divide': 'div', 'divide': 'div', 'floor_divide': 'div',
                          'remainder': 'div', 'sqrt': 'sqrt', 'square': 'square',
                          'reciprocal': 'reciprocal', 'std': 'sum', 'sum': 'sum',
                          'cumsum': 'sum'}


# Perform the standard ufunc implementations based on behavior collections
for ufunc_str in matching_input_bare_output_ufuncs:
    # Require all inputs to match units, but output base ndarray
    implement_func('ufunc', ufunc_str, input_units='all_consistent', output_unit=None)

for ufunc_str, out_unit in matching_input_set_units_output_ufuncs.items():
    # Require all inputs to match units, but output in specified unit
    implement_func('ufunc', ufunc_str, input_units='all_consistent', output_unit=out_unit)

for ufunc_str, (in_unit, out_unit) in set_units_ufuncs.items():
    # Require inputs in specified unit, and output in specified unit
    implement_func('ufunc', ufunc_str, input_units=in_unit, output_unit=out_unit)

for ufunc_str in matching_input_copy_units_output_ufuncs:
    # Require all inputs to match units, and output as first unit in arguments
    implement_func('ufunc', ufunc_str, input_units='all_consistent',
                   output_unit='match_input')

for ufunc_str in copy_units_output_ufuncs:
    # Output as first unit in arguments, but do not convert inputs
    implement_func('ufunc', ufunc_str, input_units=None, output_unit='match_input')

for ufunc_str, unit_op in op_units_output_ufuncs.items():
    implement_func('ufunc', ufunc_str, input_units=None, output_unit=unit_op)


# TODO: modf (since it had the old modf__1)


"""
Define function behavior

TODO: Document
"""


@implements('meshgrid', 'function')
def _meshgrid(*xi, **kwargs):
    # Simply need to map input units to onto list of outputs
    input_units = (x.units for x in xi)
    res = np.meshgrid(*(x.m for x in xi), **kwargs)
    return [out * unit for out, unit in zip(res, input_units)]


@implements('full_like', 'function')
def _full_like(a, fill_value, dtype=None, order='K', subok=True, shape=None):
    # Make full_like by multiplying with array from ones_like in a
    # non-multiplicative-unit-safe way
    if hasattr(fill_value, '_REGISTRY'):
        return fill_value._REGISTRY.Quantity(
            (np.ones_like(a, dtype=dtype, order=order, subok=subok, shape=shape)
             * fill_value.m), fill_value.units)
    else:
        return (np.ones_like(a, dtype=dtype, order=order, subok=subok, shape=shape)
                * fill_value)


@implements('interp', 'function')
def _interp(x, xp, fp, left=None, right=None, period=None):
    # Need to handle x and y units separately
    (x, xp, period), _ = unwrap_and_wrap_consistent_units(x, xp, period)
    (fp, right, left), output_wrap = unwrap_and_wrap_consistent_units(fp, left, right)
    return output_wrap(np.interp(x, xp, fp, left=left, right=right, period=period))


@implements('where', 'function')
def _where(condition, *args):
    args, output_wrap = unwrap_and_wrap_consistent_units(*args)
    return output_wrap(np.where(condition, *args))


@implements('linspace', 'function')
def _linspace(start, stop, *args, **kwargs):
    (start, stop), output_wrap = unwrap_and_wrap_consistent_units(start, stop)
    return output_wrap(np.linspace(start, stop, *args, **kwargs))


@implements('concatenate', 'function')
def _concatenate(sequence, *args, **kwargs):
    sequence, output_wrap = unwrap_and_wrap_consistent_units(*sequence)
    return output_wrap(np.concatenate(sequence, *args, **kwargs))


@implements('stack', 'function')
def _stack(arrays, *args, **kwargs):
    arrays, output_wrap = unwrap_and_wrap_consistent_units(*arrays)
    return output_wrap(np.stack(arrays, *args, **kwargs))


@implements('compress', 'function')
def _compress(condition, a, *args, **kwargs):
    (a,), output_wrap = unwrap_and_wrap_consistent_units(a)
    return output_wrap(np.compress(condition, a, *args, **kwargs))


@implements('append', 'function')
def _append(arr, values, axis=None):
    (arr, values), output_wrap = unwrap_and_wrap_consistent_units(arr, values)
    return output_wrap(np.append(arr, values, axis))


@implements('clip', 'function')
def _clip(a, a_min, a_max, *args, **kwargs):
    (a, a_min, a_max), output_wrap = unwrap_and_wrap_consistent_units(a, a_min, a_max)
    return output_wrap(np.clip(a, a_min, a_max, *args, **kwargs))


@implements('nan_to_num', 'function')
def _nan_to_num(x, copy=True, nan=None, posinf=None, neginf=None):
    if nan is None:
        nan = 0.0
    elif isinstance(nan, x.__class__):
        nan = nan.m_as(x.units)
    posinf = posinf if not isinstance(posinf, x.__class__) else posinf.m_as(x.units)
    neginf = neginf if not isinstance(neginf, x.__class__) else neginf.m_as(x.units)
    result_magnitude = np.nan_to_num(x.magnitude, copy=False, nan=nan, posinf=posinf,
                                     neginf=neginf)
    if not copy:
        x._magnitude = result_magnitude

    return x._REGISTRY.Quantity(result_magnitude, x.units)


@implements('isclose', 'function')
def _isclose(a, b, rtol=None, atol=None, equal_nan=False):
    (a, b, rtol, atol), _ = unwrap_and_wrap_consistent_units(a, b, rtol, atol)
    rtol = 1e-05 if rtol is None else rtol
    atol = 1e-08 if atol is None else atol
    return np.isclose(a, b, rtol, atol, equal_nan)


@implements('searchsorted', 'function')
def _searchsorted(a, v, *args, **kwargs):
    (a, v), _ = unwrap_and_wrap_consistent_units(a, v)
    return np.searchsorted(a, v, *args, **kwargs)


@implements('unwrap', 'function')
def _unwrap(p, discont=None, axis=-1):
    # np.unwrap only dispatches over p argument, so assume it is a Quantity
    discont = np.pi if discont is None else discont
    return p._REGISTRY.Quantity(np.unwrap(p.m_as('rad'), discont, axis=axis),
                                'rad').to(p.units)

# Handle single unit argument operations (axis ops, aggregations, etc.)
def implement_single_unit(func_str):
    func = getattr(np, func_str)

    @implements(func_str, 'function')
    def implementation(a, *args, **kwargs):
        (a,), output_wrap = unwrap_and_wrap_consistent_units(a)
        return output_wrap(func(a, *args, **kwargs))


for func_str in ['expand_dims', 'squeeze', 'rollaxis', 'moveaxis', 'fix', 'around',
                 'diagonal', 'mean', 'ptp', 'ravel', 'round_', 'sort', 'median', 'nanmedian',
                 'transpose', 'flip', 'copy', 'trim_zeros', 'average', 'nanmean']:
    implement_single_unit(func_str)


# Handle atleast_nd functions
def implement_atleast_nd(func_str):
    func = getattr(np, func_str)
    @implements(func_str, 'function')
    def implementation(*arrays):
        stripped_arrays, _ = convert_to_consistent_units(*arrays)
        arrays_magnitude = func(*stripped_arrays)
        if len(arrays) > 1:
            return [array_magnitude if not hasattr(original, '_REGISTRY')
                    else original._REGISTRY.Quantity(array_magnitude, original.units)
                    for array_magnitude, original in zip(arrays_magnitude, arrays)]
        else:
            output_unit = arrays[0].units
            return output_unit._REGISTRY.Quantity(arrays_magnitude, output_unit)


for func_str in ['atleast_1d', 'atleast_2d', 'atleast_3d']:
    implement_atleast_nd(func_str)

# Handle single-argument consistent unit functions
for func_str in ['block', 'hstack', 'vstack', 'dstack', 'column_stack']:
    implement_func('function', func_str, input_units='all_consistent',
                   output_unit='match_input')

for func_str in ['cumprod', 'cumproduct', 'nancumprod']:
    implement_func('function', func_str, input_units='dimensionless',
                   output_unit='match_input')

for func_str in ['size', 'isreal', 'iscomplex', 'shape', 'ones_like', 'zeros_like',
                 'empty_like', 'argsort', 'argmin', 'argmax', 'alen', 'ndim', 'nanargmax',
                 'nanargmin', 'count_nonzero', 'nonzero', 'result_type']:
    implement_func('function', func_str, input_units=None, output_unit=None)

# TODO: Verify all these below with non-united other arguments \/ !!

for func_str in ['std', 'nanstd', 'sum', 'nansum', 'cumsum', 'nancumsum']:
    implement_func('function', func_str, input_units=None, output_unit='sum')

for func_str in ['cross', 'trapz', 'dot']:
    implement_func('function', func_str, input_units=None, output_unit='mul')

for func_str in ['diff', 'ediff1d']:
    implement_func('function', func_str, input_units=None, output_unit='delta')

for func_str in ['gradient', ]:
    implement_func('function', func_str, input_units=None, output_unit='delta,div')

for func_str in ['var', 'nanvar']:
    implement_func('function', func_str, input_units=None, output_unit='variance')

# TODO: broadcast_to (how to handle subok?)
# TODO: result_type
# TODO: 'amax', 'amin', 'nanmax', 'nanmin' (version dependent signatures)
# TODO: nan_to_num (expected behavior with input values, sensible defaults?)


def numpy_wrap(func_type, func, args, kwargs, types):
    # TODO: documentation
    if func_type == 'function':
        handled = HANDLED_FUNCTIONS
    elif func_type == 'ufunc':
        handled = HANDLED_UFUNCS
    else:
        raise ValueError('Invalid func_type {}'.format(func_type))

    if func.__name__ not in handled or any(is_upcast_type(t) for t in types):
        return NotImplemented
    return handled[func.__name__](*args, **kwargs)
