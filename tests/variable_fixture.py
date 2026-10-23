"""Model-level cell edits matching the custom-variable table's input events."""
from copy import deepcopy


def column(view, ident):
    return next(item for item in view.table.columns if item['id'] == ident)


def cell(view, ident, group):
    return column(view, ident)['values'].get(group, '') or view.table.defaults.get(ident, {}).get(group, '')


def set_cell(view, ident, group, text):
    columns = deepcopy(view.table.columns)
    next(item for item in columns if item['id'] == ident)['values'][group] = text
    view.table.columns = columns
